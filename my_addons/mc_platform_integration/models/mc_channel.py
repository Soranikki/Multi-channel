# -*- coding: utf-8 -*-
import json
import logging
from datetime import datetime, timezone
from typing import Any

from psycopg2 import IntegrityError

from odoo import api, fields, models


_logger = logging.getLogger(__name__)


class McChannel(models.Model):
    _inherit = 'mc.channel'

    integration_enabled = fields.Boolean(string='Realtime Integration Enabled', default=False)
    middleware_channel_key = fields.Char(string='Middleware Channel Key', help='Platform key used by the external middleware, for example shopee or tiktok.')
    auto_parse_orders = fields.Boolean(string='Auto Parse Incoming Orders', default=True)
    auto_check_mapping = fields.Boolean(string='Auto Check SKU Mapping', default=True)
    strict_stock_check = fields.Boolean(string='Strict Stock Check (Prevent Overselling)', default=True, help="If true, raw orders will error out and not create a Sale Order if the virtual available stock (minus buffer) is less than the requested quantity.")
    auto_process_orders = fields.Boolean(string='Auto Process Parsed Orders', default=True)
    auto_reconcile_orders = fields.Boolean(string='Auto Reconcile Order Status', default=True)
    last_realtime_received_at = fields.Datetime(string='Last Realtime Event At', readonly=True)

    @api.model
    def ingest_normalized_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Entry point used by the external WebSocket connector through XML-RPC.

        The payload must already be normalized by the middleware into the standard
        mc.raw.order JSON shape: external_order_id, customer fields, and items.
        """
        if not isinstance(payload, dict):
            raise ValueError('Normalized payload must be a JSON object.')

        channel_code = str(payload.get('channel_code') or payload.get('source_platform') or '').strip().lower()
        external_order_id = str(payload.get('external_order_id') or '').strip()
        if not channel_code:
            raise ValueError('Normalized payload is missing channel_code.')
        if not external_order_id:
            raise ValueError('Normalized payload is missing external_order_id.')

        channel = self.search([('code', '=', channel_code)], limit=1)
        if not channel:
            raise ValueError(f'No mc.channel found for channel_code {channel_code!r}.')
        if not channel.integration_enabled:
            return {'status': 'ignored', 'reason': 'integration_disabled', 'channel': channel.name}

        clean_payload = dict(payload)
        integration_event_id = clean_payload.pop('_integration_event_id', False)
        normalized_at = self._parse_external_datetime(clean_payload.pop('_normalized_at', False))
        clean_payload.pop('_source_event_id', None)

        RawOrder = self.env['mc.raw.order'].sudo()
        raw_order = RawOrder.search([
            ('channel_id', '=', channel.id),
            ('external_order_id', '=', external_order_id),
        ], limit=1)
        ingest_status = 'created'
        if not raw_order:
            integration_vals = RawOrder._prepare_integration_vals_from_payload(
                clean_payload,
                integration_event_id=integration_event_id,
                normalized_at=normalized_at,
            )
            try:
                raw_order = RawOrder.create({
                    'channel_id': channel.id,
                    'external_order_id': external_order_id,
                    'raw_payload': json.dumps(clean_payload, ensure_ascii=False),
                    **integration_vals,
                })
            except IntegrityError:
                self.env.cr.rollback()
                raw_order = RawOrder.search([
                    ('channel_id', '=', channel.id),
                    ('external_order_id', '=', external_order_id),
                ], limit=1)
                if not raw_order:
                    raise
                sync_result = raw_order._apply_integration_payload(
                    clean_payload,
                    integration_event_id=integration_event_id,
                    normalized_at=normalized_at,
                )
                if sync_result.get('stale'):
                    ingest_status = 'stale'
                else:
                    ingest_status = 'updated'
        else:
            sync_result = raw_order._apply_integration_payload(
                clean_payload,
                integration_event_id=integration_event_id,
                normalized_at=normalized_at,
            )
            if sync_result.get('stale'):
                ingest_status = 'stale'
            else:
                ingest_status = 'updated'

        if channel.auto_parse_orders and raw_order.state in ('new', 'error'):
            raw_order.action_parse()

        mapping_result = {}
        if channel.auto_check_mapping:
            mapping_result = raw_order._check_product_mapping()

        if channel.auto_process_orders and raw_order.state == 'parsed' and raw_order.mapping_status in ('mapped', 'unchecked'):
            raw_order.action_process()

        reconcile_result = {}
        if channel.auto_reconcile_orders:
            reconcile_result = raw_order._reconcile_with_sale_order()

        now = fields.Datetime.now()
        channel.sudo().write({
            'last_realtime_received_at': now,
            'last_sync_at': now,
            'sync_status': 'error' if raw_order.state == 'error' else 'success',
        })

        self.env['mc.sync.log']._log(
            'error' if raw_order.state == 'error' else ('warning' if ingest_status == 'stale' else 'info'),
            f'Realtime order {external_order_id} {ingest_status}; state={raw_order.state}; mapping={mapping_result.get("status", "unchecked")}; reconcile={reconcile_result.get("state", "unchecked")}.',
            channel_id=channel.id,
            reference=external_order_id,
        )
        _logger.info('Realtime normalized order ingested: channel=%s external_order_id=%s status=%s', channel.code, external_order_id, ingest_status)

        return {
            'status': ingest_status,
            'channel': channel.name,
            'external_order_id': external_order_id,
            'raw_order_id': raw_order.id,
            'raw_order_state': raw_order.state,
            'mapping': mapping_result,
            'reconcile': reconcile_result,
        }

    @api.model
    def cron_process_incoming_orders(self, limit: int = 200) -> None:
        channels = self.sudo().search([
            ('integration_enabled', '=', True),
            ('auto_process_orders', '=', True),
        ])
        if not channels:
            return

        raw_orders = self.env['mc.raw.order'].sudo().search([
            ('channel_id', 'in', channels.ids),
            ('state', '=', 'parsed'),
            ('mapping_status', 'in', ('mapped', 'unchecked')),
        ], order='parsed_at asc, received_at asc, id asc', limit=limit)
        for raw_order in raw_orders:
            try:
                with self.env.cr.savepoint():
                    raw_order.action_process()
                    if raw_order.channel_id.auto_reconcile_orders:
                        raw_order._reconcile_with_sale_order()
            except Exception as exc:
                self.env['mc.sync.log']._log(
                    'error',
                    f'Cron order processing failed for {raw_order.external_order_id}: {exc}',
                    channel_id=raw_order.channel_id.id,
                    reference=raw_order.external_order_id,
                )

    @api.model
    def cron_reconcile_order_payment_status(self, limit: int = 200) -> None:
        channels = self.sudo().search([
            ('integration_enabled', '=', True),
            ('auto_reconcile_orders', '=', True),
        ])
        if not channels:
            return

        raw_orders = self.env['mc.raw.order'].sudo().search([
            ('channel_id', 'in', channels.ids),
            ('state', 'in', ('parsed', 'processed')),
        ], order='received_at asc, id asc', limit=limit)
        for raw_order in raw_orders:
            try:
                with self.env.cr.savepoint():
                    raw_order._reconcile_with_sale_order()
            except Exception as exc:
                self.env['mc.sync.log']._log(
                    'error',
                    f'Cron reconciliation failed for {raw_order.external_order_id}: {exc}',
                    channel_id=raw_order.channel_id.id,
                    reference=raw_order.external_order_id,
                )

    @staticmethod
    def _parse_external_datetime(raw):
        if not raw:
            return False
        try:
            value = str(raw).strip().replace('Z', '+00:00')
            dt_value = datetime.fromisoformat(value)
            if dt_value.tzinfo:
                dt_value = dt_value.astimezone(timezone.utc).replace(tzinfo=None)
            return dt_value
        except (TypeError, ValueError):
            return False
