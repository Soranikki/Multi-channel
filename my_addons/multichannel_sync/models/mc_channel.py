# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class McChannel(models.Model):
    """
    Represents a sales channel (e.g. Shopee, TikTok Shop).
    Each channel has a unique code that the Integration Service uses to route
    normalized payloads into the correct bucket.

    The Integration Service URL is stored in ir.config_parameter
    (key: multichannel_sync.integration_service_url) — not hardcoded here.
    """
    _name = 'mc.channel'
    _description = 'Sales Channel'
    _order = 'sequence, name'

    name = fields.Char(
        string='Channel Name',
        required=True,
    )
    code = fields.Selection(
        selection=[
            ('shopee', 'Shopee'),
            ('tiktok', 'TikTok Shop'),
            ('manual', 'Manual Entry'),
        ],
        string='Channel Code',
        required=True,
    )
    active = fields.Boolean(
        default=True,
    )
    sequence = fields.Integer(
        default=10,
    )
    description = fields.Text(
        string='Description',
    )
    last_sync_at = fields.Datetime(
        string='Last Sync At',
        readonly=True,
    )
    last_sync_duration = fields.Float(
        string='Last Sync Duration (s)',
        digits=(8, 2),
        readonly=True,
        help='How long the last pipeline run took, in seconds.',
    )
    sync_status = fields.Selection(
        selection=[
            ('idle',    'Idle'),
            ('syncing', 'Syncing'),
            ('success', 'Success'),
            ('error',   'Error'),
        ],
        string='Sync Status',
        default='idle',
        readonly=True,
    )
    color = fields.Integer(
        string='Color',
        default=0,
    )

    # ── Stat counters (computed on-the-fly, not stored) ──────────────────────

    raw_order_count = fields.Integer(
        string='Raw Orders',
        compute='_compute_raw_order_count',
    )
    order_count = fields.Integer(
        string='Orders',
        compute='_compute_order_count',
    )
    mapping_count = fields.Integer(
        string='Mappings',
        compute='_compute_mapping_count',
    )

    _sql_constraints = [
        ('unique_code', 'UNIQUE(code)', 'A channel with this code already exists.'),
    ]

    # ── Computed helpers ──────────────────────────────────────────────────────

    def _compute_raw_order_count(self) -> None:
        for channel in self:
            channel.raw_order_count = self.env['mc.raw.order'].search_count(
                [('channel_id', '=', channel.id)]
            ) if 'mc.raw.order' in self.env else 0

    def _compute_order_count(self) -> None:
        for channel in self:
            channel.order_count = self.env['mc.order'].search_count(
                [('channel_id', '=', channel.id)]
            ) if 'mc.order' in self.env else 0

    def _compute_mapping_count(self) -> None:
        for channel in self:
            channel.mapping_count = self.env['mc.product.mapping'].search_count(
                [('channel_id', '=', channel.id)]
            )

    # ── Button actions ────────────────────────────────────────────────────────

    def action_open_mappings(self):
        """Open product mappings filtered to this channel."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Mappings — {self.name}',
            'res_model': 'mc.product.mapping',
            'view_mode': 'tree,form',
            'domain': [('channel_id', '=', self.id)],
            'context': {'default_channel_id': self.id},
        }

    def action_run_pipeline(self) -> dict:
        """
        One-click pipeline for this channel:
            1. Set sync_status = 'syncing' immediately for UI feedback.
            2. Parse all raw orders in state 'new'.
            3. Process all raw orders now in state 'parsed'.
            4. Update last_sync_at, last_sync_duration, sync_status.

        Returns a client notification summarising detailed results:
            - how many were new, how many parsed successfully
            - how many were processed into orders, how many errored
        """
        import time
        self.ensure_one()

        # ── Signal the UI that the pipeline is running ────────────────────
        self.write({'sync_status': 'syncing'})
        self.env.cr.commit()  # flush to DB so the UI reflects 'syncing'

        start_time = time.time()
        RawOrder = self.env['mc.raw.order']

        # ── Step 1: parse all new raw orders ─────────────────────────────
        new_orders = RawOrder.search([
            ('channel_id', '=', self.id),
            ('state', '=', 'new'),
        ])
        parse_ok = 0
        parse_err = 0
        for raw in new_orders:
            try:
                raw._parse_raw_order()
                if raw.state == 'parsed':
                    parse_ok += 1
                else:
                    parse_err += 1
            except Exception as exc:
                parse_err += 1
                _logger.warning('Pipeline parse error id=%s: %s', raw.id, exc)

        # ── Step 2: process all parsed raw orders ─────────────────────────
        parsed_orders = RawOrder.search([
            ('channel_id', '=', self.id),
            ('state', '=', 'parsed'),
        ])
        process_ok = 0
        process_err = 0
        for raw in parsed_orders:
            try:
                raw._process_raw_order()
                if raw.state == 'processed':
                    process_ok += 1
                else:
                    process_err += 1
            except Exception as exc:
                process_err += 1
                _logger.warning('Pipeline process error id=%s: %s', raw.id, exc)

        # ── Update channel sync metadata ──────────────────────────────────
        elapsed = round(time.time() - start_time, 2)
        total_errors = parse_err + process_err
        self.write({
            'last_sync_at':       fields.Datetime.now(),
            'last_sync_duration': elapsed,
            'sync_status':        'error' if total_errors and not process_ok else 'success',
        })

        # ── Build result notification ─────────────────────────────────────
        lines = []
        if new_orders:
            lines.append(f'Parsed: {parse_ok} ok, {parse_err} error(s)')
        lines.append(f'Orders created: {process_ok}')
        if process_err:
            lines.append(f'Processing errors: {process_err} — check Error Log.')
        if not new_orders and not parsed_orders:
            lines.append('No new or pending raw orders to process.')
        msg = ' | '.join(lines)

        notif_type = 'warning' if total_errors else 'success'
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': f'Pipeline — {self.name} ({elapsed}s)',
                'message': msg,
                'type': notif_type,
                'sticky': total_errors > 0,
            },
        }
