from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class OAFRoles(models.Model):
    _name = 'oaf.roles'
    _description = 'OAF Roles Mapping'

    def _default_groups(self):
        groups_id = [
            self.env.ref('base.group_user').id,
            self.env.ref('base.group_partner_manager').id,
        ]
        return groups_id

    name = fields.Char(string="Role Name")
    role_value = fields.Char(string="Role Value")
    groups_id = fields.Many2many('res.groups', 'oaf_roles_groups_rel', 'role', 'gid', string='Groups',
                                 default=_default_groups)
