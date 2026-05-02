# -*- coding: utf-8 -*-
{
    'name': 'MC Core',
    'summary': 'Shared multichannel sales configuration and logging',
    'description': 'Core sales channels, shared security groups, menus, and sync logs for multichannel modules.',
    'author': 'Thesis Project',
    'category': 'Sales/Multi-channel',
    'version': '17.0.1.0.0',
    'license': 'LGPL-3',
    'depends': ['base', 'mail'],
    'application': True,
    'installable': True,
    'data': [
        'security/mc_core_security.xml',
        'security/ir.model.access.csv',
        'data/mc_channel_data.xml',
        'views/menus.xml',
        'views/mc_channel_views.xml',
        'views/mc_sync_log_views.xml',
    ],
}
