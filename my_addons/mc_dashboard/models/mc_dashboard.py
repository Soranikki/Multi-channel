# -*- coding: utf-8 -*-
import datetime
from collections import defaultdict
from odoo import api, fields, models
from odoo.tools import format_amount

def format_short_money(amount):
    if amount >= 1_000_000_000:
        return f"{amount / 1_000_000_000:.1f}B"
    if amount >= 1_000_000:
        return f"{amount / 1_000_000:.1f}M"
    if amount >= 1_000:
        return f"{amount / 1_000:.1f}K"
    return str(round(amount))

class McDashboard(models.AbstractModel):
    _name = 'mc.dashboard'
    _description = 'Multi-Channel Dashboard Backend'

    @api.model
    def get_dashboard_data(self, date_range='30d', custom_start=False, custom_end=False):
        domain = [('mc_channel_id', '!=', False)]
        now = fields.Datetime.now()
        
        if date_range == 'today':
            start_date = now.replace(hour=0, minute=0, second=0)
            end_date = now
        elif date_range == '7d':
            start_date = now - datetime.timedelta(days=7)
            end_date = now
        elif date_range == '30d':
            start_date = now - datetime.timedelta(days=30)
            end_date = now
        elif date_range == '1y':
            start_date = now - datetime.timedelta(days=365)
            end_date = now
        elif date_range == 'custom' and custom_start and custom_end:
            start_date = datetime.datetime.strptime(custom_start, '%Y-%m-%d')
            end_date = datetime.datetime.strptime(custom_end, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
        else:
            start_date = now - datetime.timedelta(days=30)
            end_date = now
            
        domain_date = domain + [('date_order', '>=', start_date), ('date_order', '<=', end_date)]
        
        # Orders
        orders = self.env['sale.order'].search(domain_date)
        total_orders = len(orders)
        
        # Exclude cancelled from total revenue calculation
        valid_orders = orders.filtered(lambda o: o.state != 'cancel')
        total_revenue = sum(valid_orders.mapped('amount_total'))
        aov = total_revenue / len(valid_orders) if valid_orders else 0
        
        cancelled_orders = len(orders.filtered(lambda o: o.state == 'cancel'))
        cancel_rate = (cancelled_orders / total_orders * 100) if total_orders else 0
        
        # Sync queue errors
        error_queue = self.env['mc.stock.sync.queue'].search_count([('state', '=', 'error')])
        
        # KPIs
        kpis = {
            'total_revenue': format_short_money(total_revenue),
            'total_revenue_raw': total_revenue,
            'total_orders': total_orders,
            'aov': format_short_money(aov),
            'cancel_rate': f"{cancel_rate:.1f}%",
            'sync_errors': error_queue
        }

        # Revenue by Channel
        channel_data = defaultdict(lambda: {'revenue': 0, 'color': '#000000'})
        shopee_color = '#FF4500'
        tiktok_color = '#000000'
        
        for o in valid_orders:
            channel_name = o.mc_channel_id.name or 'Unknown'
            color = shopee_color if 'Shopee' in channel_name else (tiktok_color if 'TikTok' in channel_name else '#10b981')
            channel_data[channel_name]['revenue'] += o.amount_total
            channel_data[channel_name]['color'] = color
            
        revenue_by_channel = []
        for name, data in channel_data.items():
            pct = (data['revenue'] / total_revenue * 100) if total_revenue else 0
            revenue_by_channel.append({
                'name': name,
                'color': data['color'],
                'raw_value': data['revenue'],
                'value_str': format_short_money(data['revenue']),
                'percentage': f"{pct:.1f}%"
            })
            
        # Revenue Trend
        trend_data = {}
        days_diff = (end_date - start_date).days
        if days_diff == 0:
            days_diff = 1 # At least 1 point for today
        
        # limit trend points to 30 to avoid huge charts
        step = max(1, days_diff // 30)
        
        for i in range(days_diff, -1, -step):
            dt = (end_date - datetime.timedelta(days=i)).strftime('%m-%d')
            trend_data[dt] = {'Shopee': 0, 'TikTok': 0}
            
        for o in valid_orders:
            if o.date_order:
                dt = o.date_order.strftime('%m-%d')
            else:
                dt = o.create_date.strftime('%m-%d')
            if dt in trend_data:
                name = 'Shopee' if 'Shopee' in o.mc_channel_id.name else 'TikTok'
                trend_data[dt][name] += o.amount_total
                
        trend = {
            'labels': list(trend_data.keys()),
            'shopee': [d['Shopee'] for d in trend_data.values()],
            'tiktok': [d['TikTok'] for d in trend_data.values()]
        }
        
        # Order Status Breakdown
        status_counts = {'Pending': 0, 'To Ship': 0, 'Shipping': 0, 'Completed': 0, 'Cancelled': 0}
        for o in orders:
            if o.state == 'cancel':
                status_counts['Cancelled'] += 1
            elif o.state in ('sale', 'done'):
                if o.mc_order_status == 'shipping':
                    status_counts['Shipping'] += 1
                elif o.mc_order_status == 'delivered':
                    status_counts['Completed'] += 1
                else:
                    status_counts['To Ship'] += 1
            else:
                status_counts['Pending'] += 1
                
        order_status_chart = {
            'labels': list(status_counts.keys()),
            'data': list(status_counts.values())
        }
        
        # Top 5 Products
        lines = self.env['sale.order.line'].search([
            ('order_id.mc_channel_id', '!=', False),
            ('order_id.state', '!=', 'cancel'),
            ('order_id.date_order', '>=', start_date),
            ('order_id.date_order', '<=', end_date)
        ])
        product_qtys = defaultdict(float)
        for line in lines:
            if line.product_id:
                product_qtys[line.product_id.display_name] += line.product_uom_qty
        
        top_items = sorted(product_qtys.items(), key=lambda x: x[1], reverse=True)[:5]
        top_products = {
            'labels': [x[0] for x in top_items],
            'data': [x[1] for x in top_items]
        }
        
        # Low Stock
        mappings = self.env['mc.product.mapping'].search([('is_active', '=', True)])
        low_stock_items = []
        for m in mappings:
            if m.product_id and m.product_id.qty_available <= m.product_id.mc_buffer_qty:
                low_stock_items.append({
                    'sku': m.external_sku,
                    'name': m.product_name,
                    'qty': m.product_id.qty_available,
                    'status': 'CẦN NHẬP NGAY' if m.product_id.qty_available <= 0 else 'SẮP HẾT'
                })
                
        # Failed Syncs
        failed_syncs = self.env['mc.stock.sync.queue'].search([('state', '=', 'error')], limit=10)
        failed_sync_data = []
        for f in failed_syncs:
            failed_sync_data.append({
                'id': f.id,
                'channel': f.channel_id.name,
                'sku': f.external_sku,
                'qty': f.qty_to_sync,
                'error': f.error_message or 'Unknown Error',
                'time': f.last_attempt_at.strftime('%H:%M %p') if f.last_attempt_at else ''
            })

        # Channel Status for header
        channels = self.env['mc.channel'].search([('integration_enabled', '=', True)])
        channel_status = [{'name': c.name, 'connected': True} for c in channels]

        return {
            'kpis': kpis,
            'revenue_by_channel': revenue_by_channel,
            'trend': trend,
            'order_status': order_status_chart,
            'top_products': top_products,
            'low_stock': low_stock_items[:5],
            'failed_syncs': failed_sync_data,
            'channel_status': channel_status
        }
