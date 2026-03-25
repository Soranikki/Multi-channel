# -*- coding: utf-8 -*-
from odoo import api, fields, models


class McProductMapping(models.Model):
    """
    Maps an external platform SKU (per channel) to an internal mc.product.
    The unique constraint on (channel_id, external_sku) ensures each external
    SKU resolves to exactly one internal product per channel — preventing
    ambiguous mapping during order processing.
    """
    _name = 'mc.product.mapping'
    _description = 'Product Channel Mapping'
    _order = 'channel_id, external_sku'

    channel_id = fields.Many2one(
        comodel_name='mc.channel',
        string='Channel',
        required=True,
        ondelete='cascade',
        index=True,
    )
    product_id = fields.Many2one(
        comodel_name='mc.product',
        string='Internal Product',
        required=True,
        ondelete='cascade',
        index=True,
    )
    external_sku = fields.Char(
        string='External SKU',
        required=True,
        help='The SKU identifier as it appears in the channel platform (Shopee/TikTok).',
    )
    external_name = fields.Char(
        string='External Product Name',
        help='Product name as shown on the external platform (for reference only).',
    )
    is_active = fields.Boolean(
        string='Active',
        default=True,
        help='Inactive mappings are skipped during pipeline processing.',
    )

    # ── Convenience computed fields ───────────────────────────────────────────

    internal_sku = fields.Char(
        string='Internal SKU',
        related='product_id.internal_sku',
        readonly=True,
    )
    product_name = fields.Char(
        string='Internal Product Name',
        related='product_id.name',
        readonly=True,
    )
    channel_code = fields.Selection(
        string='Channel Code',
        related='channel_id.code',
        readonly=True,
    )

    _sql_constraints = [
        (
            'unique_channel_external_sku',
            'UNIQUE(channel_id, external_sku)',
            'This external SKU is already mapped to a product on this channel.',
        ),
    ]
