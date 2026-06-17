from odoo import api, SUPERUSER_ID
env = env(user=SUPERUSER_ID)
orders = env['sale.order'].search([('mc_external_order_id', '=like', 'DEMO-%')])
for o in orders[:10]:
    print(o.name, o.date_order, o.create_date)
