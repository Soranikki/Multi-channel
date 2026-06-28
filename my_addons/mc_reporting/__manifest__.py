{
    'name': 'MC Reports',
    'summary': 'Multi-Channel Business Reports — Sales, Inventory, Sync Analysis',
    'description': """
        Professional reporting suite for Multi-Channel e-commerce:
        - Sales Summary: Revenue, orders, AOV, trends
        - Sales by Channel: Platform comparison with contribution %
        - Best Selling Products: Top sellers by quantity & revenue
        - Inventory Report: Stock levels, reservations, low stock alerts
        - Sync Status: Odoo vs platform stock comparison, sync health
        - Order Report: Order listing with date, channel, status filters
        
        All reports feature:
        - Interactive Chart.js visualizations
        - Date range + platform filters
        - KPI summary cards
        - PDF export (QWeb)
        - Excel export (XlsxWriter)
        - Professional print layout
    """,
    'author': 'Thesis Project',
    'category': 'Sales/Multi-channel',
    'version': '17.0.1.0.0',
    'license': 'LGPL-3',
    'depends': ['mc_sale_order', 'mc_product_inventory', 'mc_platform_integration', 'web'],
    'data': [
        'security/ir.model.access.csv',
        'data/mc_report_actions.xml',
        'views/reporting_views.xml',
        'views/menus.xml',
        'reports/mc_report_templates.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'mc_reporting/static/src/reporting/reporting.scss',
            'mc_reporting/static/src/reporting/reporting.xml',
            'mc_reporting/static/src/reporting/reporting.js',
        ],
    },
    'application': False,
    'installable': True,
}
