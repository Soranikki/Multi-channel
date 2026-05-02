# -*- coding: utf-8 -*-
from odoo import fields, models


class McSyncLog(models.Model):
    _name = 'mc.sync.log'
    _description = 'Sync Log'
    _order = 'timestamp desc, id desc'

    channel_id = fields.Many2one('mc.channel', string='Channel', ondelete='set null', index=True)
    log_type = fields.Selection(
        selection=[('info', 'Info'), ('warning', 'Warning'), ('error', 'Error')],
        string='Type',
        required=True,
        default='info',
        index=True,
    )
    message = fields.Text(required=True)
    reference = fields.Char(help='External order ID or other identifier related to this log entry.')
    timestamp = fields.Datetime(default=fields.Datetime.now, required=True, index=True)

    @classmethod
    def _log(cls, env, log_type: str, message: str, channel_id: int | None = None, reference: str | None = None) -> None:
        env['mc.sync.log'].sudo().create({
            'log_type': log_type,
            'message': message,
            'channel_id': channel_id,
            'reference': reference,
        })
