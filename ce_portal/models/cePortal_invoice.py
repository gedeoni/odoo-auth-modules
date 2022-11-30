from odoo import models, fields, api, _


class CePortalAccountInvoice(models.Model):
    _inherit = 'account.move'
    _description = "Ce_portal Invoice"

    client_phone_number = fields.Char(string='Phone Number')
