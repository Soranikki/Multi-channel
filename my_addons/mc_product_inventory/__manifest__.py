# -*- coding: utf-8 -*-
{
    'name': 'MC Product and Inventory',
    'summary': 'Multichannel product mapping on top of Odoo Product and Inventory',
    'description': 'Uses Odoo product.product, product.template, stock.quant, and stock moves as the base Product/Inventory implementation.',
    'author': 'Thesis Project',
    'category': 'Sales/Multi-channel',
    'version': '17.0.1.0.0',
    'license': 'LGPL-3',
    'depends': ['mc_core', 'stock'],
    'application': False,
    'installable': True,
    'data': [
        'security/mc_product_inventory_security.xml',
        'security/ir.model.access.csv',
        'views/product_views.xml',
        'views/mc_product_mapping_views.xml',
        'views/menus.xml',
    ],
}
