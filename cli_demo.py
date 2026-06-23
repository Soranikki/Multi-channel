import xmlrpc.client
import sys
import os
import json
import time
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import print as rprint

URL = "http://localhost:8069"
DB = "Multi-Channel"
USER = "dev"
PASSWORD = "123"

console = Console()

def get_auth():
    common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common', allow_none=True)
    uid = common.authenticate(DB, USER, PASSWORD, {})
    if not uid:
        console.print("[bold red]Lỗi đăng nhập! Kiểm tra lại URL, DB, USER, PASSWORD.[/bold red]")
        sys.exit(1)
    models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object', allow_none=True)
    return uid, models

def main_menu():
    uid, models = get_auth()
    
    while True:
        console.print("\n[bold cyan]--- ODOO MULTICHANNEL CLI DEMO ---[/bold cyan]")
        console.print("[1]. Xem tồn kho hiện tại (Inventory State)")
        console.print("[2]. Demo: Có đơn hàng mới (Trừ kho)")
        console.print("[3]. Demo: Xử lý bán vượt mức (Overselling Prevention)")
        console.print("[4]. Demo: Đồng bộ tồn kho lên Sàn (Sync-Back)")
        console.print("[0]. Thoát")
        
        choice = input("\nChọn kịch bản demo: ")
        
        if choice == '1':
            show_inventory(uid, models)
        elif choice == '2':
            simulate_new_order(uid, models)
        elif choice == '3':
            simulate_overselling(uid, models)
        elif choice == '4':
            simulate_sync_back(uid, models)
        elif choice == '0':
            console.print("[green]Thoát chương trình![/green]")
            break
        else:
            console.print("[red]Lựa chọn không hợp lệ.[/red]")

def show_inventory(uid, models):
    console.print("\n[bold yellow]=== TRẠNG THÁI TỒN KHO ==-[/bold yellow]")
    
    products = models.execute_kw(DB, uid, PASSWORD, 'product.product', 'search_read',
        [[('default_code', 'like', 'SKU-%')]],
        {'fields': ['default_code', 'name', 'qty_available', 'virtual_available', 'mc_buffer_qty', 'mc_low_stock_threshold', 'mc_is_low_stock']}
    )
    
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Mã (SKU)")
    table.add_column("Tên Sản Phẩm")
    table.add_column("Tồn thực tế (On Hand)")
    table.add_column("Dự báo (Forecast)")
    table.add_column("Dự phòng (Buffer)")
    table.add_column("Tồn đồng bộ (Synced Qty)", justify="right")
    table.add_column("Cảnh báo")
    
    for p in products:
        synced = max(0, p['virtual_available'] - p['mc_buffer_qty'])
        warning = "[bold red]Sắp hết hàng[/bold red]" if p['mc_is_low_stock'] else "[green]An toàn[/green]"
        
        table.add_row(
            p['default_code'],
            p['name'],
            str(p['qty_available']),
            str(p['virtual_available']),
            str(p['mc_buffer_qty']),
            f"[bold cyan]{synced}[/bold cyan]",
            warning
        )
        
    console.print(table)

