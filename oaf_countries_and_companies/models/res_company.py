# -*- coding: utf-8 -*-

from odoo import models, fields, _


class Company(models.Model):
    _inherit = 'res.company'

    keycloak_loc_identifier = fields.Char(string="Location Identifier")