from odoo import fields, models


class McChannel(models.Model):
    _name = 'mc.channel'
    _description = 'Sales Channel'
    _order = 'sequence, name'

    name = fields.Char(string='Channel Name', required=True)
    code = fields.Char(string='Channel Code', required=True, index=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    description = fields.Text()
    platform_icon = fields.Binary(string='Platform Icon')
    platform_icon_filename = fields.Char(string='Icon Filename')
    last_sync_at = fields.Datetime(string='Last Sync At', readonly=True)
    last_sync_duration = fields.Float(string='Last Sync Duration (s)', digits=(8, 2), readonly=True)
    sync_status = fields.Selection(
        selection=[
            ('idle', 'Idle'),
            ('syncing', 'Syncing'),
            ('success', 'Success'),
            ('error', 'Error'),
        ],
        default='idle',
        readonly=True,
    )
    color = fields.Integer(default=0)

    _sql_constraints = [
        ('unique_code', 'UNIQUE(code)', 'A channel with this code already exists.'),
    ]

    def action_open_sync_logs(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Sync Logs - {self.name}',
            'res_model': 'mc.sync.log',
            'view_mode': 'tree,form',
            'domain': [('channel_id', '=', self.id)],
            'context': {'default_channel_id': self.id},
        }
