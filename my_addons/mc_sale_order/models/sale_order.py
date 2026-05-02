# -*- coding: utf-8 -*-
from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    mc_channel_id = fields.Many2one('mc.channel', string='Sales Channel', ondelete='restrict', index=True)
    mc_external_order_id = fields.Char(string='External Order ID', index=True, copy=False)
    mc_raw_order_id = fields.Many2one('mc.raw.order', string='Source Raw Order', copy=False, readonly=True, ondelete='set null')

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
            'name': 'Raw Order',
            'res_model': 'mc.raw.order',
            'view_mode': 'form',
            'res_id': self.mc_raw_order_id.id,
        }


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    mc_external_sku = fields.Char(string='External SKU', copy=False, readonly=True)
    mc_mapping_id = fields.Many2one('mc.product.mapping', string='SKU Mapping Used', copy=False, readonly=True, ondelete='set null')