def simulate_new_order(uid, models):
    console.print("\n[bold yellow]=== DEMO: ĐƠN HÀNG MỚI TỪ SHOPEE ==-[/bold yellow]")
    
    # 1. Tìm sản phẩm để test
    products = models.execute_kw(DB, uid, PASSWORD, 'product.product', 'search_read',
        [[('default_code', 'like', 'SKU-%')]],
        {'fields': ['default_code', 'name', 'list_price'], 'limit': 1}
    )
    
    if not products:
        console.print("[red]Không tìm thấy sản phẩm![/red]")
        return
        
    p = products[0]
    
    # 2. Tìm kênh shopee
    shopee = models.execute_kw(DB, uid, PASSWORD, 'mc.channel', 'search_read', [[('code', '=', 'shopee')]], {'fields': ['id'], 'limit': 1})
    if not shopee:
        console.print("[red]Không tìm thấy kênh Shopee![/red]")
        return
        
    channel_id = shopee[0]['id']
    ext_sku = f"SHP-{p['default_code']}"
    ext_order_id = f"SHP-DEMO-{int(time.time())}"
    qty = 2
    
    payload = {
        "external_order_id": ext_order_id,
        "customer_name": "Nguyễn Văn Demo",
        "customer_phone": "0988888888",
        "shipping_address": "Demo Address",
        "order_date": datetime.now().isoformat() + "Z",
        "total_amount": p['list_price'] * qty,
        "currency": "VND", "platform_order_status": "PAID",
        "items": [{
            "external_sku": ext_sku,
            "product_name": p['name'],
            "quantity": qty,
            "unit_price": p['list_price']
        }]
    }
    
    console.print(Panel(json.dumps(payload, indent=2, ensure_ascii=False), title="Payload gửi từ Sàn"))
    
    console.print("[blue]Đang đẩy đơn vào hệ thống Odoo...[/blue]")
    
    raw_id = models.execute_kw(DB, uid, PASSWORD, 'mc.raw.order', 'create', [{
        'channel_id': channel_id,
        'external_order_id': ext_order_id,
        'raw_payload': json.dumps(payload),
    }])
    
    try:
        models.execute_kw(DB, uid, PASSWORD, 'mc.raw.order', 'action_parse', [[raw_id]])
    except xmlrpc.client.Fault as e:
        if 'cannot marshal None' not in str(e): raise

    try:
        models.execute_kw(DB, uid, PASSWORD, 'mc.raw.order', 'action_process', [[raw_id]])
    except xmlrpc.client.Fault as e:
        if 'cannot marshal None' not in str(e): raise

    
    raw_order = models.execute_kw(DB, uid, PASSWORD, 'mc.raw.order', 'read', [[raw_id]], {'fields': ['state', 'sale_order_id', 'error_message']})[0]
    
    if raw_order['state'] == 'processed':
        so_name = raw_order['sale_order_id'][1]
        console.print(f"[bold green]Thành công![/bold green] Đơn hàng Odoo [bold]{so_name}[/bold] đã được tạo.")
        console.print("[yellow]Odoo sẽ tự động trừ kho dự báo (Forecast). Chạy [1] để kiểm tra lại kho.[/yellow]")
    else:
        console.print(f"[bold red]Lỗi:[/bold red] {raw_order['error_message']}")

def simulate_overselling(uid, models):
    console.print("\n[bold yellow]=== DEMO: CHỐNG BÁN VƯỢT MỨC (OVERSELLING) ==-[/bold yellow]")
    
    products = models.execute_kw(DB, uid, PASSWORD, 'product.product', 'search_read',
        [[('default_code', 'like', 'SKU-%')]],
        {'fields': ['default_code', 'name', 'list_price', 'virtual_available', 'mc_buffer_qty'], 'limit': 1}
    )
    p = products[0]
    
    console.print(f"[blue]Cấu hình Tồn kho hiện tại của {p['default_code']} ({p['name']}):[/blue]")
    console.print(f" - Dự báo: {p['virtual_available']}")
    console.print(f" - Buffer: {p['mc_buffer_qty']}")
    
    synced = p['virtual_available'] - p['mc_buffer_qty']
    if synced != 1:
        console.print(f"[yellow]>> Đang ép Tồn kho đồng bộ (Synced Qty) về = 1 để Demo (Thay đổi Buffer)...[/yellow]")
        models.execute_kw(DB, uid, PASSWORD, 'product.product', 'write', [[p['id']], {'mc_buffer_qty': p['virtual_available'] - 1}])
        console.print(f"[green]>> Xong! Hiện tại Synced Qty = 1.[/green]")

        
    shopee = models.execute_kw(DB, uid, PASSWORD, 'mc.channel', 'search_read', [[('code', '=', 'shopee')]], {'fields': ['id'], 'limit': 1})
    tiktok = models.execute_kw(DB, uid, PASSWORD, 'mc.channel', 'search_read', [[('code', '=', 'tiktok')]], {'fields': ['id'], 'limit': 1})
    
    console.print("\n[bold red]!!! SỰ KIỆN: 2 khách hàng cùng đặt mua trên Shopee và TikTok trong cùng 1 giây !!![/bold red]")
    import time
    # Đơn 1: Shopee
    ext_sku_shp = f"SHP-{p['default_code']}"
    ext_order_shp = f"SHP-OS-{int(time.time())}"
    payload1 = {
        "external_order_id": ext_order_shp, "customer_name": "Khách Shopee", "platform_order_status": "PAID",
        "items": [{"external_sku": ext_sku_shp, "product_name": p['name'], "quantity": 1, "unit_price": p['list_price']}]
    }
    
    # Đơn 2: TikTok
    ext_sku_tt = f"TT-{p['default_code']}"
    ext_order_tt = f"TT-OS-{int(time.time())}"
    payload2 = {
        "external_order_id": ext_order_tt, "customer_name": "Khách TikTok", "platform_order_status": "PAID",
        "items": [{"external_sku": ext_sku_tt, "product_name": p['name'], "quantity": 1, "unit_price": p['list_price']}]
    }
    import json
    console.print("[blue]>> Bắn đơn Shopee vào hệ thống...[/blue]")
    id1 = models.execute_kw(DB, uid, PASSWORD, 'mc.raw.order', 'create', [{'channel_id': shopee[0]['id'], 'external_order_id': ext_order_shp, 'raw_payload': json.dumps(payload1)}])
    try:
        models.execute_kw(DB, uid, PASSWORD, 'mc.raw.order', 'action_parse', [[id1]])
    except xmlrpc.client.Fault as e:
        if 'cannot marshal None' not in str(e): raise

    try:
        models.execute_kw(DB, uid, PASSWORD, 'mc.raw.order', 'action_process', [[id1]])
    except xmlrpc.client.Fault as e:
        if 'cannot marshal None' not in str(e): raise

    res1 = models.execute_kw(DB, uid, PASSWORD, 'mc.raw.order', 'read', [[id1]], {'fields': ['state', 'error_message']})[0]
    
    if res1['state'] == 'processed':
        so_id = models.execute_kw(DB, uid, PASSWORD, 'mc.raw.order', 'read', [[id1]], {'fields': ['sale_order_id']})[0]['sale_order_id'][0]
        models.execute_kw(DB, uid, PASSWORD, 'sale.order', 'action_confirm', [[so_id]])
        console.print("[bold green]>> Đơn Shopee: THÀNH CÔNG (Tạo Sale Order).[/bold green]")
    else:
        console.print(f"[bold red]>> Đơn Shopee: THẤT BẠI - {res1['error_message']}[/bold red]")
        
    console.print("\n[blue]>> Bắn đơn TikTok vào hệ thống...[/blue]")
    id2 = models.execute_kw(DB, uid, PASSWORD, 'mc.raw.order', 'create', [{'channel_id': tiktok[0]['id'], 'external_order_id': ext_order_tt, 'raw_payload': json.dumps(payload2)}])
    try:
        models.execute_kw(DB, uid, PASSWORD, 'mc.raw.order', 'action_parse', [[id2]])
    except xmlrpc.client.Fault as e:
        if 'cannot marshal None' not in str(e): raise

    try:
        models.execute_kw(DB, uid, PASSWORD, 'mc.raw.order', 'action_process', [[id2]])
    except xmlrpc.client.Fault as e:
        if 'cannot marshal None' not in str(e): raise

    res2 = models.execute_kw(DB, uid, PASSWORD, 'mc.raw.order', 'read', [[id2]], {'fields': ['state', 'error_message']})[0]
    
    if res2['state'] == 'processed':
        console.print("[bold green]>> Đơn TikTok: THÀNH CÔNG.[/bold green]")
    else:
        console.print(f"[bold red]>> Đơn TikTok: THẤT BẠI - Hệ thống chặn tạo đơn vì không đủ tồn kho (Overselling Prevention)![/bold red]")
        console.print(f"[dim]{res2['error_message']}[/dim]")

