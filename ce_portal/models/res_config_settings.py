# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    oaf_location_list = fields.Char('OAF Location', config_parameter='oaf_location_list')
