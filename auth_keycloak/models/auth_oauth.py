# Copyright 2018 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)
from odoo import fields, models, api, _
from dotenv import dotenv_values, load_dotenv
import logging
import os

_logger = logging.getLogger(__name__)

load_dotenv()


class OAuthProvider(models.Model):
    _inherit = 'auth.oauth.provider'

    client_secret = fields.Char()
    users_endpoint = fields.Char(
        help='User endpoint',
        default='http://localhost:8080/auth/admin/realms/master/users',
        required=False,
    )
    superuser = fields.Char(
        help='A super power user that is able to CRUD users on KC.',
        required=False,
    )
    superuser_pwd = fields.Char(
        help='"Superuser" user password',
        required=False,
    )
    users_management_enabled = fields.Boolean(
        compute='_compute_users_management_enabled'
    )
    allow_redirect = fields.Boolean(string="Auto Redirect", default=False)

    @api.depends(
        'enabled',
        'users_endpoint',
        'superuser',
        'superuser_pwd',
    )
    def _compute_users_management_enabled(self):
        for item in self:
            item.users_management_enabled = all([
                item.enabled,
                item.users_endpoint,
                item.superuser,
                item.superuser_pwd,
            ])

    def _set_keycloak_values(self):
        provider_id = self.env.ref('auth_keycloak.default_keycloak_provider')
        if provider_id:
            provider_id.write({
                'client_id': os.getenv('CLIENT_ID'),
                'client_secret': os.getenv('CLIENT_SECRET'),
                'auth_endpoint': os.getenv('AUTHENTICATION_URL'),
                'validation_endpoint': os.getenv('VALIDATION_URL'),
                'data_endpoint': os.getenv('DATA_URL'),
                'users_endpoint': os.getenv('USER_ENDPOINT'),
                'superuser': os.getenv('SUPER_USER'),
                'superuser_pwd': os.getenv('SUPER_USER_PASSWORD'),
                'enabled': True,
            })

            if os.getenv('AUTO_REDIRECT_KEYCLOAK') == 'True':
                provider_id.write({
                    'allow_redirect': True
                })
            else:
                provider_id.write({
                    'allow_redirect': False
                })

    def _auto_sync_keycloak_user(self):
        """
            Pass wizard params to auth.keycloak.sync.wiz
        """
        self.env['auth.keycloak.sync.wiz'].create({
            'provider_id': self.env.ref('auth_keycloak.default_keycloak_provider').id,
            'login_match_key': 'email:partner_id.email',
        }).button_sync()
