# -*- coding: utf-8 -*-
from odoo import api, fields, models


class McProductMapping(models.Model):
    _name = 'mc.product.mapping'
    _description = 'Product Channel Mapping'
    _order = 'channel_id, external_sku'

    channel_id = fields.Many2one('mc.channel', string='Channel', required=True, ondelete='cascade', index=True)
    product_id = fields.Many2one('product.product', string='Odoo Product Variant', required=True, ondelete='cascade', index=True)
    external_sku = fields.Char(string='External SKU', required=True, index=True)
    external_name = fields.Char(string='External Product Name')
    is_active = fields.Boolean(default=True)

    internal_sku = fields.Char(related='product_id.default_code', string='Internal Reference', readonly=True)
    product_name = fields.Char(related='product_id.display_name', string='Product', readonly=True)
    channel_code = fields.Char(related='channel_id.code', string='Channel Code', readonly=True)
    qty_available = fields.Float(related='product_id.qty_available', string='On Hand', readonly=True)
    virtual_available = fields.Float(related='product_id.virtual_available', string='Forecasted', readonly=True)
    mc_buffer_qty = fields.Float(related='product_id.mc_buffer_qty', string='Buffer Qty', readonly=True)
    synced_qty = fields.Float(
        string='Synced Quantity',
        compute='_compute_synced_qty',
        store=False
    )
    last_synced_qty = fields.Float(string='Last Synced Qty', default=-1.0, copy=False)
    mc_is_low_stock = fields.Boolean(related='product_id.mc_is_low_stock', string='Low Stock', readonly=True)

    @api.depends('virtual_available', 'mc_buffer_qty')
    def _compute_synced_qty(self):
        for mapping in self:
            safe_qty = mapping.virtual_available - mapping.mc_buffer_qty
            mapping.synced_qty = max(0.0, safe_qty)

    @api.model
    def _cron_queue_stock_updates(self, limit=200):
        # find mappings where synced_qty changed
        # synced_qty is not stored so we can't search on it directly easily
        # Instead, search active mappings and compare memory synced_qty vs last_synced_qty
        mappings = self.search([('is_active', '=', True)], limit=limit)
        
        updates_created = 0
        Queue = self.env['mc.stock.sync.queue']
        
        for mapping in mappings:
            current_qty = mapping.synced_qty
            if current_qty != mapping.last_synced_qty:
                # create queue item
                Queue.create({
                    'channel_id': mapping.channel_id.id,
                    'mapping_id': mapping.id,
                    'qty_to_sync': current_qty,
                    'state': 'pending'
                })
                # update last_synced_qty to prevent duplicate queuing
                mapping.last_synced_qty = current_qty
                updates_created += 1
                
        if updates_created > 0:
            import logging
            logging.getLogger(__name__).info('Queued %d stock sync updates.', updates_created)

    _sql_constraints = [
        (
            'unique_channel_external_sku',
            'UNIQUE(channel_id, external_sku)',
            'This external SKU is already mapped to a product on this channel.',
        ),
    ]
