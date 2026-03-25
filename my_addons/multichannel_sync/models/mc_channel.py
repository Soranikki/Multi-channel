# -*- coding: utf-8 -*-
from odoo import api, fields, models


class McChannel(models.Model):
    """
    Represents a sales channel (e.g. Shopee, TikTok Shop).
    Each channel has a unique code that drives parser dispatch in the pipeline.
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
    sync_status = fields.Selection(
        selection=[
            ('idle', 'Idle'),
            ('syncing', 'Syncing'),
            ('success', 'Success'),
            ('error', 'Error'),
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
            1. Parse all raw orders in state 'new'.
            2. Process all raw orders now in state 'parsed'.

        Returns a client notification summarising results.
        """
        self.ensure_one()
        RawOrder = self.env['mc.raw.order']

        # Step 1: parse all new raw orders for this channel
        new_orders = RawOrder.search([
            ('channel_id', '=', self.id),
            ('state', '=', 'new'),
        ])
        for raw in new_orders:
            raw._parse_raw_order()

        # Step 2: process all parsed raw orders for this channel
        parsed_orders = RawOrder.search([
            ('channel_id', '=', self.id),
            ('state', '=', 'parsed'),
        ])
        created = 0
        errors = 0
        for raw in parsed_orders:
            try:
                raw._process_raw_order()
                created += 1
            except Exception:
                errors += 1

        # Update channel sync metadata
        self.write({
            'last_sync_at': fields.Datetime.now(),
            'sync_status':  'error' if (errors and not created) else 'success',
        })

        msg = f'Pipeline complete: {created} order(s) created'
        if errors:
            msg += f', {errors} error(s). Check the Error Log.'
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Pipeline Complete',
                'message': msg,
                'type': 'warning' if errors else 'success',
                'sticky': errors > 0,
            },
        }
