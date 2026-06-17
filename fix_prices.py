from odoo import api, SUPERUSER_ID
env = env(user=SUPERUSER_ID)
orders = env['sale.order'].search([('mc_external_order_id', '=like', 'DEMO-%')])
for o in orders:
    for l in o.order_line:
        l.price_unit = l.price_unit * 1000
env.cr.commit()
print("Fixed prices!")
