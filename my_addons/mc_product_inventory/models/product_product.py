# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductProduct(models.Model):
    _inherit = 'product.product'

    mc_low_stock_threshold = fields.Float(
        string="Ngưỡng cảnh báo Tồn kho MC",
        digits='Product Unit of Measure',
        default=5.0,
        help='Multichannel warning threshold. Compared with Odoo forecasted quantity.',
    )
    mc_buffer_qty = fields.Float(
        string='MC Buffer Quantity',
        digits='Product Unit of Measure',
        default=0.0,
        help='Quantity to keep in reserve (safety stock) from channel syncs.',
    )
    mc_is_low_stock = fields.Boolean(
        string="Sắp hết hàng MC",
        compute='_compute_mc_is_low_stock',
        search='_search_mc_is_low_stock',
    )
    mc_mapping_count = fields.Integer(string='Channel Mappings', compute='_compute_mc_mapping_count')

    def _compute_mc_is_low_stock(self) -> None:
        for product in self:
            product.mc_is_low_stock = product.virtual_available <= product.mc_low_stock_threshold

    def _search_mc_is_low_stock(self, operator, value):
        # virtual_available is a computed stock field, not a database column.
        # search_read keeps the search correct while avoiding full recordset filtering.
        products = self.search_read([], ['virtual_available', 'mc_low_stock_threshold'])
        low_stock_ids = [
            product['id']
            for product in products
            if product['virtual_available'] <= product['mc_low_stock_threshold']
        ]
        if (operator, bool(value)) in [('=', True), ('!=', False)]:
            return [('id', 'in', low_stock_ids)]
        return [('id', 'not in', low_stock_ids)]

    def _compute_mc_mapping_count(self) -> None:
        counts = self.env['mc.product.mapping'].read_group(
            [('product_id', 'in', self.ids)], ['product_id'], ['product_id']
        )
        count_by_product = {row['product_id'][0]: row['product_id_count'] for row in counts}
        for product in self:
            product.mc_mapping_count = count_by_product.get(product.id, 0)

    def action_open_mc_mappings(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Channel Mappings - {self.display_name}',
            'res_model': 'mc.product.mapping',
            'view_mode': 'tree,form',
            'domain': [('product_id', '=', self.id)],
            'context': {'default_product_id': self.id},
        }
