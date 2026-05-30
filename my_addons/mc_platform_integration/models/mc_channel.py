# -*- coding: utf-8 -*-
import json
import logging
from datetime import datetime
from typing import Any

from odoo import api, fields, models


_logger = logging.getLogger(__name__)


class McChannel(models.Model):
    _inherit = 'mc.channel'

    integration_enabled = fields.Boolean(string='Realtime Integration Enabled', default=True)
    middleware_channel_key = fields.Char(string='Middleware Channel Key', help='Platform key used by the external middleware, for example shopee or tiktok.')
    auto_parse_orders = fields.Boolean(string='Auto Parse Incoming Orders', default=True)
    auto_check_mapping = fields.Boolean(string='Auto Check SKU Mapping', default=True)
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
        duplicate = bool(raw_order)
        if not raw_order:
            raw_order = RawOrder.create({
                'channel_id': channel.id,
                'external_order_id': external_order_id,
                'raw_payload': json.dumps(clean_payload, ensure_ascii=False),
                'integration_event_id': integration_event_id,
                'normalized_at': normalized_at,
            })

        if channel.auto_parse_orders and raw_order.state in ('new', 'error'):
            raw_order.action_parse()

        mapping_result = {}
        if channel.auto_check_mapping:
            mapping_result = raw_order._check_product_mapping()

        now = fields.Datetime.now()
        channel.sudo().write({
            'last_realtime_received_at': now,
            'last_sync_at': now,
            'sync_status': 'success' if raw_order.state != 'error' else 'error',
        })

        status = 'duplicate' if duplicate else 'created'
        self.env['mc.sync.log']._log(
            'info' if raw_order.state != 'error' else 'error',
            f'Realtime order {external_order_id} {status}; state={raw_order.state}; mapping={mapping_result.get("status", "unchecked")}.',
            channel_id=channel.id,
            reference=external_order_id,
        )
        _logger.info('Realtime normalized order ingested: channel=%s external_order_id=%s status=%s', channel.code, external_order_id, status)

        return {
            'status': status,
            'channel': channel.name,
            'external_order_id': external_order_id,
            'raw_order_id': raw_order.id,
            'raw_order_state': raw_order.state,
            'mapping': mapping_result,
        }

    @staticmethod
    def _parse_external_datetime(raw):
        if not raw:
            return fields.Datetime.now()
        try:
            value = str(raw).replace('Z', '').strip()
            if '+' in value:
                value = value.split('+', 1)[0]
            return fields.Datetime.to_string(datetime.fromisoformat(value))
        except (TypeError, ValueError):
            return fields.Datetime.now()
