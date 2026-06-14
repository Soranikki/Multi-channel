import json
import logging
from datetime import datetime, timezone
from typing import Any

import requests
from psycopg2 import IntegrityError

from odoo import api, fields, models
from odoo.exceptions import UserError


_logger = logging.getLogger(__name__)


class McChannel(models.Model):
    _inherit = 'mc.channel'

    integration_enabled = fields.Boolean(string='Realtime Integration Enabled', default=False)
    middleware_channel_key = fields.Char(string='Middleware Channel Key', help='Platform key used by the external middleware, for example shopee or tiktok.')
    strict_stock_check = fields.Boolean(string='Strict Stock Check (Prevent Overselling)', default=True, help="If true, raw orders will error out and not create a Sale Order if the virtual available stock (minus buffer) is less than the requested quantity.")
    last_realtime_received_at = fields.Datetime(string='Last Realtime Event At', readonly=True)
    middleware_config_json = fields.Text(
        string='Archived Middleware Config (JSON)',
        help='Snapshot of the middleware channel config, saved when the channel is hard-deleted for later restoration.',
        readonly=True, copy=False,
    )

    def _get_connector_base_url(self):
        Service = self.env['mc.integration.service']
        url = Service._get_service_url('odoo_ws_connector')
        if not url:
            _logger.warning("No odoo_ws_connector URL configured in Integration Services.")
        return url

    def _call_connector_api(self, method, path, json_body=None):
        base_url = self._get_connector_base_url()
        if not base_url:
            return None
        url = f"{base_url}{path}"
        try:
            if method == 'GET':
                resp = requests.get(url, timeout=5.0)
            elif method == 'POST':
                resp = requests.post(url, json=json_body or {}, timeout=5.0)
            else:
                return None
            if resp.status_code >= 500:
                _logger.warning("Connector API %s returned %s: %s", url, resp.status_code, resp.text)
                return None
            return resp.json() if resp.content else {}
        except Exception as exc:
            _logger.warning("Cannot reach odoo_ws_connector at %s: %s", url, exc)
            return None

    def _has_dependent_orders(self):
        self.ensure_one()
        raw_count = self.env['mc.raw.order'].search_count([('channel_id', '=', self.id)])
        sale_count = self.env['sale.order'].search_count([('mc_channel_id', '=', self.id)])
        return raw_count > 0 or sale_count > 0

    def _archive_cleanup(self):
        self.ensure_one()
        result = self._call_connector_api('POST', f'/api/channel/{self.code}/archive')
        if result is None:
            return None  # API call failed (connector unreachable)
        # API succeeded — snapshot may be None if already archived, that's fine
        return result.get('snapshot') or {}

    def _check_connectivity(self):
        result = self._call_connector_api('GET', '/health')
        if result and result.get('connected_to_middleware'):
            return True
        return False

    def write(self, vals):
        if 'active' in vals:
            if vals.get('active') is False:
                vals['integration_enabled'] = False
                vals['sync_status'] = 'idle'
            elif vals.get('active') is True:
                vals['integration_enabled'] = True
                vals['sync_status'] = 'success' if self._check_connectivity() else 'error'
                vals['last_sync_at'] = fields.Datetime.now()
        return super().write(vals)

    def unlink(self):
        for channel in self:
            if channel._has_dependent_orders():
                raise UserError(
                    "Cannot delete channel '%s' because it has linked orders. "
                    "Archive it instead." % channel.name
                )
            channel._archive_cleanup()
        return super().unlink()

    @api.model
    def ingest_normalized_order(self, payload: dict[str, Any]) -> dict[str, Any]:
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

        # Pipeline: parse → mapping → process → reconcile (mandatory)
        if raw_order.state in ('new', 'error'):
            raw_order.action_parse()

        mapping_result = raw_order._check_product_mapping()

        if raw_order.state == 'parsed' and raw_order.mapping_status in ('mapped', 'unchecked'):
            raw_order.action_process()

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
