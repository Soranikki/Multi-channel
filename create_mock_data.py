import random
from datetime import datetime, timedelta
from odoo import api, SUPERUSER_ID

env = env(user=SUPERUSER_ID)

# Find Channels
shopee = env['mc.channel'].search([('middleware_channel_key', '=', 'shopee')], limit=1)
tiktok = env['mc.channel'].search([('middleware_channel_key', '=', 'tiktok')], limit=1)

if not shopee or not tiktok:
    print("Channels not found!")
    exit()

# Find or Create Partner
partner = env['res.partner'].search([('name', '=', 'Khách hàng Demo')], limit=1)
if not partner:
    partner = env['res.partner'].create({'name': 'Khách hàng Demo'})

# Find Mappings to get products
mappings = env['mc.product.mapping'].search([('is_active', '=', True)])
products = [m.product_id for m in mappings if m.product_id]

if not products:
    print("No mapped products found!")
    exit()

print(f"Found {len(products)} products to generate orders.")

# Generate Data for the last 30 days
now = datetime.now()
total_orders_to_generate = 150

states = ['sale', 'cancel']
state_weights = [0.85, 0.15]  # 85% success, 15% cancel

def get_random_state():
    return random.choices(states, weights=state_weights, k=1)[0]

orders_created = 0
for i in range(total_orders_to_generate):
    # Random day within last 30 days
    days_ago = random.randint(0, 30)
    order_date = now - timedelta(days=days_ago, hours=random.randint(0, 23), minutes=random.randint(0, 59))
    
    channel = random.choice([shopee, tiktok])
    state = get_random_state()
    
    if state == 'cancel':
        mc_order_status = 'cancelled'
        mc_payment_status = 'refunded'
    else:
        mc_order_status = random.choice(['shipping', 'delivered', 'confirmed'])
        mc_payment_status = 'paid'

    order_vals = {
        'partner_id': partner.id,
        'date_order': order_date,
        'mc_channel_id': channel.id,
        'mc_external_order_id': f"DEMO-{channel.middleware_channel_key.upper()}-{10000 + i}",
        'mc_order_status': mc_order_status,
        'mc_payment_status': mc_payment_status,
        'state': state,
    }

    # Add 1 to 3 random products
    order_lines = []
    num_products = random.randint(1, 3)
    chosen_products = random.sample(products, num_products)
    
    for prod in chosen_products:
        qty = random.randint(1, 3)
        order_lines.append((0, 0, {
            'product_id': prod.id,
            'product_uom_qty': qty,
            'price_unit': prod.list_price or random.choice([150000, 300000, 500000, 850000])
        }))
        
    order_vals['order_line'] = order_lines
    
    # Create the order
    order = env['sale.order'].create(order_vals)
    orders_created += 1
    
    if orders_created % 20 == 0:
        print(f"Created {orders_created} orders...")
        env.cr.commit()

env.cr.commit()
print(f"Successfully generated {orders_created} demo orders!")
