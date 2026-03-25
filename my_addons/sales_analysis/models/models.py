from datetime import date, datetime, time, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class SalesAnalysisPreset(models.Model):
    _name = 'sales.analysis.preset'
    _description = 'Sales Analysis Preset'
    _order = 'sequence, name, id'

    name = fields.Char(required=True, translate=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    color = fields.Integer()
    user_id = fields.Many2one(
        'res.users',
        string='Owner',
        required=True,
        default=lambda self: self.env.user,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    is_shared = fields.Boolean(string='Shared With Team')
    date_range = fields.Selection(
        selection=[
            ('this_month', 'This Month'),
            ('this_quarter', 'This Quarter'),
            ('this_year', 'This Year'),
            ('last_30_days', 'Last 30 Days'),
            ('last_90_days', 'Last 90 Days'),
            ('custom', 'Custom Range'),
        ],
        string='Period',
        required=True,
        default='this_year',
    )
    date_from = fields.Date()
    date_to = fields.Date()
    state_scope = fields.Selection(
        selection=[
            ('sale', 'Confirmed Orders'),
            ('quotation', 'Quotations'),
            ('all', 'All Documents'),
        ],
        string='Document Scope',
        required=True,
        default='sale',
    )
    invoice_status = fields.Selection(
        selection=[
            ('upselling', 'Upselling Opportunity'),
            ('invoiced', 'Fully Invoiced'),
            ('to invoice', 'To Invoice'),
            ('no', 'Nothing to Invoice'),
        ],
        string='Invoice Status',
    )
    group_by = fields.Selection(
        selection=[
            ('date:month', 'Month'),
            ('user_id', 'Salesperson'),
            ('team_id', 'Sales Team'),
            ('partner_id', 'Customer'),
            ('country_id', 'Country'),
            ('product_tmpl_id', 'Product'),
            ('categ_id', 'Product Category'),
            ('state', 'Status'),
            ('company_id', 'Company'),
            ('none', 'No Default Grouping'),
        ],
        string='Default Group By',
        required=True,
        default='date:month',
    )
    sales_team_id = fields.Many2one('crm.team', string='Sales Team')
    salesperson_id = fields.Many2one('res.users', string='Salesperson')
    partner_id = fields.Many2one('res.partner', string='Customer')
    product_tmpl_id = fields.Many2one('product.template', string='Product')
    categ_id = fields.Many2one('product.category', string='Product Category')
    notes = fields.Text()

    currency_id = fields.Many2one('res.currency', compute='_compute_currency_id')
    order_count = fields.Integer(compute='_compute_metrics', string='Orders')
    total_revenue = fields.Monetary(compute='_compute_metrics', currency_field='currency_id')
    untaxed_total = fields.Monetary(compute='_compute_metrics', currency_field='currency_id')
    qty_ordered = fields.Float(compute='_compute_metrics', string='Ordered Qty')
    qty_delivered = fields.Float(compute='_compute_metrics', string='Delivered Qty')
    qty_to_invoice = fields.Float(compute='_compute_metrics', string='Qty To Invoice')

    @api.depends('company_id')
    def _compute_currency_id(self):
        for preset in self:
            preset.currency_id = preset.company_id.currency_id or self.env.company.currency_id

    @api.depends(
        'company_id',
        'date_range',
        'date_from',
        'date_to',
        'state_scope',
        'invoice_status',
        'sales_team_id',
        'salesperson_id',
        'partner_id',
        'product_tmpl_id',
        'categ_id',
    )
    def _compute_metrics(self):
        SaleReport = self.env['sale.report']
        aggregate_fields = [
            'price_total:sum',
            'price_subtotal:sum',
            'product_uom_qty:sum',
            'qty_delivered:sum',
            'qty_to_invoice:sum',
        ]
        for preset in self:
            domain = preset._get_sale_report_domain()
            grouped = SaleReport.read_group(domain, aggregate_fields, [])
            values = grouped[0] if grouped else {}
            order_refs = {
                order.id
                for order in SaleReport.search(domain).mapped('order_reference')
                if order
            }
            preset.order_count = len(order_refs)
            preset.total_revenue = values.get('price_total_sum', 0.0)
            preset.untaxed_total = values.get('price_subtotal_sum', 0.0)
            preset.qty_ordered = values.get('product_uom_qty_sum', 0.0)
            preset.qty_delivered = values.get('qty_delivered_sum', 0.0)
            preset.qty_to_invoice = values.get('qty_to_invoice_sum', 0.0)

    @api.constrains('date_range', 'date_from', 'date_to')
    def _check_custom_dates(self):
        for preset in self:
            if preset.date_range == 'custom':
                if not preset.date_from or not preset.date_to:
                    raise ValidationError(_('Custom range presets require both From and To dates.'))
                if preset.date_from > preset.date_to:
                    raise ValidationError(_('The start date must be earlier than or equal to the end date.'))

    def _get_period_bounds(self):
        self.ensure_one()
        today = fields.Date.context_today(self)
        if self.date_range == 'custom':
            return self.date_from, self.date_to
        if self.date_range == 'this_month':
            start = today.replace(day=1)
            if today.month == 12:
                end = date(today.year, 12, 31)
            else:
                end = date(today.year, today.month + 1, 1) - timedelta(days=1)
            return start, end
        if self.date_range == 'this_quarter':
            quarter_start_month = ((today.month - 1) // 3) * 3 + 1
            start = date(today.year, quarter_start_month, 1)
            if quarter_start_month == 10:
                end = date(today.year, 12, 31)
            else:
                end = date(today.year, quarter_start_month + 3, 1) - timedelta(days=1)
            return start, end
        if self.date_range == 'this_year':
            return date(today.year, 1, 1), date(today.year, 12, 31)
        if self.date_range == 'last_30_days':
            return today - timedelta(days=29), today
        if self.date_range == 'last_90_days':
            return today - timedelta(days=89), today
        return False, False

    def _get_sale_report_domain(self):
        self.ensure_one()
        domain = [('company_id', '=', self.company_id.id)]
        start_date, end_date = self._get_period_bounds()
        if start_date:
            domain.append(('date', '>=', fields.Datetime.to_string(datetime.combine(start_date, time.min))))
        if end_date:
            domain.append(('date', '<=', fields.Datetime.to_string(datetime.combine(end_date, time.max))))
        if self.state_scope == 'sale':
            domain.append(('state', '=', 'sale'))
        elif self.state_scope == 'quotation':
            domain.append(('state', 'in', ('draft', 'sent')))
        if self.invoice_status:
            domain.append(('invoice_status', '=', self.invoice_status))
        if self.sales_team_id:
            domain.append(('team_id', '=', self.sales_team_id.id))
        if self.salesperson_id:
            domain.append(('user_id', '=', self.salesperson_id.id))
        if self.partner_id:
            domain.append(('partner_id', '=', self.partner_id.id))
        if self.product_tmpl_id:
            domain.append(('product_tmpl_id', '=', self.product_tmpl_id.id))
        if self.categ_id:
            domain.append(('categ_id', 'child_of', self.categ_id.id))
        return domain

    def _get_summary_payload(self):
        self.ensure_one()
        report_model = self.env['sale.report']
        domain = self._get_sale_report_domain()
        top_customers = report_model.read_group(
            domain,
            ['partner_id', 'price_total:sum'],
            ['partner_id'],
            limit=5,
            lazy=False,
        )
        top_products = report_model.read_group(
            domain,
            ['product_tmpl_id', 'price_total:sum'],
            ['product_tmpl_id'],
            limit=5,
            lazy=False,
        )
        top_customers = sorted(top_customers, key=lambda row: row.get('price_total_sum', 0.0), reverse=True)[:5]
        top_products = sorted(top_products, key=lambda row: row.get('price_total_sum', 0.0), reverse=True)[:5]
        return {
            'id': self.id,
            'name': self.name,
            'company': self.company_id.display_name,
            'owner': self.user_id.display_name,
            'group_by': dict(self._fields['group_by'].selection).get(self.group_by),
            'date_range': dict(self._fields['date_range'].selection).get(self.date_range),
            'state_scope': dict(self._fields['state_scope'].selection).get(self.state_scope),
            'invoice_status': dict(self._fields['invoice_status'].selection).get(self.invoice_status) if self.invoice_status else '',
            'metrics': {
                'order_count': self.order_count,
                'total_revenue': self.total_revenue,
                'untaxed_total': self.untaxed_total,
                'qty_ordered': self.qty_ordered,
                'qty_delivered': self.qty_delivered,
                'qty_to_invoice': self.qty_to_invoice,
                'currency': self.currency_id.symbol or self.currency_id.name,
            },
            'top_customers': [
                {
                    'name': row['partner_id'][1] if row.get('partner_id') else _('Undefined Customer'),
                    'amount': row.get('price_total_sum', 0.0),
                }
                for row in top_customers
            ],
            'top_products': [
                {
                    'name': row['product_tmpl_id'][1] if row.get('product_tmpl_id') else _('Undefined Product'),
                    'amount': row.get('price_total_sum', 0.0),
                }
                for row in top_products
            ],
        }

    def action_open_analysis(self):
        self.ensure_one()
        views = [
            (self.env.ref('sales_analysis.view_sales_analysis_graph').id, 'graph'),
            (self.env.ref('sales_analysis.view_sales_analysis_pivot').id, 'pivot'),
            (self.env.ref('sales_analysis.view_sales_analysis_tree').id, 'tree'),
        ]
        context = {
            'group_by_no_leaf': 1,
        }
        if self.group_by != 'none':
            context['group_by'] = self.group_by
        return {
            'type': 'ir.actions.act_window',
            'name': _('Sales Analysis: %s', self.name),
            'res_model': 'sale.report',
            'view_mode': 'graph,pivot,tree',
            'views': views,
            'search_view_id': self.env.ref('sales_analysis.view_sales_analysis_search').id,
            'domain': self._get_sale_report_domain(),
            'context': context,
            'target': 'current',
        }

    def action_open_summary_page(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': f'/sales_analysis/preset/{self.id}',
            'target': 'new',
        }
