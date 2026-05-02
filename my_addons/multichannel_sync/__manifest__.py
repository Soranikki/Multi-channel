# -*- coding: utf-8 -*-
{
    'name': 'Multichannel Sync Legacy',
    'summary': 'Legacy monolithic module kept uninstallable/upgradable while migrating to mc_core, mc_product_inventory, mc_sale_order',
    'description': """
        Core operational engine for multi-channel e-commerce sales management.
        Receives standardized order payloads from the Integration Service (FastAPI),
        processes them through a pipeline, and manages inventory — all with custom models.
    """,
    'author': 'Thesis Project',
    'category': 'Sales/Multi-channel',
    'version': '17.0.1.0.0',
    'license': 'LGPL-3',
    'depends': ['base', 'mail', 'product'],
    'application': True,
    'installable': True,
    'data': [
        # Security — must load before views
        'security/multichannel_security.xml',
        'security/ir.model.access.csv',
        # Seed / config data
        'data/mc_channel_data.xml',
        'data/mc_sequence_data.xml',
        # Views — channels
        'views/mc_channel_views.xml',
        # Views — products & mappings
        'views/mc_product_views.xml',
        'views/mc_product_mapping_views.xml',
        # Views — pipeline: raw orders → orders
        'views/mc_raw_order_views.xml',
        'views/mc_order_views.xml',
        # Views — inventory
        'views/mc_stock_move_views.xml',
        'views/mc_stock_adjustment_wizard_views.xml',
        'views/mc_inventory_monitor_views.xml',
        # Views — analytics / dashboard
        'views/mc_analysis_views.xml',
        # Views — sync log
        'views/mc_sync_log_views.xml',
        # Menus (loaded last so all actions exist)
        'views/menus.xml',
    ],
}  # type: ignore
