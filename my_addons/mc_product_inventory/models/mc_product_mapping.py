# -*- coding: utf-8 -*-
from odoo import fields, models


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
    channel_code = fields.Selection(related='channel_id.code', readonly=True)
    qty_available = fields.Float(related='product_id.qty_available', string='On Hand', readonly=True)
    virtual_available = fields.Float(related='product_id.virtual_available', string='Forecasted', readonly=True)
    mc_is_low_stock = fields.Boolean(related='product_id.mc_is_low_stock', string='Low Stock', readonly=True)

    _sql_constraints = [
        (
            'unique_channel_external_sku',
            'UNIQUE(channel_id, external_sku)',
            'This external SKU is already mapped to a product on this channel.',
        ),
    ]
