# -*- coding: utf-8 -*-
import json
import logging
from datetime import datetime

from psycopg2 import IntegrityError

from odoo import Command, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

REQUIRED_FIELDS = ('external_order_id', 'items')


class McRawOrder(models.Model):
    _name = 'mc.raw.order'
    _description = 'Raw Incoming Order'
    _order = 'received_at desc, id desc'
    _inherit = ['mail.thread']
    _rec_name = 'external_order_id'

    channel_id = fields.Many2one('mc.channel', string='Channel', required=True, ondelete='restrict', index=True, tracking=True)
    external_order_id = fields.Char(string='External Order ID', index=True)
    raw_payload = fields.Text(string='Raw Payload (JSON)', required=True)
    state = fields.Selection(
        selection=[('new', 'New'), ('parsed', 'Parsed'), ('processed', 'Processed'), ('error', 'Error')],
        default='new',
        required=True,
        index=True,
        tracking=True,
    )
    error_message = fields.Text(readonly=True)
    received_at = fields.Datetime(default=fields.Datetime.now, required=True, readonly=True)
    parsed_at = fields.Datetime(readonly=True)
    processed_at = fields.Datetime(readonly=True)

    parsed_external_order_id = fields.Char(string='Parsed Order ID', readonly=True)
    parsed_customer_name = fields.Char(string='Customer Name', readonly=True)
    parsed_customer_phone = fields.Char(string='Customer Phone', readonly=True)
    parsed_customer_email = fields.Char(string='Customer Email', readonly=True)
    parsed_shipping_address = fields.Char(string='Shipping Address', readonly=True)
    parsed_order_date = fields.Datetime(string='Order Date', readonly=True)
    parsed_total_amount = fields.Float(string='Total Amount', digits=(12, 2), readonly=True)
    parsed_currency = fields.Char(string='Currency', readonly=True)
    parsed_items_json = fields.Text(string='Parsed Items (JSON)', readonly=True)

    sale_order_id = fields.Many2one('sale.order', string='Resulting Sales Order', readonly=True, ondelete='set null')

    _sql_constraints = [
        (
            'unique_channel_external_order',
            'UNIQUE(channel_id, external_order_id)',
            'This external order ID has already been received from this channel.',
        ),
    ]

    def action_parse(self):
        for record in self.filtered(lambda raw: raw.state in ('new', 'error')):
            record._parse_raw_order()

    def action_process(self):
        for record in self.filtered(lambda raw: raw.state == 'parsed'):
            record._process_raw_order()

    def action_reprocess(self):
        records = self.filtered(lambda raw: raw.state == 'error')
        if not records:
            raise UserError('No error records selected to reprocess.')
        records.write({
            'state': 'new',
            'error_message': False,
            'parsed_at': False,
            'parsed_external_order_id': False,
            'parsed_customer_name': False,
            'parsed_customer_phone': False,
            'parsed_customer_email': False,
            'parsed_shipping_address': False,
            'parsed_order_date': False,
            'parsed_total_amount': False,
            'parsed_currency': False,
            'parsed_items_json': False,
        })

    def action_open_sale_order(self):
        self.ensure_one()
        if not self.sale_order_id:
            raise UserError('This raw order has not been processed yet.')
        return {
            'type': 'ir.actions.act_window',
            'name': 'Sales Order',
            'res_model': 'sale.order',
            'view_mode': 'form',
            'res_id': self.sale_order_id.id,
        }

    def _parse_raw_order(self) -> None:
        self.ensure_one()
        try:
            payload = self._load_json_payload()
            parsed = self._extract_standard_payload(payload)
            self.write({
                'state': 'parsed',
                'error_message': False,
                'parsed_at': fields.Datetime.now(),
                'external_order_id': parsed['external_order_id'],
                'parsed_external_order_id': parsed['external_order_id'],
                'parsed_customer_name': parsed['customer_name'],
                'parsed_customer_phone': parsed['customer_phone'],
                'parsed_customer_email': parsed['customer_email'],
                'parsed_shipping_address': parsed['shipping_address'],
                'parsed_order_date': parsed['order_date'],
                'parsed_total_amount': parsed['total_amount'],
                'parsed_currency': parsed['currency'],
                'parsed_items_json': json.dumps(parsed['items']),
            })
            self.env['mc.sync.log']._log(
                'info',
                f'Parsed raw order {parsed["external_order_id"]} successfully.',
                channel_id=self.channel_id.id,
                reference=parsed['external_order_id'],
            )
        except Exception as exc:
            message = str(exc)
            self.write({'state': 'error', 'error_message': message})
            self.env['mc.sync.log']._log('error', f'Parse failed for raw order #{self.id}: {message}', self.channel_id.id, self.external_order_id)
            _logger.warning('mc.raw.order parse failed id=%s: %s', self.id, message)

    def _process_raw_order(self) -> None:
        self.ensure_one()
        if self.state != 'parsed':
            raise UserError('Raw order must be parsed before processing.')
        try:
            with self.env.cr.savepoint():
                sale_order = self._upsert_sale_order_from_raw()
                self._apply_channel_status_to_sale_order(sale_order)
                self.write({
                    'state': 'processed',
                    'error_message': False,
                    'processed_at': fields.Datetime.now(),
                    'sale_order_id': sale_order.id,
                })
            self.env['mc.sync.log']._log(
                'info',
                f'Sales order {sale_order.name} created from raw order {self.parsed_external_order_id}.',
                channel_id=self.channel_id.id,
                reference=self.parsed_external_order_id,
            )
        except IntegrityError as exc:
            message = 'Duplicate conflict while processing order. Please retry.'
            self.env.cr.rollback()
            self.write({'state': 'error', 'error_message': message})
            self.env['mc.sync.log']._log('error', f'Processing conflict for raw order #{self.id}: {exc}', self.channel_id.id, self.parsed_external_order_id)
            _logger.warning('mc.raw.order process integrity conflict id=%s: %s', self.id, exc)
        except Exception as exc:
            message = str(exc)
            self.write({'state': 'error', 'error_message': message})
            self.env['mc.sync.log']._log('error', f'Processing failed for raw order #{self.id}: {message}', self.channel_id.id, self.parsed_external_order_id)
            _logger.warning('mc.raw.order process failed id=%s: %s', self.id, message)

    def _upsert_sale_order_from_raw(self):
        items = json.loads(self.parsed_items_json or '[]')
        resolved_lines = []
        unmapped = []
        oversold = []
        
        for item in items:
            mapping = self.env['mc.product.mapping'].search([
                ('channel_id', '=', self.channel_id.id),
                ('external_sku', '=', item['external_sku']),
                ('is_active', '=', True),
            ], limit=1)
            if mapping:
                # Overselling Check
                requested_qty = item['quantity']
                if self.channel_id.sudo().strict_stock_check:
                    # check if requested exceeds what we believe we have available to sync
                    if requested_qty > mapping.synced_qty:
                        oversold.append(f"{item['external_sku']} (Req: {requested_qty}, Avail: {mapping.synced_qty})")
                
                resolved_lines.append((mapping, item))
            else:
                unmapped.append(item['external_sku'])
                
        if unmapped:
            raise UserError('Unmapped SKU(s):\n' + '\n'.join(f'  - {sku}' for sku in unmapped))
            
        if oversold:
            raise UserError('Overselling prevented: Not enough stock for:\n' + '\n'.join(f'  - {sku}' for sku in oversold))

        partner = self._find_or_create_partner()
        line_commands = [
            Command.create(self._prepare_sale_order_line(mapping, item))
            for mapping, item in resolved_lines
        ]
        order_vals = {
            'partner_id': partner.id,
            'date_order': self.parsed_order_date,
            'client_order_ref': self.parsed_external_order_id,
            'mc_channel_id': self.channel_id.id,
            'mc_external_order_id': self.parsed_external_order_id,
            'mc_raw_order_id': self.id,
        }

        sale_order = self.env['sale.order'].search([
            ('mc_channel_id', '=', self.channel_id.id),
            ('mc_external_order_id', '=', self.parsed_external_order_id),
        ], limit=1)

        if sale_order:
            if sale_order.state in ('draft', 'sent'):
                sale_order.order_line.unlink()
                sale_order.write({**order_vals, 'order_line': line_commands})
            else:
                sale_order.write({
                    'partner_id': partner.id,
                    'client_order_ref': self.parsed_external_order_id,
                    'mc_raw_order_id': self.id,
                })
        else:
            sale_order = self.env['sale.order'].create({
                **order_vals,
                'order_line': line_commands,
            })
        return sale_order

    def _apply_channel_status_to_sale_order(self, sale_order) -> None:
        self.ensure_one()
        if not hasattr(sale_order, '_mc_apply_channel_statuses'):
            return
        order_status = self._get_channel_order_status() or 'unknown'
        payment_status = self._get_channel_payment_status() or 'unknown'
        updated_at = self._get_channel_status_updated_at()
        sale_order._mc_apply_channel_statuses(order_status, payment_status, updated_at)

    def _get_channel_order_status(self):
        self.ensure_one()
        if 'canonical_order_status' in self._fields:
            return self.canonical_order_status
        return False

    def _get_channel_payment_status(self):
        self.ensure_one()
        if 'canonical_payment_status' in self._fields:
            return self.canonical_payment_status
        return False

    def _get_channel_status_updated_at(self):
        self.ensure_one()
        if 'platform_status_updated_at' in self._fields:
            return self.platform_status_updated_at
        return False

    def _prepare_sale_order_line(self, mapping, item: dict) -> dict:
        product = mapping.product_id
        return {
            'product_id': product.id,
            'name': item.get('product_name') or product.display_name,
            'product_uom_qty': item['quantity'],
            'product_uom': product.uom_id.id,
            'price_unit': item['unit_price'],
            'mc_external_sku': item['external_sku'],
            'mc_mapping_id': mapping.id,
        }

    def _find_or_create_partner(self):
        Partner = self.env['res.partner']
        # 1. Try email (most reliable dedup key)
        if self.parsed_customer_email:
            partner = Partner.search([('email', '=', self.parsed_customer_email)], limit=1)
            if partner:
                return partner
        # 2. Try phone
        if self.parsed_customer_phone:
            partner = Partner.search([('phone', '=', self.parsed_customer_phone)], limit=1)
            if partner:
                return partner
        # 3. Try name (prevent duplicate contacts for same-named customers)
        customer_name = self.parsed_customer_name or f'Customer {self.parsed_external_order_id}'
        if self.parsed_customer_name:
            partner = Partner.search([('name', '=', customer_name), ('customer_rank', '>', 0)], limit=1)
            if partner:
                return partner
        return Partner.create({
            'name': customer_name,
            'phone': self.parsed_customer_phone or False,
            'email': self.parsed_customer_email or False,
            'street': self.parsed_shipping_address or False,
            'customer_rank': 1,
        })

    def _load_json_payload(self) -> dict:
        if not self.raw_payload or not self.raw_payload.strip():
            raise ValueError('Raw payload is empty.')
        data = json.loads(self.raw_payload)
        if not isinstance(data, dict):
            raise ValueError('Payload must be a JSON object.')
        return data

    def _extract_standard_payload(self, payload: dict) -> dict:
        for key in REQUIRED_FIELDS:
            if not payload.get(key):
                raise ValueError(f'Required field "{key}" is missing or empty.')
        external_order_id = str(payload['external_order_id']).strip()
        items = []
        for index, item in enumerate(payload['items']):
            sku = str(item.get('external_sku', '')).strip()
            quantity = float(item.get('quantity', 0))
            if not sku:
                raise ValueError(f'Order {external_order_id}: item #{index} is missing external_sku.')
            if quantity <= 0:
                raise ValueError(f'Order {external_order_id}: item {sku} has invalid quantity {quantity}.')
            items.append({
                'external_sku': sku,
                'product_name': str(item.get('product_name', '')).strip(),
                'quantity': quantity,
                'unit_price': float(item.get('unit_price', 0.0)),
            })
        return {
            'external_order_id': external_order_id,
            'customer_name': str(payload.get('customer_name', '')).strip(),
            'customer_phone': str(payload.get('customer_phone', '')).strip(),
            'customer_email': str(payload.get('customer_email', '')).strip(),
            'shipping_address': str(payload.get('shipping_address', '')).strip(),
            'order_date': self._parse_iso_datetime(payload.get('order_date'), external_order_id),
            'total_amount': float(payload.get('total_amount', 0.0)),
            'currency': str(payload.get('currency', 'VND')).strip(),
            'items': items,
        }

    @staticmethod
    def _parse_iso_datetime(raw, order_id: str):
        if not raw:
            return fields.Datetime.now()
        try:
            return datetime.fromisoformat(str(raw).replace('Z', '').strip()).strftime('%Y-%m-%d %H:%M:%S')
        except (TypeError, ValueError):
            _logger.warning('Order %s has invalid order_date %r, defaulting to now()', order_id, raw)
            return fields.Datetime.now()
