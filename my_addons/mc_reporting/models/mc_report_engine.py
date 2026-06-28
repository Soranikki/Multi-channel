from datetime import timedelta
from collections import defaultdict
from odoo import api, fields, models


def _fmt(amount):
    if amount >= 1_000_000_000:
        return f"{amount / 1_000_000_000:.1f}B"
    if amount >= 1_000_000:
        return f"{amount / 1_000_000:.1f}M"
    if amount >= 1_000:
        return f"{amount / 1_000:.1f}K"
    return str(round(amount))


def _domain(platform, start_date, end_date):
    dom = [('mc_channel_id', '!=', False)]
    if platform and platform != 'all':
        dom += [('mc_channel_id.code', '=', platform)]
    if start_date:
        dom += [('date_order', '>=', start_date)]
    if end_date:
        dom += [('date_order', '<=', end_date)]
    return dom


def _resolve_dates(date_range, custom_start, custom_end):
    now = fields.Datetime.now()
    if date_range == 'today':
        return now.replace(hour=0, minute=0, second=0), now
    if date_range == '7d':
        return now - timedelta(days=7), now
    if date_range == '30d':
        return now - timedelta(days=30), now
    if date_range == '90d':
        return now - timedelta(days=90), now
    if date_range == '1y':
        return now - timedelta(days=365), now
    if date_range == 'custom' and custom_start and custom_end:
        from datetime import datetime
        s = datetime.strptime(custom_start, '%Y-%m-%d')
        e = datetime.strptime(custom_end, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
        return s, e
    return now - timedelta(days=30), now


class McReportEngine(models.AbstractModel):
    _name = 'mc.report.engine'
    _description = 'Multi-Channel Report Engine'

    @api.model
    def get_report_data(self, report_type, date_range='30d', platform='all',
                        custom_start=False, custom_end=False):
        start, end = _resolve_dates(date_range, custom_start, custom_end)
        handler = getattr(self, f'_build_{report_type}', None)
        if not handler:
            return {'error': f'Unknown report type: {report_type}'}
        return handler(start, end, platform)

    # ── Sales Summary ────────────────────────────────────────────────────────

    def _build_sales_summary(self, start, end, platform):
        dom = _domain(platform, start, end) + [('state', 'not in', ('draft', 'sent', 'cancel'))]
        orders = self.env['sale.order'].search(dom)
        total_rev = sum(orders.mapped('amount_total'))
        total_ord = len(orders)
        aov = total_rev / total_ord if total_ord else 0

        trend_data = self._calc_trend(orders, start, end)
        table_data = self._daily_summary(orders, start, end)

        growth, growth_label = self._calc_growth(dom, start, end)

        return {
            'kpis': {
                'total_revenue_str': _fmt(total_rev),
                'total_revenue_raw': total_rev,
                'total_orders': total_ord,
                'aov_str': _fmt(aov),
                'aov_raw': aov,
                'growth': growth_label,
                'growth_up': growth >= 0,
                'cancelled': 0,
            },
            'trend': trend_data,
            'table': table_data,
        }

    # ── Sales by Channel ─────────────────────────────────────────────────────

    def _build_sales_channel(self, start, end, platform):
        dom = _domain(platform, start, end) + [('state', 'not in', ('draft', 'sent', 'cancel'))]
        orders = self.env['sale.order'].search(dom)

        channel_map = {}
        channels = self.env['mc.channel'].search([])
        for ch in channels:
            channel_map[ch.id] = ch

        ch_data = defaultdict(lambda: {'revenue': 0, 'orders': 0})
        for o in orders:
            cid = o.mc_channel_id.id
            ch_data[cid]['revenue'] += o.amount_total
            ch_data[cid]['orders'] += 1

        total_rev = sum(d['revenue'] for d in ch_data.values())
        data = []
        labels = []
        rev_vals = []
        ord_vals = []
        brand_colors = {'shopee': '#FF4500', 'tiktok': '#1f2937'}
        fallback_colors = ['#10b981', '#3b82f6', '#f59e0b']

        for idx, (cid, d) in enumerate(sorted(ch_data.items(), key=lambda x: x[1]['revenue'], reverse=True)):
            ch = channel_map.get(cid)
            name = ch.name if ch else f'Channel #{cid}'
            code = ch.code if ch else ''
            pct = (d['revenue'] / total_rev * 100) if total_rev else 0
            color = brand_colors.get(code)
            if not color:
                color = fallback_colors[idx % len(fallback_colors)] if code else '#6b7280'
            data.append({
                'name': name,
                'code': code,
                'revenue_raw': d['revenue'],
                'revenue_str': _fmt(d['revenue']),
                'orders': d['orders'],
                'percentage': round(pct, 1),
                'color': color,
            })
            labels.append(name)
            rev_vals.append(d['revenue'])
            ord_vals.append(d['orders'])

        return {
            'kpis': {
                'total_revenue_str': _fmt(total_rev),
                'total_channels': len(data),
                'top_channel': data[0]['name'] if data else '',
                'top_channel_pct': data[0]['percentage'] if data else 0,
            },
            'channels': data,
            'chart': {'labels': labels, 'revenue': rev_vals, 'orders': ord_vals},
        }

    # ── Best Selling Products ────────────────────────────────────────────────

    def _build_best_selling(self, start, end, platform):
        dom = _domain(platform, start, end) + [('state', 'not in', ('draft', 'sent', 'cancel'))]
        orders = self.env['sale.order'].search(dom)

        lines = self.env['sale.order.line'].search([
            ('order_id', 'in', orders.ids),
        ])

        prod_data = defaultdict(lambda: {'qty': 0, 'revenue': 0, 'orders': set()})
        for line in lines:
            if not line.product_id:
                continue
            pid = line.product_id.id
            prod_data[pid]['qty'] += line.product_uom_qty
            prod_data[pid]['revenue'] += line.price_subtotal
            prod_data[pid]['orders'].add(line.order_id.id)

        sorted_prods = sorted(prod_data.items(), key=lambda x: x[1]['revenue'], reverse=True)
        total_qty = sum(d['qty'] for _, d in sorted_prods)
        total_rev = sum(d['revenue'] for _, d in sorted_prods)

        products = []
        labels = []
        qty_vals = []
        rev_vals = []
        for rank, (pid, d) in enumerate(sorted_prods[:20], 1):
            product = self.env['product.product'].browse(pid)
            pct = (d['revenue'] / total_rev * 100) if total_rev else 0
            products.append({
                'rank': rank,
                'sku': product.default_code or '',
                'name': product.display_name,
                'qty': d['qty'],
                'revenue_raw': d['revenue'],
                'revenue_str': _fmt(d['revenue']),
                'orders': len(d['orders']),
                'percentage': round(pct, 1),
            })
            labels.append(product.default_code or product.display_name[:20])
            qty_vals.append(d['qty'])
            rev_vals.append(d['revenue'])

        return {
            'kpis': {
                'total_qty': total_qty,
                'total_revenue_str': _fmt(total_rev),
                'total_products': len(prod_data),
                'top_sku': products[0]['sku'] if products else '',
            },
            'products': products,
            'chart': {'labels': labels, 'qty': qty_vals, 'revenue': rev_vals},
        }

    # ── Inventory Report ─────────────────────────────────────────────────────

    def _build_inventory(self, start, end, platform):
        products = self.env['product.product'].search([
            ('type', '=', 'product'),
            ('mc_mapping_count', '>', 0),
        ])
        data = []
        total = len(products)
        low_stock = 0
        out_stock = 0
        in_stock = 0
        for p in products:
            status = 'in_stock'
            if p.virtual_available <= 0:
                status = 'out_of_stock'
                out_stock += 1
            elif p.virtual_available <= p.mc_low_stock_threshold:
                status = 'low_stock'
                low_stock += 1
            else:
                in_stock += 1

            data.append({
                'product_id': p.id,
                'sku': p.default_code or '',
                'name': p.display_name,
                'qty_on_hand': p.qty_available,
                'qty_reserved': p.virtual_available - p.qty_available,
                'qty_forecast': p.virtual_available,
                'low_stock_threshold': p.mc_low_stock_threshold,
                'buffer_qty': p.mc_buffer_qty,
                'stock_status': status,
            })

        return {
            'kpis': {
                'total_products': total,
                'in_stock': in_stock,
                'low_stock': low_stock,
                'out_of_stock': out_stock,
                'healthy_pct': round(in_stock / total * 100, 1) if total else 0,
            },
            'products': data,
            'stock_status': {
                'labels': ['Còn hàng', 'Sắp hết', 'Hết hàng'],
                'data': [in_stock, low_stock, out_stock],
            },
        }

    # ── Sync Status ──────────────────────────────────────────────────────────

    def _build_sync_status(self, start, end, platform):
        dom = [('is_active', '=', True)]
        if platform and platform != 'all':
            dom += [('channel_id.code', '=', platform)]
        mappings = self.env['mc.product.mapping'].search(dom)

        data = []
        total = len(mappings)
        synced = 0
        pending = 0
        error = 0
        for m in mappings:
            queue = self.env['mc.stock.sync.queue'].search([
                ('mapping_id', '=', m.id),
            ], order='create_date desc', limit=1)

            status = 'synced'
            if not queue:
                status = 'pending'
                pending += 1
            elif queue.state == 'done':
                status = 'synced'
                synced += 1
            elif queue.state == 'error':
                status = 'error'
                error += 1
            else:
                status = 'pending'
                pending += 1

            data.append({
                'mapping_id': m.id,
                'sku': m.external_sku,
                'channel': m.channel_id.name,
                'channel_code': m.channel_id.code,
                'product_name': m.product_id.display_name if m.product_id else '',
                'odoo_qty': m.product_id.qty_available if m.product_id else 0,
                'synced_qty': m.synced_qty,
                'last_synced_qty': m.last_synced_qty,
                'status': status,
                'last_sync': queue.last_attempt_at.strftime('%d/%m/%Y %H:%M') if queue and queue.last_attempt_at else '',
                'error_msg': queue.error_message if queue and queue.state == 'error' else '',
            })

        return {
            'kpis': {
                'total_mappings': total,
                'synced': synced,
                'pending': pending,
                'error': error,
                'healthy_pct': round(synced / total * 100, 1) if total else 0,
            },
            'mappings': data,
            'chart': {
                'labels': ['Đã đồng bộ', 'Chờ xử lý', 'Lỗi'],
                'data': [synced, pending, error],
            },
        }

    # ── Order Report ─────────────────────────────────────────────────────────

    def _build_order_list(self, start, end, platform):
        dom = _domain(platform, start, end) + [('state', 'not in', ('draft', 'sent'))]
        orders = self.env['sale.order'].search(dom, order='date_order desc')

        data = []
        status_map = {
            'draft': 'Nháp', 'sent': 'Đã gửi', 'sale': 'Đã xác nhận',
            'done': 'Hoàn thành', 'cancel': 'Đã hủy',
        }
        for o in orders:
            data.append({
                'id': o.id,
                'name': o.name,
                'date': o.date_order.strftime('%d/%m/%Y') if o.date_order else '',
                'channel': o.mc_channel_id.name if o.mc_channel_id else '',
                'channel_code': o.mc_channel_id.code if o.mc_channel_id else '',
                'customer': o.partner_id.name if o.partner_id else '',
                'total_raw': o.amount_total,
                'total_str': _fmt(o.amount_total),
                'state': o.state,
                'state_label': status_map.get(o.state, o.state),
                'mc_order_status': o.mc_order_status or '',
                'mc_payment_status': o.mc_payment_status or '',
                'external_order_id': o.mc_external_order_id or '',
            })

        status_counts = defaultdict(int)
        for o in orders:
            status_counts[o.state] += 1

        return {
            'kpis': {
                'total_orders': len(orders),
                'total_revenue_str': _fmt(sum(o.amount_total for o in orders if o.state != 'cancel')),
                'confirmed': status_counts.get('sale', 0) + status_counts.get('done', 0),
                'cancelled': status_counts.get('cancel', 0),
            },
            'orders': data,
            'order_status': {
                'labels': ['Đã xác nhận', 'Hoàn thành', 'Đã hủy'],
                'data': [status_counts.get('sale', 0), status_counts.get('done', 0), status_counts.get('cancel', 0)],
            },
        }

    # ── Insights & Summary ──────────────────────────────────────────────────

    @api.model
    def enrich_for_pdf(self, report_type, start, end, platform, kpis, channels=None, products=None, table=None):
        """Add Vietnamese prose-style executive summary and business insights."""
        summary = ''
        insights = ''

        if report_type in ('sales_summary', 'sales_channel', 'best_selling'):
            rev = kpis.get('total_revenue_str', '0')
            orders = kpis.get('total_orders', 0)
            aov = kpis.get('aov_str', '0')
            growth = kpis.get('growth', '0%')

            if orders:
                summary += f'Trong kỳ báo cáo, hệ thống ghi nhận {orders} đơn hàng hoàn thành với tổng doanh thu {rev} đồng. '
                summary += f'Giá trị trung bình mỗi đơn đạt {aov} đồng. '
                direction = 'tăng' if kpis.get('growth_up') else 'giảm' if growth != '0%' else 'ổn định so với'
                summary += f'Doanh thu {direction} kỳ trước ({growth}).'
            else:
                summary += 'Không có dữ liệu bán hàng trong kỳ báo cáo.'

            insights_parts = []
            if channels:
                top = channels[0]
                insights_parts.append(f'{top["name"]} đóng góp {top["percentage"]}% doanh thu')
                if len(channels) > 1:
                    insights_parts.append(f'{channels[1]["name"]} đóng góp {channels[1]["percentage"]}% doanh thu')
            if table:
                best = max(table, key=lambda r: r['revenue_raw'])
                insights_parts.append(f'Ngày có doanh thu cao nhất: {best["date"]}')
            if products:
                insights_parts.append(f'{products[0]["name"]} là sản phẩm bán chạy nhất với {products[0]["qty"]} lượt')

            if insights_parts:
                insights = 'Phân tích nhanh — ' + ', '.join(insights_parts) + '.'

        elif report_type == 'inventory':
            total = kpis.get('total_products', 0)
            in_s = kpis.get('in_stock', 0)
            low = kpis.get('low_stock', 0)
            out = kpis.get('out_of_stock', 0)
            pct = kpis.get('healthy_pct', 0)
            summary += f'Hệ thống đang quản lý {total} sản phẩm trên tất cả các kênh. '
            summary += f'Có {in_s} sản phẩm ({pct}%) đang còn hàng. '
            if low:
                insights += f'{low} sản phẩm sắp hết hàng, cần nhập bổ sung. '
            if out:
                insights += f'{out} sản phẩm đã hết hàng, cần xử lý ngay.'

        elif report_type == 'sync_status':
            total = kpis.get('total_mappings', 0)
            synced = kpis.get('synced', 0)
            err = kpis.get('error', 0)
            pct = kpis.get('healthy_pct', 0)
            summary += f'Hiện đang theo dõi {total} mapping sản phẩm giữa các kênh. '
            summary += f'{synced} mapping ({pct}%) đang đồng bộ thành công. '
            if err:
                insights += f'{err} mapping gặp lỗi, cần kiểm tra lại.'

        elif report_type == 'order_list':
            total = kpis.get('total_orders', 0)
            rev = kpis.get('total_revenue_str', '0')
            confirmed = kpis.get('confirmed', 0)
            cancelled = kpis.get('cancelled', 0)
            summary += f'Tổng số {total} đơn hàng đã được xử lý, tạo ra {rev} đồng doanh thu. '
            summary += f'{confirmed} đơn đã được xác nhận. '
            if cancelled:
                summary += f'{cancelled} đơn bị hủy ({round(cancelled/total*100, 1) if total else 0}% tỷ lệ hủy).'

        return {
            'executive_summary': summary,
            'business_insights': insights,
        }

    # ── Shared helpers ───────────────────────────────────────────────────────

    def _calc_trend(self, orders, start, end):
        days = (end - start).days or 1
        step = max(1, days // 31)
        trend = {}
        for i in range(days, -1, -step):
            dt = (end - timedelta(days=i)).strftime('%d/%m')
            trend[dt] = 0
        for o in orders:
            dt = (o.date_order or o.create_date).strftime('%d/%m')
            if dt in trend:
                trend[dt] += o.amount_total
        return {
            'labels': list(trend.keys()),
            'datasets': [{
                'label': 'Doanh thu',
                'data': list(trend.values()),
            }],
        }

    def _daily_summary(self, orders, start, end):
        days = (end - start).days or 1
        daily = {}
        for i in range(days, -1, -1):
            dt = (end - timedelta(days=i)).strftime('%d/%m/%Y')
            daily[dt] = {'revenue': 0, 'orders': 0}
        for o in orders:
            dt = (o.date_order or o.create_date).strftime('%d/%m/%Y')
            if dt in daily:
                daily[dt]['revenue'] += o.amount_total
                daily[dt]['orders'] += 1
        result = []
        for dt, d in daily.items():
            aov = d['revenue'] / d['orders'] if d['orders'] else 0
            result.append({
                'date': dt,
                'revenue_raw': d['revenue'],
                'revenue_str': _fmt(d['revenue']),
                'orders': d['orders'],
                'aov_str': _fmt(aov),
            })
        return result

    def _calc_growth(self, base_dom, start, end):
        period_len = (end - start).total_seconds()
        prev_end = start - timedelta(seconds=1)
        prev_start = prev_end - timedelta(seconds=period_len)
        prev_dom = list(base_dom) + [('date_order', '>=', prev_start), ('date_order', '<=', prev_end)]
        cur_orders = self.env['sale.order'].search(base_dom + [('date_order', '>=', start), ('date_order', '<=', end)])
        prev_orders = self.env['sale.order'].search(prev_dom)
        cur_rev = sum(cur_orders.mapped('amount_total'))
        prev_rev = sum(prev_orders.mapped('amount_total'))
        if not prev_rev:
            return 0, '+0%'
        growth = (cur_rev - prev_rev) / prev_rev * 100
        return growth, f"{'+' if growth >= 0 else ''}{growth:.1f}%"
