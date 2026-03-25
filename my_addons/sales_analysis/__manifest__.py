{
    'name': 'Sales Analysis',
    'summary': 'Odoo 17 sales analytics app with live reports and reusable presets',
    'description': """
Sales Analysis
==============

Provides a focused sales analytics app for Odoo 17 based on the native
``sale.report`` model, plus reusable report presets for teams.

Features:
- live graph, pivot, and list reports for sales performance
- reusable analysis presets with filters and grouping
- internal summary page and JSON endpoint for each preset
- dedicated access groups and rules for analysts and managers
- app icon for quick access from the main menu
    """,
    'author': 'Custom Development',
    'website': 'https://www.odoo.com',
    'category': 'Sales/Reporting',
    'version': '17.0.1.0.0',
    'license': 'LGPL-3',
    'depends': ['sale_management'],
    'data': [
        'security/sales_analysis_security.xml',
        'security/ir.model.access.csv',
        'views/views.xml',
        'views/templates.xml',
    ],
    'application': True,
    'installable': True,
} # type: ignore
