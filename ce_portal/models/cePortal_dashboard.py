import requests
import logging
from datetime import datetime, date
import json

from odoo import models, fields, api, _, exceptions
from odoo.exceptions import UserError

try:
    from json.decoder import JSONDecodeError
except ImportError:
    # py2
    JSONDecodeError = ValueError

_logger = logging.getLogger(__name__)


class CePortalClients(models.Model):
    _inherit = 'res.partner'
    _description = 'ce_portal Clients'

    is_ce_portal_open = fields.Boolean(
        default=True)
    display_client_account_number = fields.Boolean(
        string='Display Client Account number', compute="_compute_ce_portal_config")
    display_repayment_timestamp = fields.Boolean(
        string='Display Repayment Timestamp')
    display_client_first_name = fields.Boolean(
        string='Display Client First Name')
    display_client_last_name = fields.Boolean(
        string='Display Client Last Name')
    display_transaction_phone_number = fields.Boolean(
        string='Display Transaction Phone Number')
    display_primary_phone_number = fields.Boolean(
        string='Display Primary Phone Number')
    display_payment_amount = fields.Boolean(string='Display Payment Amount')
    display_MNO_transaction_code = fields.Boolean(
        string='Display MNO Transaction Code')
    display_aggregator_transaction_code = fields.Boolean(
        string='Display Aggregator Transaction Code')
    display_validation_status = fields.Boolean(
        string='Display Validation Status')
    display_loan_id = fields.Boolean(string='Display Loan ID')
    display_loan_name = fields.Boolean(string='Display Loan Name')

    @api.depends('is_ce_portal_open')
    def _compute_ce_portal_config(self):
        for item in self:
            config_parameter = self.env['ir.config_parameter']
            if item.is_ce_portal_open:
                item.display_client_account_number = config_parameter.get_param(
                    'display_client_account_number')
                item.display_repayment_timestamp = config_parameter.get_param(
                    'display_repayment_timestamp')
                item.display_client_first_name = config_parameter.get_param(
                    'display_client_first_name')
                item.display_client_last_name = config_parameter.get_param(
                    'display_client_last_name')
                item.display_transaction_phone_number = config_parameter.get_param(
                    'display_transaction_phone_number')
                item.display_primary_phone_number = config_parameter.get_param(
                    'display_primary_phone_number')
                item.display_MNO_transaction_code = config_parameter.get_param(
                    'display_MNO_transaction_code')
                item.display_aggregator_transaction_code = config_parameter.get_param(
                    'display_aggregator_transaction_code')
                item.display_validation_status = config_parameter.get_param(
                    'display_validation_status')
                item.display_loan_id = config_parameter.get_param(
                    'display_loan_id')
                item.display_loan_name = config_parameter.get_param(
                    'display_loan_name')
            else:
                item.display_client_account_number = False
                item.display_repayment_timestamp = False
                item.display_client_first_name = False
                item.display_client_last_name = False
                item.display_transaction_phone_number = False
                item.display_primary_phone_number = False
                item.display_MNO_transaction_code = False
                item.display_aggregator_transaction_code = False
                item.display_validation_status = False
                item.display_loan_id = False
                item.display_loan_name = False

    client_status = fields.Selection([
        ('Active', 'Active'),
        ('Inactive', 'Inactive')],
        string='Client Status', default='Inactive', compute='_set_client_status')

    @api.depends('active')
    def _set_client_status(self):
        for item in self:
            if item.active:
                item.client_status = 'Active'
            else:
                item.client_status = 'Inactive'

    first_name = fields.Char(string='First Name')
    last_name = fields.Char(string='Last Name')
    full_name = fields.Char(string='Full Name')
    national_id = fields.Char(string='National Id')
    activation_date = fields.Char(string='Activation Date')
    fineract_client_id = fields.Char(string='Fineract Id')
    gender = fields.Selection(selection=[
        ('Male', 'Male'),
        ('Female', 'Female'),
        ('Others', 'Others'),
    ])
    date_of_birth = fields.Date(index=True, string='Date of Birth')

    oaf_location = fields.Selection(selection=lambda self: self.env['fineract.methods'].get_oaf_countries(),
                                    string='OAF Location')
    rural_retail_outlet = fields.Selection([],
                                           string='Rural Retail Outlet')
    government_location = fields.Selection([],
                                           string='Government Location')

    co_insured = fields.One2many(
        'res.partner', 'parent_id', string='Co_insured', domain=[('active', '=', True)])

    beneficiaries = fields.One2many(
        'res.partner', 'parent_id', string='Beneficiaries', domain=[('active', '=', True)])

    type = fields.Selection(selection_add=[('Dependent', 'Dependent'),
                                           ('Co_insured', 'Co_insured'),
                                           ('Beneficiary', 'Beneficiary')
                                           ], string='Contact Type')

    contact_type = fields.Selection(
        [('contact', 'Contact'),
         ('Co_insured', 'Co_insured'),
         ('Dependent', 'Dependent'),
         ('Beneficiary', 'Beneficiary')
         ], string='Contact Type',
        default='contact',
        help="Client contact types.")

    @api.model
    def create(self, vals):
      try:
        contact_type = vals.get('contact_type')
        combined_name = f"{vals['first_name']} {vals['last_name']}"
        if contact_type == 'contact':
            response = self.env['fineract.methods'].save_new_client_to_fineract(vals)
            vals.update({
                "fineract_client_id": response.json()['clientId'],
                "is_customer": True
            })
            print('\n\n\n\n', response.json(), '\n\n\n\n', flush=True)
        vals.update({
            "client_status": "Active",
            "name": combined_name,
            "display_name": combined_name,
            "type": contact_type
        })
        return super(CePortalClients, self).create(vals)
      except Exception as e:
          _logger.warning(e)

    def write(self, vals):
      try:
        current_data = self.read()[0]
        new_vals = {}
        if vals:
          for index, key in enumerate(current_data.keys(), 1):
            new_vals[key] = current_data[key]
            if index == len(current_data.keys()):
              for value in vals.keys():
                new_vals[value] = vals[value]
        combined_name = f"{new_vals['first_name']} {new_vals['last_name']}"
        contact_type = new_vals['contact_type']
        vals.update({
          'name':combined_name,
          'display_name':combined_name,
          'type': contact_type
        })

        if current_data != new_vals and new_vals.get('fineract_client_id'):
            self.env['fineract.methods'].update_fineract_client_info(new_vals)
        return super(CePortalClients, self).write(vals)
      except Exception as e:
          _logger.warning(e)
