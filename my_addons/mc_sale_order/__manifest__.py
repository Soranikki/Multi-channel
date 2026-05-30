# -*- coding: utf-8 -*-
{
    'name': 'MC Sale Order',
    'summary': 'Multichannel raw orders processed into Odoo Sales Orders',
    'description': 'Uses Odoo sale.order and sale.order.line as the base order management implementation.',
    'author': 'Thesis Project',
    'category': 'Sales/Multi-channel',
    'version': '17.0.1.0.0',
    'license': 'LGPL-3',
    'depends': ['mc_product_inventory', 'sale_stock'],
    'application': False,
    'installable': True,
    'data': [
        'security/mc_sale_order_security.xml',
        'security/ir.model.access.csv',
        'views/sale_order_views.xml',
        'views/mc_raw_order_views.xml',
        'views/menus.xml',
    ],
}
