from odoo import api, SUPERUSER_ID
env = env(user=SUPERUSER_ID)
orders = env['sale.order'].search([('mc_external_order_id', '=like', 'DEMO-%')])
from collections import Counter
counts = Counter([o.date_order.strftime('%m-%d') for o in orders])
for dt in sorted(counts.keys()):
    print(dt, counts[dt])
