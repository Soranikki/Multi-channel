# -*- coding: utf-8 -*-
import logging

from odoo import fields, models
from odoo.exceptions import UserError


_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    MC_ORDER_STATUS_SELECTION = [
        ('unknown', 'Không rõ'),
        ('pending', 'Chờ xử lý'),
        ('confirmed', 'Đã xác nhận'),
        ('shipping', 'Đang giao'),
        ('delivered', 'Đã giao'),
        ('cancelled', 'Đã hủy'),
        ('refunded', 'Đã hoàn tiền'),
    ]
    MC_PAYMENT_STATUS_SELECTION = [
        ('unknown', 'Không rõ'),
        ('pending', 'Chờ xử lý'),
        ('paid', 'Đã thanh toán'),
        ('failed', 'Thất bại'),
        ('refunded', 'Đã hoàn tiền'),
    ]

    mc_channel_id = fields.Many2one('mc.channel', string="Kênh bán hàng", ondelete='restrict', index=True)
    mc_external_order_id = fields.Char(string="Mã đơn hàng (Sàn)", index=True, copy=False)
    mc_raw_order_id = fields.Many2one('mc.raw.order', string="Đơn hàng gốc nguồn", copy=False, readonly=True, ondelete='set null')
    mc_order_status = fields.Selection(selection=MC_ORDER_STATUS_SELECTION, string="Trạng thái đơn hàng (Kênh)", default='unknown', copy=False, index=True)
    mc_payment_status = fields.Selection(selection=MC_PAYMENT_STATUS_SELECTION, string="Trạng thái thanh toán (Kênh)", default='unknown', copy=False, index=True)
    mc_last_channel_status_at = fields.Datetime(string="Trạng thái kênh cập nhật lúc", copy=False, index=True)

    _sql_constraints = [
        (
            'unique_mc_channel_external_order',
            'UNIQUE(mc_channel_id, mc_external_order_id)',
            'An external order with this ID already exists for this channel.',
        ),
    ]

    def action_open_mc_raw_order(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Đơn hàng gốc',
            'res_model': 'mc.raw.order',
            'view_mode': 'form',
            'res_id': self.mc_raw_order_id.id,
        }

    def _mc_apply_channel_statuses(self, order_status: str, payment_status: str, status_updated_at=False) -> dict:
        self.ensure_one()
        if self.mc_last_channel_status_at and status_updated_at and status_updated_at < self.mc_last_channel_status_at:
            return {'stale': True, 'applied': False}

        write_vals = {
            'mc_order_status': order_status or 'unknown',
            'mc_payment_status': payment_status or 'unknown',
        }
        if status_updated_at:
            write_vals['mc_last_channel_status_at'] = status_updated_at
        self.write(write_vals)

        if order_status in ('cancelled', 'refunded'):
            if self.state != 'cancel':
                try:
                    self.action_cancel()
                except UserError as exc:
                    _logger.warning('Unable to cancel sale order %s during channel sync: %s', self.name, exc)
        elif order_status in ('confirmed', 'shipping', 'delivered'):
            if self.state in ('draft', 'sent'):
                self.action_confirm()

        return {'stale': False, 'applied': True}

    def _mc_get_canonical_order_status(self) -> str:
        self.ensure_one()
        if self.state == 'cancel':
            return 'cancelled'
        if self.state in ('draft', 'sent'):
            return 'pending'
        if self.state in ('sale', 'done'):
            if self.picking_ids:
                if all(picking.state == 'done' for picking in self.picking_ids):
                    return 'delivered'
                if any(picking.state not in ('done', 'cancel') for picking in self.picking_ids):
                    return 'shipping'
            return 'confirmed'
        return 'unknown'

    def _mc_get_canonical_payment_status(self) -> str:
        self.ensure_one()
        if not self.invoice_ids:
            return self.mc_payment_status or 'pending'

        active_invoices = self.invoice_ids.filtered(lambda inv: inv.state != 'cancel')
        if not active_invoices:
            return self.mc_payment_status or 'pending'

        payment_states = set(active_invoices.mapped('payment_state'))
        move_types = set(active_invoices.mapped('move_type'))
        if any(move_type in ('out_refund', 'in_refund') for move_type in move_types) or 'reversed' in payment_states:
            return 'refunded'
        if payment_states and payment_states.issubset({'paid'}):
            return 'paid'
        if any(state in {'in_payment', 'partial', 'not_paid'} for state in payment_states):
            return 'pending'
        return 'unknown'


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    mc_external_sku = fields.Char(string="SKU (Sàn)", copy=False, readonly=True)
    mc_mapping_id = fields.Many2one('mc.product.mapping', string="Mapping SKU đã dùng", copy=False, readonly=True, ondelete='set null')

    def _action_confirm(self):
        # Override to prevent date_order from being overwritten for historical multichannel orders
        res = super()._action_confirm()
        for order in self:
            if order.mc_raw_order_id and order.mc_raw_order_id.parsed_order_date:
                # Restore original parsed date
                order.write({'date_order': order.mc_raw_order_id.parsed_order_date})
        return res
