def run():
    print("Fixing historical dates...")
    env.cr.execute("ALTER TABLE sale_order DISABLE TRIGGER ALL;")
    
    env.cr.execute("""
        UPDATE sale_order so
        SET date_order = ro.parsed_order_date
        FROM mc_raw_order ro
        WHERE ro.sale_order_id = so.id
    """)
    
    env.cr.execute("ALTER TABLE sale_order ENABLE TRIGGER ALL;")
    env.cr.commit()
    print("Dates fixed!")

run()
