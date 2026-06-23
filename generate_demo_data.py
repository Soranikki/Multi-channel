import random
from datetime import datetime, timedelta
import json
from odoo import fields

def run():
    print("Starting Fake Data Generation...")
    
    # We will NOT delete old data. We just add new historical data!
    
    shopee = env['mc.channel'].search([('code', '=', 'shopee')], limit=1)
    if not shopee:
        shopee = env['mc.channel'].create({'name': 'Shopee', 'code': 'shopee', 'active': True})
        
    tiktok = env['mc.channel'].search([('code', '=', 'tiktok')], limit=1)
    if not tiktok:
        tiktok = env['mc.channel'].create({'name': 'TikTok Shop', 'code': 'tiktok', 'active': True})
        
    channels = [shopee, tiktok]
    
    # 3. Create Products & Mappings
    print("Creating new products and inventory for demo...")
    products_data = [
        ("Tai nghe chống ồn Sony WH-1000XM5", 6500000),
        ("Chuột Apple Magic Mouse", 2100000),
        ("Cáp sạc Magsafe 3", 1200000),
        ("Máy lọc không khí Xiaomi", 2400000),
        ("Sạc Anker Nano 3 30W", 450000),
        ("Ổ cứng SSD Samsung 1TB", 1950000),
        ("Đế tản nhiệt Laptop nhôm", 350000),
        ("Camera hành trình GoPro", 3200000),
    ]
    
    products = []
    location_id = env.ref('stock.stock_location_stock').id
    for name, price in products_data:
        code = f"SKU-{random.randint(10000, 99999)}"
        product = env['product.product'].create({
            'name': name,
            'default_code': code,
            'list_price': price,
            'type': 'product',
            'mc_buffer_qty': random.randint(2, 5),
            'mc_low_stock_threshold': random.randint(5, 10),
        })
        
        # Add inventory
        env['stock.quant'].with_context(inventory_mode=True).create({
            'product_id': product.id,
            'location_id': location_id,
            'inventory_quantity': random.randint(500, 2000),
        }).action_apply_inventory()
        
        products.append(product)
        
        env['mc.product.mapping'].create([
            {
                'channel_id': shopee.id,
                'product_id': product.id,
                'external_sku': f"SHP-{code}",
                'external_name': f"[Shopee] {name}",
                'is_active': True,
            },
            {
                'channel_id': tiktok.id,
                'product_id': product.id,
                'external_sku': f"TT-{code}",
                'external_name': f"[TikTok] {name}",
                'is_active': True,
            }
        ])
        
    print("Generating historical orders (This might take a few minutes)...")
    start_date = datetime(2025, 1, 1)
    end_date = datetime.now()
    
    current_date = start_date
    order_count = 0
    names = ["Nguyễn Văn A", "Trần Thị B", "Lê Văn C", "Phạm Thị D", "Lý Đức E", "Đặng Văn F"]
    
    while current_date <= end_date:
        is_weekend = current_date.weekday() >= 5
        is_mega_sale = (current_date.day == current_date.month)
        
        # Base orders
        base_orders = random.randint(2, 5)
        if is_weekend: base_orders = int(base_orders * 1.5)
        if is_mega_sale: base_orders = int(base_orders * 3.0)
            
        trend_multiplier = 1.0 + ((current_date - start_date).days / 365.0) * 0.7
        daily_orders = int(base_orders * trend_multiplier)
        
        for _ in range(daily_orders):
            channel = random.choice(channels)
            prod = random.choice(products)
            qty = random.randint(1, 3)
            
            ext_sku = f"SHP-{prod.default_code}" if channel.code == 'shopee' else f"TT-{prod.default_code}"
            
            payload = {
                "external_order_id": f"{channel.code.upper()}-{current_date.strftime('%y%m%d')}-{random.randint(10000, 99999)}",
                "customer_name": random.choice(names),
                "customer_phone": f"09{random.randint(10000000, 99999999)}",
                "shipping_address": "Hồ Chí Minh",
                "order_date": current_date.replace(hour=random.randint(0, 23), minute=random.randint(0, 59)).isoformat() + "Z",
                "total_amount": prod.list_price * qty,
                "currency": "VND",
                "items": [{
                    "external_sku": ext_sku,
                    "product_name": prod.name,
                    "quantity": qty,
                    "unit_price": prod.list_price
                }]
            }
            
            raw_order = env['mc.raw.order'].create({
                'channel_id': channel.id,
                'external_order_id': payload["external_order_id"],
                'raw_payload': json.dumps(payload),
                'received_at': current_date.replace(hour=random.randint(0, 23)),
            })
            
            raw_order.action_parse()
            if raw_order.state == 'parsed':
                raw_order.action_process()
                
            if raw_order.sale_order_id:
                r = random.random()
                if r < 0.85:
                    raw_order.sale_order_id._mc_apply_channel_statuses('delivered', 'paid')
                elif r < 0.95:
                    raw_order.sale_order_id._mc_apply_channel_statuses('cancelled', 'failed')
                else:
                    raw_order.sale_order_id._mc_apply_channel_statuses('refunded', 'refunded')
            
            order_count += 1
            
        current_date += timedelta(days=1)
        if current_date.day == 1:
            env.cr.commit()
            print(f"Committed orders up to {current_date.strftime('%Y-%m-%d')}...")
            
    env.cr.commit()
    print(f"Done! Total orders generated: {order_count}")

run()
