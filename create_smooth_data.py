import math
import random
from datetime import datetime, timedelta
from odoo import api, SUPERUSER_ID

env = env(user=SUPERUSER_ID)

# 1. Delete old DEMO orders
env.cr.execute("DELETE FROM sale_order_line WHERE order_id IN (SELECT id FROM sale_order WHERE mc_external_order_id LIKE 'DEMO-%')")
env.cr.execute("DELETE FROM sale_order WHERE mc_external_order_id LIKE 'DEMO-%'")
print("Deleted old demo orders.")

# 2. Get channels and product
shopee = env['mc.channel'].search([('middleware_channel_key', '=', 'shopee')], limit=1)
tiktok = env['mc.channel'].search([('middleware_channel_key', '=', 'tiktok')], limit=1)
mappings = env['mc.product.mapping'].search([('is_active', '=', True)])
products = [m.product_id for m in mappings if m.product_id]
if not products:
    print("No products!")
    exit()

now = datetime.now()
partner = env['res.partner'].search([('name', '=', 'Khách hàng Demo')], limit=1)

orders_created = 0

# 3. Generate exactly 1 order per day per channel with a calculated price
# This guarantees a smooth line chart
for day in range(31):
    order_date = now - timedelta(days=30 - day, hours=12)
    
    # Smooth curves with slight noise
    # Shopee: 4M -> 10M
    base_shopee = 4_000_000 + (6_000_000 * (day / 30.0))
    # Add a slight sine wave for natural curve
    base_shopee += math.sin(day / 4.0) * 800_000
    base_shopee += random.randint(-200_000, 200_000) # Noise
    
    # TikTok: 2M -> 8M
    base_tiktok = 2_000_000 + (6_000_000 * (day / 30.0))
    base_tiktok += math.sin((day+2) / 5.0) * 600_000
    base_tiktok += random.randint(-150_000, 150_000) # Noise
    
    for channel, amount in [(shopee, base_shopee), (tiktok, base_tiktok)]:
        if amount < 0: amount = 100_000
        
        # We just create 1 order with 1 generic line matching the amount
        # This makes the total_amount exactly what we want for the chart
        order_vals = {
            'partner_id': partner.id,
            'date_order': order_date,
            'mc_channel_id': channel.id,
            'mc_external_order_id': f"DEMO-{channel.middleware_channel_key.upper()}-{day}",
            'mc_order_status': 'delivered',
            'mc_payment_status': 'paid',
            'state': 'sale',
            'order_line': [(0, 0, {
                'product_id': products[0].id,
                'product_uom_qty': 1,
                'price_unit': round(amount)
            })]
        }
        env['sale.order'].create(order_vals)
        orders_created += 1

env.cr.commit()
print(f"Created {orders_created} smoothed demo orders.")
