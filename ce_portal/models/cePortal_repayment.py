from odoo import fields, models


class CePortalSaleOrder(models.Model):
    _inherit = "account.payment"
    _description = "Ce_portal Repaymet"

    group_code = fields.Char(string='group code')
    total_amount_repaid = fields.Char(string='total amount repaid')
    total_credit = fields.Char(string='total credit')
    display_name = fields.Char(string='display name')
