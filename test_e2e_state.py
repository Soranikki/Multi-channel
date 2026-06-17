import xmlrpc.client
import json

URL = "http://127.0.0.1:8069"
DB = "Multi-Channel"
USER = "dev"
PASS = "123"

def main():
    try:
        common = xmlrpc.client.ServerProxy('{}/xmlrpc/2/common'.format(URL))
        uid = common.authenticate(DB, USER, PASS, {})
        if not uid:
            print("Authentication failed.")
            return

        models = xmlrpc.client.ServerProxy('{}/xmlrpc/2/object'.format(URL))

        # Check Sale Orders
        sale_orders = models.execute_kw(DB, uid, PASS, 'sale.order', 'search_read',
            [[('mc_channel_id', '!=', False)]],
            {'fields': ['name', 'mc_external_order_id', 'state', 'mc_order_status', 'amount_total', 'order_line']}
        )
        print(f"--- Sale Orders created from Integration ---")
        for so in sale_orders:
            print(f"Order: {so['name']}, Ext_ID: {so['mc_external_order_id']}, Odoo_State: {so['state']}, Channel_State: {so['mc_order_status']}, Total: {so['amount_total']}")
            
        # Check Mappings
        mappings = models.execute_kw(DB, uid, PASS, 'mc.product.mapping', 'search_read',
            [[]],
            {'fields': ['channel_id', 'external_sku', 'product_id', 'synced_qty', 'qty_available']}
        )
        print(f"\\n--- Product Mappings ---")
        for m in mappings:
            print(f"Channel: {m['channel_id'][1]}, SKU: {m['external_sku']}, Product: {m['product_id'][1] if m['product_id'] else None}, Sys Qty: {m['qty_available']}, Synced Qty: {m['synced_qty']}")

        # Check Inventory Queue
        queues = models.execute_kw(DB, uid, PASS, 'mc.stock.sync.queue', 'search_read',
            [[]],
            {'fields': ['channel_id', 'external_sku', 'qty_to_sync', 'state', 'error_message']}
        )
        print(f"\n--- Stock Sync Queue ---")
        for q in queues:
            print(f"Channel: {q['channel_id'][1]}, SKU: {q['external_sku']}, Qty: {q['qty_to_sync']}, State: {q['state']}, Error: {q.get('error_message')}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    main()