def simulate_sync_back(uid, models):
    console.print("\n[bold yellow]=== DEMO: ĐỒNG BỘ KHO LÊN SÀN (SYNC-BACK) ==-[/bold yellow]")
    
    console.print("[blue]Đang quét các sản phẩm có sự thay đổi tồn kho (Chạy cronjob giả lập)...[/blue]")
    
    models.execute_kw(DB, uid, PASSWORD, 'mc.product.mapping', 'action_queue_stock_updates', [])
    
    queues = models.execute_kw(DB, uid, PASSWORD, 'mc.stock.sync.queue', 'search_read',
        [[('state', '=', 'pending')]],
        {'fields': ['channel_id', 'mapping_id', 'qty_to_sync'], 'limit': 10}
    )
    
    if not queues:
        console.print("[green]Không có dữ liệu tồn kho nào cần đồng bộ![/green]")
        return
        
    table = Table(show_header=True, header_style="bold blue")
    table.add_column("Sàn (Channel)")
    table.add_column("SKU (Sàn)")
    table.add_column("Số lượng gửi lên (Qty)")
    
    for q in queues:
        mapping = models.execute_kw(DB, uid, PASSWORD, 'mc.product.mapping', 'read', [[q['mapping_id'][0]]], {'fields': ['external_sku']})[0]
        table.add_row(
            q['channel_id'][1],
            mapping['external_sku'],
            str(q['qty_to_sync'])
        )
        
    console.print(table)
    console.print("[yellow]Hệ thống Odoo sẽ gọi ra API của Shopee/TikTok để cập nhật các số lượng này.[/yellow]")
    
    # Mark as done to clear queue
    queue_ids = [q['id'] for q in queues]
    models.execute_kw(DB, uid, PASSWORD, 'mc.stock.sync.queue', 'write', [queue_ids, {'state': 'done'}])
    console.print("[green]Đã hoàn thành mô phỏng đồng bộ![/green]")

if __name__ == '__main__':
    main_menu()
