# -*- coding: utf-8 -*-
"""
mc.analysis.report — SQL view for multichannel analytics.

Design:
    _auto = False → Odoo does NOT create a table; instead we create a
    PostgreSQL VIEW via _auto_init(). This is the standard Odoo pattern
    for read-only analytical models (e.g. sale.report, mrp.report.*).

SQL strategy:
    - JOIN mc_order → mc_order_line → mc_product → mc_channel
    - Only include orders in state != 'cancelled' for revenue figures
    - Avoid row explosion: one row per order line (qty, revenue at line level)
    - Deterministic: no random ordering, no implicit assumptions on join
    - No company_id in custom models — single-company thesis setup.
      Add res_company join here if multi-company is needed in future.

Measures:
    - revenue      = subtotal (line level, after discount)
    - quantity     = line quantity
    - order_count  = count distinct orders (use count_distinct with groupby)
"""
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class McAnalysisReport(models.Model):
    """
    Analytics report model reading from normalized mc.order + mc.order.line data.
    This is a SQL view — records are never created or written directly.
    """
    _name = 'mc.analysis.report'
    _description = 'Multichannel Sales Analysis'
    _auto = False          # Do not create a table — we provide the SQL view
    _rec_name = 'order_name'
    _order = 'order_date desc'

    # ── Dimension fields ──────────────────────────────────────────────────────

    order_id = fields.Many2one(
        comodel_name='mc.order',
        string='Order',
        readonly=True,
    )
    order_name = fields.Char(
        string='Order Reference',
        readonly=True,
    )
    channel_id = fields.Many2one(
        comodel_name='mc.channel',
        string='Channel',
        readonly=True,
    )
    channel_code = fields.Selection(
        selection=[
            ('shopee', 'Shopee'),
            ('tiktok', 'TikTok Shop'),
            ('manual', 'Manual Entry'),
        ],
        string='Channel Code',
        readonly=True,
    )
    product_id = fields.Many2one(
        comodel_name='mc.product',
        string='Product',
        readonly=True,
    )
    product_name = fields.Char(
        string='Product Name',
        readonly=True,
    )
    internal_sku = fields.Char(
        string='Internal SKU',
        readonly=True,
    )
    category = fields.Char(
        string='Category',
        readonly=True,
    )
    order_date = fields.Datetime(
        string='Order Date',
        readonly=True,
    )
    state = fields.Selection(
        selection=[
            ('draft',     'Draft'),
            ('confirmed', 'Confirmed'),
            ('done',      'Done'),
            ('cancelled', 'Cancelled'),
        ],
        string='Order State',
        readonly=True,
    )

    # ── Measure fields ────────────────────────────────────────────────────────

    quantity = fields.Float(
        string='Quantity',
        digits=(12, 3),
        readonly=True,
    )
    unit_price = fields.Float(
        string='Unit Price',
        digits=(12, 2),
        readonly=True,
    )
    revenue = fields.Float(
        string='Revenue',
        digits=(12, 2),
        readonly=True,
        help='Line subtotal (quantity × unit_price × (1 - discount/100)).',
    )

    # ── View definition ───────────────────────────────────────────────────────

    def init(self) -> None:
        """
        Create (or replace) the mc_analysis_report PostgreSQL view.

        Called automatically by Odoo during module install/update because
        _auto = False. Using CREATE OR REPLACE VIEW makes this idempotent.

        SQL joins:
            mc_order        o   (main order, filters: state != 'cancelled')
            mc_order_line   l   (line items)
            mc_product      p   (internal product)
            mc_channel      c   (sales channel)
        """
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW mc_analysis_report AS (
                SELECT
                    -- Stable unique ID per line (required by Odoo ORM for _auto=False views)
                    l.id                        AS id,
                    o.id                        AS order_id,
                    o.name                      AS order_name,
                    o.channel_id                AS channel_id,
                    c.code                      AS channel_code,
                    l.product_id                AS product_id,
                    p.name                      AS product_name,
                    p.internal_sku              AS internal_sku,
                    p.category                  AS category,
                    o.order_date                AS order_date,
                    o.state                     AS state,
                    l.quantity                  AS quantity,
                    l.unit_price                AS unit_price,
                    l.subtotal                  AS revenue
                FROM mc_order_line  l
                JOIN mc_order       o ON o.id = l.order_id
                JOIN mc_product     p ON p.id = l.product_id
                JOIN mc_channel     c ON c.id = o.channel_id
                WHERE o.state != 'cancelled'
            )
        """)
