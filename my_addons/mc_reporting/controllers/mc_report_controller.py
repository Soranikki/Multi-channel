import json, math
from datetime import datetime

from odoo import http
from odoo.http import request


class DictObj:
    def __init__(self, d):
        for k, v in d.items():
            if isinstance(v, dict):
                self.__dict__[k] = DictObj(v)
            elif isinstance(v, list):
                self.__dict__[k] = [DictObj(i) if isinstance(i, dict) else i for i in v]
            else:
                self.__dict__[k] = v


class McReportExport(http.Controller):

    _REPORT_NAMES = {
        'sales_summary': 'BÁO CÁO TỔNG HỢP BÁN HÀNG',
        'sales_channel': 'BÁO CÁO BÁN HÀNG THEO KÊNH',
        'best_selling': 'BÁO CÁO SẢN PHẨM BÁN CHẠY',
        'inventory': 'BÁO CÁO TỒN KHO',
        'sync_status': 'BÁO CÁO ĐỒNG BỘ TỒN KHO',
        'order_list': 'BÁO CÁO DANH SÁCH ĐƠN HÀNG',
    }

    _SHEET_TITLES = {
        'sales_summary': 'TK Ban Hang',
        'sales_channel': 'Ban Hang Theo Kenh',
        'best_selling': 'SP Ban Chay',
        'inventory': 'Ton Kho',
        'sync_status': 'Dong Bo Ton Kho',
        'order_list': 'Danh Sach Don Hang',
    }

    # ── Data ────────────────────────────────────────────────────────────

    def _get_data(self, **params):
        return request.env['mc.report.engine'].get_report_data(
            params['report_type'], params.get('date_range', '30d'),
            params.get('platform', 'all'),
            params.get('custom_start') or False,
            params.get('custom_end') or False,
        )

    def _fmt(self, v):
        if v >= 1_000_000_000: return f"{v / 1_000_000_000:.1f}B"
        if v >= 1_000_000: return f"{v / 1_000_000:.1f}M"
        if v >= 1_000: return f"{v / 1_000:.1f}K"
        return str(round(v))

    # ── SVG Charts ──────────────────────────────────────────────────────

    def _svg_line_chart(self, labels, values, w=700, h=200):
        if not labels or not values:
            return '<p style="color:#94a3b8;text-align:center;">No data</p>'
        mx = max(values) or 1
        pad_l, pad_r, pad_t, pad_b = 45, 15, 20, 30
        cw, ch = w - pad_l - pad_r, h - pad_t - pad_b

        def x(i): return pad_l + (i / (len(labels) - 1)) * cw if len(labels) > 1 else pad_l + cw / 2
        def y(v): return pad_t + ch - (v / mx) * ch * 0.85

        pts = ' '.join(f'{x(i)},{y(v)}' for i, v in enumerate(values))
        grid = ''
        for gi in range(5):
            gy = pad_t + ch * gi / 4
            gv = mx - mx * gi / 4 * 0.85
            grid += f'<line x1="{pad_l}" y1="{gy}" x2="{pad_l+cw}" y2="{gy}" stroke="#e2e8f0" stroke-width="0.5"/>'
            grid += f'<text x="{pad_l-5}" y="{gy+3}" text-anchor="end" font-size="7" fill="#64748b">{self._fmt(gv)}</text>'

        x_labels = ''
        step = max(1, len(labels) // 10)
        for i in range(0, len(labels), step):
            x_labels += f'<text x="{x(i)}" y="{h-5}" text-anchor="middle" font-size="6" fill="#94a3b8" transform="rotate(-30,{x(i)},{h-5})">{labels[i]}</text>'

        return f'''<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg">
            {grid}
            <polyline points="{pts}" fill="none" stroke="#2563eb" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            <circle cx="{pts.split(' ')[0].split(',')[0]}" cy="{pts.split(' ')[0].split(',')[1]}" r="3" fill="#2563eb"/>
            <circle cx="{pts.split(' ')[-1].split(',')[0]}" cy="{pts.split(' ')[-1].split(',')[1]}" r="3" fill="#2563eb"/>
            {x_labels}
        </svg>'''

    def _svg_bar_chart(self, labels, values, colors, w=800, h=180):
        if not labels or not values:
            return '<p style="color:#94a3b8;text-align:center;">No data</p>'
        mx = max(values) or 1
        pad_l, pad_r, pad_t, pad_b = 50, 20, 15, 40
        cw, ch = w - pad_l - pad_r, h - pad_t - pad_b
        bw = min(60, (cw - (len(labels) - 1) * 20) / len(labels))
        gap = (cw - bw * len(labels)) / (len(labels) + 1)

        bars = ''
        for i, (lb, v, c) in enumerate(zip(labels, values, colors)):
            bx = pad_l + gap + i * (bw + gap)
            bh = (v / mx) * ch * 0.85
            by = pad_t + ch - bh
            bars += f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" rx="3" fill="{c}" opacity="0.85"/>'
            bars += f'<text x="{bx+bw/2}" y="{by-5}" text-anchor="middle" font-size="8" font-weight="bold" fill="#1e293b">{self._fmt(v)}</text>'
            bars += f'<text x="{bx+bw/2}" y="{h-5}" text-anchor="middle" font-size="7" fill="#64748b">{lb}</text>'

        return f'''<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg">
            <line x1="{pad_l}" y1="{pad_t}" x2="{pad_l}" y2="{pad_t+ch}" stroke="#e2e8f0" stroke-width="0.5"/>
            {bars}
        </svg>'''

    def _svg_hbar_chart(self, labels, values, colors, w=800, h=130):
        if not labels or not values:
            return '<p style="color:#94a3b8;text-align:center;">No data</p>'
        mx = max(values) or 1
        pad_l, pad_r, pad_t, pad_b = 80, 100, 15, 20
        cw, ch = w - pad_l - pad_r, h - pad_t - pad_b
        bh = min(30, (ch - (len(labels) - 1) * 8) / len(labels))
        gap = (ch - bh * len(labels)) / (len(labels) + 1)

        bars = ''
        for i, (lb, v, c) in enumerate(zip(labels, values, colors)):
            by = pad_t + gap + i * (bh + gap)
            bw = (v / mx) * cw * 0.9
            pct = round(v / mx * 100, 1) if mx else 0
            bars += f'<rect x="{pad_l}" y="{by}" width="{bw}" height="{bh}" rx="4" fill="{c}" opacity="0.85"/>'
            bars += f'<text x="{pad_l-6}" y="{by+bh/2+2}" text-anchor="end" font-size="8" font-weight="bold" fill="#334155">{lb}</text>'
            bars += f'<text x="{pad_l+bw+6}" y="{by+bh/2+2}" text-anchor="start" font-size="8" fill="#64748b">{self._fmt(v)}</text>'

        return f'''<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg">
            {bars}
        </svg>'''

    # ── PDF Export ──────────────────────────────────────────────────────

    @http.route('/mc/report/pdf/<report_type>', type='http', auth='user')
    def export_pdf(self, report_type, date_range='30d', platform='all',
                   custom_start='', custom_end='', **kw):
        data = self._get_data(
            report_type=report_type, date_range=date_range,
            platform=platform, custom_start=custom_start, custom_end=custom_end,
        )
        data = self._enrich(data, report_type, date_range, platform)

        html = request.env['ir.qweb']._render(
            f'mc_reporting.pdf_{report_type}', {'doc': DictObj(data)},
        )

        pf = request.env.ref('mc_reporting.paperformat_mc_report', raise_if_not_found=False)
        pf_args = {}
        if pf:
            pf_args = {
                'data-report-margin-top': pf.margin_top,
                'data-report-margin-bottom': pf.margin_bottom,
                'data-report-margin-left': pf.margin_left,
                'data-report-margin-right': pf.margin_right,
                'data-report-header-spacing': pf.header_spacing,
                'data-report-header-line': pf.header_line,
            }

        pdf = request.env['ir.actions.report']._run_wkhtmltopdf(
            [html], landscape=True, specific_paperformat_args=pf_args,
        )

        fn = f'{report_type}_{datetime.now().strftime("%Y%m%d_%H%M")}.pdf'
        return request.make_response(pdf, headers=[
            ('Content-Type', 'application/pdf'),
            ('Content-Disposition', f'attachment; filename="{fn}"'),
        ])

    def _enrich(self, data, report_type, date_range, platform):
        now = datetime.now()
        loc = {'today': 'Hôm nay', '7d': '7 ngày qua', '30d': '30 ngày qua',
               '90d': '90 ngày qua', '1y': '1 năm qua', 'custom': 'Tùy chỉnh'}
        loc_en = {'today': 'Today', '7d': 'Last 7 Days', '30d': 'Last 30 Days',
                  '90d': 'Last 90 Days', '1y': 'Last Year', 'custom': 'Custom Period'}
        plat_names = {'all': 'Tất cả kênh', 'shopee': 'Shopee', 'tiktok': 'TikTok Shop'}

        data['title'] = self._REPORT_NAMES.get(report_type, report_type)
        data['date_label'] = loc.get(date_range, date_range)
        data['date_label_en'] = loc_en.get(date_range, date_range)
        data['platform_label'] = plat_names.get(platform, platform)
        data['generated_at'] = now.strftime('%d/%m/%Y %H:%M')
        data['generated_by'] = request.env.user.name or 'Administrator'
        data['report_type'] = report_type
        data['company_name'] = request.env.company.name or 'Multi-Channel System'

        # Executive summary + insights
        enrich = request.env['mc.report.engine'].enrich_for_pdf(
            report_type, None, None, platform,
            data.get('kpis', {}),
            channels=data.get('channels'),
            products=data.get('products'),
            table=data.get('table'),
        )
        data.update(enrich)

        # SVG charts — full width, stacked
        data['svg_trend'] = ''
        data['svg_channel'] = ''
        data['svg_hbar'] = ''

        if report_type in ('sales_summary', 'sales_channel', 'best_selling', 'order_list'):
            # Revenue trend line chart (full width)
            trend = data.get('trend', {})
            if trend.get('labels') and trend.get('datasets'):
                data['svg_trend'] = self._svg_line_chart(
                    trend['labels'], trend['datasets'][0]['data'],
                )

            # Channel / product bar chart (full width)
            ch_data = data.get('chart') or data.get('channels')
            if ch_data and isinstance(ch_data, dict) and ch_data.get('labels'):
                channels_lookup = {c['name']: c.get('color', '#2563eb') for c in data.get('channels', [])}
                colors = [channels_lookup.get(lb, '#2563eb') for lb in ch_data['labels']]
                data['svg_channel'] = self._svg_bar_chart(
                    ch_data['labels'], ch_data.get('revenue', ch_data.get('data', [])),
                    colors,
                )
            elif ch_data and isinstance(ch_data, list):
                data['svg_channel'] = self._svg_bar_chart(
                    [c['name'] for c in ch_data],
                    [c.get('revenue_raw', c.get('qty', 0)) for c in ch_data],
                    [c.get('color', '#2563eb') for i, c in enumerate(ch_data)],
                )

        # Revenue by Channel horizontal bar for all sales reports
        channels = data.get('channels', [])
        if channels:
            data['svg_hbar'] = self._svg_hbar_chart(
                [c['name'] for c in channels],
                [c.get('revenue_raw', 0) for c in channels],
                [c.get('color', '#2563eb') for c in channels],
            )

        # Table totals
        table = data.get('table', [])
        if table:
            tr = sum(r.get('revenue_raw', 0) for r in table)
            to = sum(r.get('orders', 0) for r in table)
            ta = tr / to if to else 0
            data['total_row'] = {'revenue_str': self._fmt(tr), 'orders': to, 'aov_str': self._fmt(ta)}
        elif report_type == 'order_list' and data.get('orders'):
            orders = data['orders']
            tr = sum(o.get('total_raw', 0) for o in orders)
            to = len(orders)
            ta = tr / to if to else 0
            data['total_row'] = {'revenue_str': self._fmt(tr), 'orders': to, 'aov_str': self._fmt(ta)}
        elif report_type == 'best_selling' and data.get('products'):
            prods = data['products']
            tr = sum(p.get('revenue_raw', 0) for p in prods)
            tq = sum(p.get('qty', 0) for p in prods)
            data['total_row'] = {'revenue_str': self._fmt(tr), 'qty': tq}

        return data

    # ── XLSX Export ─────────────────────────────────────────────────────

    @http.route('/mc/report/xlsx/<report_type>', type='http', auth='user')
    def export_xlsx(self, report_type, date_range='30d', platform='all',
                    custom_start='', custom_end='', **kw):
        import io
        import xlsxwriter

        now = datetime.now()
        data = self._get_data(
            report_type=report_type, date_range=date_range,
            platform=platform, custom_start=custom_start, custom_end=custom_end,
        )

        out = io.BytesIO()
        wb = xlsxwriter.Workbook(out, {'in_memory': True})

        t_fmt = wb.add_format({'bold': True, 'font_size': 16, 'font_color': '#1f2937',
                                'bottom': 2, 'bottom_color': '#e5e7eb', 'valign': 'vcenter'})
        s_fmt = wb.add_format({'italic': True, 'font_size': 10, 'font_color': '#6b7280'})
        h_fmt = wb.add_format({'bold': True, 'font_size': 11, 'bg_color': '#f3f4f6',
                                'border': 1, 'border_color': '#d1d5db', 'text_wrap': True,
                                'valign': 'vcenter', 'align': 'center'})
        c_fmt = wb.add_format({'font_size': 10, 'border': 1, 'border_color': '#d1d5db'})
        m_fmt = wb.add_format({'font_size': 10, 'border': 1, 'border_color': '#d1d5db', 'num_format': '#,##0'})
        kl = wb.add_format({'bold': True, 'font_size': 10, 'font_color': '#6b7280'})
        kv = wb.add_format({'bold': True, 'font_size': 14, 'font_color': '#1f2937'})

        ws = wb.add_worksheet((self._SHEET_TITLES.get(report_type) or report_type)[:31])
        ws.set_landscape()
        ws.set_margins(0.5, 0.5, 0.5, 0.5)
        ws.set_column('A:A', 20)
        ws.set_column('B:B', 18)
        ws.set_column('C:C', 18)
        ws.set_column('D:D', 18)
        ws.set_column('E:E', 18)
        ws.set_column('F:F', 18)

        row = 0
        ws.merge_range(row, 0, row, 5, self._REPORT_NAMES.get(report_type, report_type), t_fmt)
        row += 1
        dl = {'today': 'Hôm nay', '7d': '7 ngày qua', '30d': '30 ngày qua',
              '90d': '90 ngày qua', '1y': '1 năm qua', 'custom': 'Tùy chỉnh'}
        pl = platform if platform != 'all' else 'Tất cả kênh'
        ws.merge_range(row, 0, row, 5,
                       f'Khoảng: {dl.get(date_range, date_range)} | Kênh: {pl} | Xuất: {now.strftime("%d/%m/%Y %H:%M")}',
                       s_fmt)
        row += 2

        kpis = data.get('kpis', {})
        kc = {
            'sales_summary': [('Tổng doanh thu', 'total_revenue_str'), ('Số đơn hàng', 'total_orders'),
                              ('Giá trị TB/Đơn', 'aov_str'), ('Tăng trưởng', 'growth')],
            'sales_channel': [('Tổng doanh thu', 'total_revenue_str'), ('Số kênh', 'total_channels'),
                              ('Kênh cao nhất', 'top_channel'), ('Tỷ trọng', 'top_channel_pct')],
            'best_selling': [('Tổng SP đã bán', 'total_qty'), ('Tổng doanh thu', 'total_revenue_str'),
                             ('Số SP', 'total_products'), ('Top SKU', 'top_sku')],
            'inventory': [('Tổng SP', 'total_products'), ('Còn hàng', 'in_stock'),
                          ('Sắp hết', 'low_stock'), ('Hết hàng', 'out_of_stock')],
            'sync_status': [('Tổng mapping', 'total_mappings'), ('Đã đồng bộ', 'synced'),
                            ('Chờ xử lý', 'pending'), ('Lỗi', 'error')],
            'order_list': [('Tổng đơn', 'total_orders'), ('Doanh thu', 'total_revenue_str'),
                           ('Đã xác nhận', 'confirmed'), ('Đã hủy', 'cancelled')],
        }
        for i, (lb, k) in enumerate(kc.get(report_type, [])):
            v = kpis.get(k, '')
            vs = f'{v:,.0f}' if isinstance(v, float) else str(v) if v is not None else ''
            r = row if i < 4 else row + 1
            ws.write(r, (i % 4) * 2, lb, kl)
            ws.write(r, (i % 4) * 2 + 1, vs, kv)
        row += 3 if len(kc.get(report_type, [])) <= 4 else 4

        tm = {
            'sales_summary': {'h': ['Ngày', 'Doanh thu', 'Số đơn', 'TB/Đơn'],
                              'r': [(r['date'], r['revenue_raw'], r['orders'], r['aov_str']) for r in data.get('table', [])]},
            'sales_channel': {'h': ['Kênh', 'Doanh thu', 'Số đơn', 'Tỷ trọng (%)'],
                              'r': [(c['name'], c['revenue_raw'], c['orders'], c['percentage']) for c in data.get('channels', [])]},
            'best_selling': {'h': ['#', 'SKU', 'Tên SP', 'SL bán', 'Doanh thu', 'Đơn hàng', '%'],
                             'r': [(p['rank'], p['sku'], p['name'], p['qty'], p['revenue_raw'], p['orders'], p['percentage']) for p in data.get('products', [])]},
            'inventory': {'h': ['SKU', 'Tên SP', 'Tồn kho', 'Đã đặt', 'Dự báo', 'Trạng thái'],
                          'r': [(p['sku'], p['name'], p['qty_on_hand'], p['qty_reserved'], p['qty_forecast'], p['stock_status']) for p in data.get('products', [])]},
            'sync_status': {'h': ['SKU', 'Kênh', 'Tồn Odoo', 'Đã đồng bộ', 'Trạng thái', 'Lần cuối'],
                            'r': [(m['sku'], m['channel'], m['odoo_qty'], m['synced_qty'], m['status'], m['last_sync']) for m in data.get('mappings', [])]},
            'order_list': {'h': ['Mã đơn', 'Ngày', 'Kênh', 'Khách hàng', 'Tổng tiền', 'Trạng thái'],
                           'r': [(o['name'], o['date'], o['channel'], o['customer'], o['total_raw'], o['state_label']) for o in data.get('orders', [])]},
        }
        t = tm.get(report_type)
        if t:
            for ci, h in enumerate(t['h']):
                ws.write(row, ci, h, h_fmt)
            row += 1
            for line in t['r']:
                for ci, v in enumerate(line):
                    ws.write(row, ci, v, m_fmt if isinstance(v, float) else c_fmt)
                row += 1

        wb.close()
        out.seek(0)
        fn = f'{report_type}_{now.strftime("%Y%m%d_%H%M")}.xlsx'
        return request.make_response(out.getvalue(), headers=[
            ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
            ('Content-Disposition', f'attachment; filename="{fn}"'),
        ])
