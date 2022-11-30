from odoo import api, fields, models


class CePortalSaleOrder(models.Model):
    _inherit = "sale.order"
    _description = "Ce_portal Sales Order"

    partner_bank_id = fields.Char(string='Bank number')

    order_status = fields.Selection([
        ('Active', 'Active'),
        ('Inactive', 'Inactive')],
        string='Order Status', default='Active')
