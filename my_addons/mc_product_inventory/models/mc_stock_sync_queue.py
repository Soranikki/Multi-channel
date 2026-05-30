# -*- coding: utf-8 -*-
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
