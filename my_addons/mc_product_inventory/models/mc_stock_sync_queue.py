# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models


class McStockSyncQueue(models.Model):
    _name = 'mc.stock.sync.queue'
    _description = 'Multichannel Stock Sync Queue'
    _order = 'create_date desc'

    channel_id = fields.Many2one('mc.channel', string='Channel', required=True, ondelete='cascade', index=True)
    mapping_id = fields.Many2one('mc.product.mapping', string='Product Mapping', required=True, ondelete='cascade', index=True)
    external_sku = fields.Char(related='mapping_id.external_sku', store=True, readonly=True)
    qty_to_sync = fields.Float(string='Qty to Sync', required=True)
    state = fields.Selection([
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('done', 'Done'),
        ('error', 'Error')
    ], default='pending', required=True, index=True)
    error_message = fields.Text(readonly=True)
    attempt_count = fields.Integer(default=0, readonly=True)
    last_attempt_at = fields.Datetime(readonly=True)
    next_retry_at = fields.Datetime(readonly=True, index=True)

    @api.model
    def claim_pending_for_connector(self, limit=50):
        now = fields.Datetime.now()
        records = self.search([
            ('state', 'in', ['pending', 'error']),
            '|',
            ('next_retry_at', '=', False),
            ('next_retry_at', '<=', now),
        ], order='create_date asc', limit=limit)
        if not records:
            return []
        records.write({
            'state': 'processing',
            'last_attempt_at': now,
        })
        return records._to_connector_payload()

    def mark_done_from_connector(self):
        self.write({
            'state': 'done',
            'error_message': False,
            'next_retry_at': False,
        })
        return True

    def mark_failed_from_connector(self, error_message):
        now = fields.Datetime.now()
        for record in self:
            attempt_count = record.attempt_count + 1
            delay_minutes = min(60, 2 ** min(attempt_count - 1, 5))
            record.write({
                'state': 'error',
                'attempt_count': attempt_count,
                'error_message': error_message,
                'last_attempt_at': now,
                'next_retry_at': now + timedelta(minutes=delay_minutes),
            })
        return True

    def _to_connector_payload(self):
        return [{
            'id': record.id,
            'external_sku': record.external_sku,
            'qty_to_sync': record.qty_to_sync,
            'channel_id': record.channel_id.id,
            'channel_code': record.channel_id.code,
            'attempt_count': record.attempt_count,
        } for record in self]
