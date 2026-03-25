# -*- coding: utf-8 -*-
# from odoo import http


# class SalesAnalysis(http.Controller):
#     @http.route('/sales_analysis/sales_analysis', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/sales_analysis/sales_analysis/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('sales_analysis.listing', {
#             'root': '/sales_analysis/sales_analysis',
#             'objects': http.request.env['sales_analysis.sales_analysis'].search([]),
#         })

#     @http.route('/sales_analysis/sales_analysis/objects/<model("sales_analysis.sales_analysis"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('sales_analysis.object', {
#             'object': obj
#         })

