import random
from datetime import datetime, timedelta
from odoo import api, SUPERUSER_ID

env = env(user=SUPERUSER_ID)

shopee = env['mc.channel'].search([('middleware_channel_key', '=', 'shopee')], limit=1)
tiktok = env['mc.channel'].search([('middleware_channel_key', '=', 'tiktok')], limit=1)

mappings = env['mc.product.mapping'].search([('is_active', '=', True)])

for i in range(5):
    m = random.choice(mappings)
    env['mc.stock.sync.queue'].create({
        'channel_id': random.choice([shopee, tiktok]).id,
        'mapping_id': m.id,
        'qty_to_sync': random.randint(1, 50),
        'state': 'error',
        'error_message': random.choice([
            'API Rate Limit Exceeded (HTTP 429)',
            'Product Mapping Not Found (Odoo ID null)',
            'Timeout while pushing stock update',
            'Platform API returned 500 Internal Server Error'
        ]),
        'attempt_count': random.randint(1, 5)
    })

env.cr.commit()
print("Generated 5 failed sync events")
