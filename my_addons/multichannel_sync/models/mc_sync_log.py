# -*- coding: utf-8 -*-
from odoo import fields, models


class McSyncLog(models.Model):
    """
    Append-only processing and error log for the data pipeline.
    Records are created by the parser and processor — never edited manually.
    This provides an audit trail of every sync event, parse attempt, and error.
    """
    _name = 'mc.sync.log'
    _description = 'Sync Log'
    _order = 'timestamp desc, id desc'

    channel_id = fields.Many2one(
        comodel_name='mc.channel',
        string='Channel',
        ondelete='set null',
        index=True,
    )
    log_type = fields.Selection(
        selection=[
            ('info', 'Info'),
            ('warning', 'Warning'),
            ('error', 'Error'),
        ],
        string='Type',
        required=True,
        default='info',
        index=True,
    )
    message = fields.Text(
        string='Message',
        required=True,
    )
    reference = fields.Char(
        string='Reference',
        help='External order ID or other identifier related to this log entry.',
    )
    timestamp = fields.Datetime(
        string='Timestamp',
        required=True,
        default=fields.Datetime.now,
        index=True,
    )

    # ── Helper class method used by other models ──────────────────────────────

    @classmethod
    def _log(cls, env, log_type: str, message: str, channel_id: int = None, reference: str = None) -> None:
        """Convenience factory used across the pipeline to write log entries."""
        env['mc.sync.log'].sudo().create({
            'log_type': log_type,
            'message': message,
            'channel_id': channel_id,
            'reference': reference,
        })
