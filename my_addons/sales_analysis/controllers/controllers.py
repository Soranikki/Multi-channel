from odoo import _, http
from odoo.exceptions import AccessError, MissingError
from odoo.http import request


class SalesAnalysisController(http.Controller):
    def _get_preset(self, preset_id):
        preset = request.env['sales.analysis.preset'].browse(preset_id)
        if not preset.exists():
            raise MissingError(_('The requested sales analysis preset does not exist.'))
        preset.check_access_rights('read')
        preset.check_access_rule('read')
        return preset

    @http.route('/sales_analysis/preset/<int:preset_id>', type='http', auth='user')
    def preset_summary_page(self, preset_id, **kwargs):
        if not request.env.user.has_group('sales_analysis.group_sales_analysis_user'):
            raise AccessError(_('Access Denied'))
        preset = self._get_preset(preset_id)
        return request.render('sales_analysis.preset_summary', {
            'preset': preset,
            'summary': preset._get_summary_payload(),
            'overview_action_id': request.env.ref('sales_analysis.action_sales_analysis_overview').id,
        })

    @http.route('/sales_analysis/preset/<int:preset_id>/summary', type='json', auth='user')
    def preset_summary_json(self, preset_id, **kwargs):
        if not request.env.user.has_group('sales_analysis.group_sales_analysis_user'):
            raise AccessError(_('Access Denied'))
        preset = self._get_preset(preset_id)
        return preset._get_summary_payload()
