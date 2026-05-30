# -*- coding: utf-8 -*-
import json

from odoo import fields, models


class McRawOrder(models.Model):
    _inherit = 'mc.raw.order'

    integration_event_id = fields.Char(string='Integration Event ID', readonly=True, copy=False, index=True)
    normalized_at = fields.Datetime(string='Normalized At', readonly=True, copy=False)
    mapping_status = fields.Selection(
        selection=[
            ('unchecked', 'Unchecked'),
            ('mapped', 'Mapped'),
            ('partial', 'Partially Mapped'),
            ('unmapped', 'Unmapped'),
        ],
        string='SKU Mapping Status',
        default='unchecked',
        readonly=True,
        copy=False,
        index=True,
    )
    mapped_product_count = fields.Integer(string='Mapped Product Count', readonly=True, copy=False)
    unmapped_skus = fields.Text(string='Unmapped SKUs', readonly=True, copy=False)

    def _check_product_mapping(self) -> dict:
        self.ensure_one()
        if self.state != 'parsed' or not self.parsed_items_json:
            self.write({
                'mapping_status': 'unchecked',
                'mapped_product_count': 0,
                'unmapped_skus': False,
            })
            return {'status': 'unchecked', 'mapped_count': 0, 'unmapped_skus': []}

        items = json.loads(self.parsed_items_json or '[]')
        skus = sorted({str(item.get('external_sku') or '').strip() for item in items if item.get('external_sku')})
        if not skus:
            self.write({
                'mapping_status': 'unmapped',
                'mapped_product_count': 0,
                'unmapped_skus': False,
            })
            return {'status': 'unmapped', 'mapped_count': 0, 'unmapped_skus': []}

        mappings = self.env['mc.product.mapping'].search([
            ('channel_id', '=', self.channel_id.id),
            ('external_sku', 'in', skus),
            ('is_active', '=', True),
        ])
        mapped_skus = set(mappings.mapped('external_sku'))
        unmapped = [sku for sku in skus if sku not in mapped_skus]
        if not unmapped:
            status = 'mapped'
        elif mapped_skus:
            status = 'partial'
        else:
            status = 'unmapped'

        self.write({
            'mapping_status': status,
            'mapped_product_count': len(mapped_skus),
            'unmapped_skus': '\n'.join(unmapped) if unmapped else False,
        })
        return {'status': status, 'mapped_count': len(mapped_skus), 'unmapped_skus': unmapped}
