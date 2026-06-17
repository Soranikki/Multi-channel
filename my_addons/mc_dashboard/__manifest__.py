# -*- coding: utf-8 -*-
{
    'name': 'MC Dashboard',
    'summary': 'Multichannel Analytics Dashboard',
    'description': 'Modern, clean dashboard for Multi-channel E-commerce tracking revenue, orders, and stock alerts.',
    'author': 'Thesis Project',
    'category': 'Sales/Multi-channel',
    'version': '17.0.1.0.0',
    'license': 'LGPL-3',
    'depends': ['mc_sale_order', 'mc_product_inventory', 'board', 'web'],
    'data': [
        'security/ir.model.access.csv',
        'views/dashboard_views.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'mc_dashboard/static/src/dashboard/dashboard.scss',
            'mc_dashboard/static/src/dashboard/dashboard.xml',
            'mc_dashboard/static/src/dashboard/dashboard.js',
        ],
    },
    'application': False,
    'installable': True,
}
