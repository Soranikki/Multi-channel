from odoo import api, SUPERUSER_ID
env = env(user=SUPERUSER_ID)
orders = env['sale.order'].search([('mc_external_order_id', '=like', 'DEMO-%')], limit=5)
for o in orders:
    print(o.name, o.amount_total, [(l.product_id.name, l.price_unit, l.product_uom_qty) for l in o.order_line])
