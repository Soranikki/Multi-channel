def run():
    print("WARNING: Cleaning all demo data...")
    # Delete sale orders
    env.cr.execute("DELETE FROM sale_order_line WHERE order_id IN (SELECT id FROM sale_order WHERE mc_channel_id IS NOT NULL);")
    env.cr.execute("DELETE FROM sale_order WHERE mc_channel_id IS NOT NULL;")
    env.cr.execute("DELETE FROM mc_raw_order;")
    env.cr.execute("DELETE FROM mc_product_mapping;")
    
    # Clean stock references
    env.cr.execute("DELETE FROM stock_valuation_layer WHERE product_id IN (SELECT id FROM product_product WHERE default_code LIKE 'SKU-%');")
    env.cr.execute("DELETE FROM stock_move_line WHERE product_id IN (SELECT id FROM product_product WHERE default_code LIKE 'SKU-%');")
    env.cr.execute("DELETE FROM stock_move WHERE product_id IN (SELECT id FROM product_product WHERE default_code LIKE 'SKU-%');")
    env.cr.execute("DELETE FROM stock_quant WHERE product_id IN (SELECT id FROM product_product WHERE default_code LIKE 'SKU-%');")
    
    # Delete products
    env.cr.execute("DELETE FROM product_product WHERE default_code LIKE 'SKU-%';")
    env.cr.execute("DELETE FROM product_template WHERE default_code LIKE 'SKU-%';")
    
    env.cr.commit()
    print("Cleanup done!")

run()
