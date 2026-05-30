# -*- coding: utf-8 -*-
{
    'name': 'MC Platform Integration',
    'summary': 'Realtime WebSocket integration bridge for multichannel platform data',
    'description': 'Receives normalized Shopee/TikTok order payloads from the external middleware and stores them as Odoo raw orders.',
    'author': 'Thesis Project',
    'category': 'Sales/Multi-channel',
    'version': '17.0.1.0.0',
    'license': 'LGPL-3',
    'depends': ['mc_sale_order'],
    'application': False,
    'installable': True,
    'data': [
        'data/mc_channel_integration_data.xml',
        'data/mc_realtime_cron.xml',
        'views/mc_channel_views.xml',
        'views/mc_raw_order_views.xml',
    ],
}
