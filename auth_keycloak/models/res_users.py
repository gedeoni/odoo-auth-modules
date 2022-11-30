# Copyright 2018 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)
import logging
import requests
import json
import jwt

from odoo import api, models, exceptions, _
from ..exceptions import OAuthError
from odoo.exceptions import AccessDenied, UserError
from odoo.addons.auth_signup.models.res_users import SignupError

try:
    from json.decoder import JSONDecodeError
except ImportError:
    # py2
    JSONDecodeError = ValueError

logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = 'res.users'

    def _keycloak_validate(self, provider, access_token):
        """Validate token against Keycloak."""
        logger.debug('Calling: %s' % provider.validation_endpoint)

        headers = {
            'Authorization': 'Bearer %s' % access_token,
            'content-type': 'application/json'
        }
        resp = requests.get(provider.data_endpoint, headers=headers)

        if not resp.ok:
            raise OAuthError(resp.reason)

        validation = resp.json()
        if validation.get("error"):
            raise OAuthError(validation)
        logger.debug('Validation: %s' % str(validation))

        return validation

    @api.model
    def _auth_oauth_validate(self, provider, access_token):
        """Override to use authentication headers.

        The method `_auth_oauth_rpc` is not pluggable
        as you don't have the provider there.
        """
        # `provider` is `provider_id` actually... I'm respecting orig signature
        oauth_provider = self.env['auth.oauth.provider'].browse(provider)
        validation = self._keycloak_validate(oauth_provider, access_token)
        # clone keycloak ID expected by odoo into `user_id`
        validation['user_id'] = validation['sub']
        return validation

    def button_push_to_keycloak(self):
        """Quick action to push current users to Keycloak."""
        provider = self.env.ref(
            'auth_keycloak.default_keycloak_provider',
            raise_if_not_found=False
        )
        enabled = provider and provider.users_management_enabled
        if not enabled:
            raise exceptions.UserError(
                _('Keycloak provider not found or not configured properly.')
            )
        wiz = self.env['auth.keycloak.create.wiz'].create({
            'provider_id': provider.id,
            'user_ids': [(6, 0, self.ids)],
        })
        action = self.env.ref('auth_keycloak.keycloak_create_users').read()[0]
        action['res_id'] = wiz.id
        return action

    def _get_keycloak_token(self):
        self.ensure_one()
        """Retrieve auth token from Keycloak and return access_token"""
        provider_id = self.env.ref('auth_keycloak.default_keycloak_provider')
        url = provider_id.validation_endpoint.replace('/introspect', '')
        headers = {'content-type': 'application/x-www-form-urlencoded'}
        data = {
            'username': provider_id.superuser,
            'password': provider_id.superuser_pwd,
            'grant_type': 'password',
            'client_id': provider_id.client_id,
            'client_secret': provider_id.client_secret,
        }
        resp = requests.post(url, data=data, headers=headers)
        self._validate_response(resp)
        return resp.json()['access_token']

    def _validate_response(self, resp, no_json=False):
        """Make sure Keycloak answered properly."""
        if not resp.ok:
            # TODO: do something better?
            raise resp.raise_for_status()
        if no_json:
            return resp.content
        try:
            return resp.json()
        except JSONDecodeError:
            raise exceptions.UserError(
                _('Something went wrong. Please check logs.')
            )

    def update_user_pwd_keycloak(self, oauth_uid, pwd):
        token = self._get_keycloak_token()
        provider_id = self.env.ref('auth_keycloak.default_keycloak_provider')
        """Update keycloak user pwd"""
        logger.info('Calling %s' % provider_id.users_endpoint)
        update_pwd_url = "%s/%s/reset-password" % (
            provider_id.users_endpoint, oauth_uid)
        headers = {
            'Authorization': 'Bearer %s' % token,
            'content-type': 'application/json'
        }
        data = {
            "type": "password",
            "temporary": "false",
            "value": pwd
        }
        resp = requests.put(update_pwd_url, json=data, headers=headers)
        return resp

    def enable_disable_user_keycloak(self, oauth_uid, enabled):
        token = self._get_keycloak_token()
        provider_id = self.env.ref('auth_keycloak.default_keycloak_provider')
        """Update keycloak state:enabled/disabled"""
        logger.info('Calling %s' % provider_id.users_endpoint)
        update_enable_url = "%s/%s" % (provider_id.users_endpoint, oauth_uid)
        headers = {
            'Authorization': 'Bearer %s' % token,
            'content-type': 'application/json'
        }
        data = {
            "enabled": enabled
        }
        resp = requests.put(update_enable_url, json=data, headers=headers)
        return resp

    @api.model
    def signup(self, values, token=None):
        """Update keycloak user password after signup"""
        ret = super(ResUsers, self).signup(values, token=token)
        user = self.env['res.users'].sudo().search(
            [('login', '=', ret[1])], limit=1)
        if 'password' in values and user and user.oauth_uid:
            user.update_user_pwd_keycloak(user.oauth_uid, values['password'])
        return ret

    def write(self, vals):
        """When activate/deactivate/archive user, update also keycloak user
        state"""
        ret = super(ResUsers, self).write(vals)
        for user in self:
            if 'active' in vals and user.oauth_uid:
                user.enable_disable_user_keycloak(user.oauth_uid, vals['active'])
        return ret

    @api.model
    def _auth_oauth_signin(self, provider, validation, params):
        """ retrieve and sign in the user corresponding to provider and validated access token
            :param provider: oauth provider id (int)
            :param validation: result of validation of access token (dict)
            :param params: oauth parameters (dict)
            :return: user login (str)
            :raise: AccessDenied if signin failed

            This method can be overridden to add alternative signin methods.
        """
        oauth_uid = validation['user_id']
        try:
            oauth_user = self.search([("oauth_uid", "=", oauth_uid), ('oauth_provider_id', '=', provider)])
            if not oauth_user:
                raise AccessDenied()
            assert len(oauth_user) == 1
            oauth_user.write({'oauth_access_token': params['access_token']})
            return oauth_user.login
        except AccessDenied as access_denied_exception:
            if self.env.context.get('no_user_creation'):
                return None
            state = json.loads(params['state'])
            token = state.get('t')
            values = self._generate_signup_values(provider, validation, params)
            try:
                _, login, _ = self.signup(values, token)
                return login
            except (SignupError, UserError):
                raise access_denied_exception


class ChangePasswordUser(models.TransientModel):
    """ A wizard to manage the change of users' passwords.
    Update Keycloak user passwords"""
    _inherit = "change.password.user"

    def change_password_button(self):
        for line in self:
            if not line.new_passwd:
                raise UserError("Before clicking on 'Change Password',"
                                " you have to write a new password.")
            line.user_id.write({'password': line.new_passwd})
            if line.user_id.oauth_uid:
                line.user_id.update_user_pwd_keycloak(
                    line.user_id.oauth_uid, line.new_passwd)

        # don't keep temporary passwords in the database longer than necessary
        self.write({'new_passwd': False})
