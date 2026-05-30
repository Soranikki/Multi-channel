import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class McIntegrationService(models.Model):
    _name = 'mc.integration.service'
    _description = 'Integration Service'
    _order = 'sequence, name'

    name = fields.Char(string='Service Name', required=True)
    code = fields.Char(string='Service Code', required=True, index=True)
    base_url = fields.Char(string='Base URL', required=True, help='Full URL including protocol and port, e.g. http://odoo-ws-connector:8021')
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    description = fields.Text(string='Description')

    _sql_constraints = [
        ('unique_code', 'UNIQUE(code)', 'A service with this code already exists.'),
    ]

    @api.model
    def _get_service_url(self, code):
        svc = self.search([('code', '=', code), ('active', '=', True)], limit=1)
        if svc:
            return svc.base_url.rstrip('/')
        _logger.warning("No active integration service found for code: %s", code)
        return False
