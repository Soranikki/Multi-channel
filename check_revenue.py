from odoo import api, SUPERUSER_ID
env = env(user=SUPERUSER_ID)
orders = env['sale.order'].search([('mc_channel_id', '!=', False), ('state', '!=', 'cancel')])
print(f"Total Orders: {len(orders)}")
print(f"Total Revenue: {sum(o.amount_total for o in orders)}")
