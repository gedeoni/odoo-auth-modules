# Copyright 2018 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)
import logging
import requests
import json
import jwt

from odoo import api, models, exceptions, _
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
            if params['access_token']:
                self._assign_user_group(oauth_user, params['access_token'])
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

    def _assign_user_group(self, oauth_user, access_token):
        keycloak_roles = self._keycloak_read_odoo_roles(access_token=access_token)

        user_country_company_ids = self._keycloak_user_company_mapping(
            self._keycloak_read_odoo_company(access_token=access_token)
        )

        main_company = self.env.ref('base.main_company')
        portal_user_group_name = 'base.group_portal'
        user_group_name = 'base.group_user'

        if keycloak_roles:
            try:
                portal_user_group = self.env.ref(portal_user_group_name)
                user_group = self.env.ref(user_group_name)

                roles_groups = self._map_roles(roles=keycloak_roles)
                if portal_user_group.id in roles_groups and oauth_user.has_group(portal_user_group_name):
                    pass
                elif portal_user_group.id not in roles_groups and (
                        oauth_user.has_group(portal_user_group_name) or oauth_user.has_group(user_group_name)
                ):
                    groups_to_assign = list(roles_groups)
                    # Compulsory group
                    groups_to_assign.extend(
                        [self.env.ref('base.group_partner_manager').id, user_group.id]
                    )

                    if groups_to_assign:
                        user_vals = {'groups_id': [(6, 0, groups_to_assign)]}
                        if user_country_company_ids:
                            user_vals.update({
                                'company_ids': [(6, 0, user_country_company_ids)],
                                'company_id': user_country_company_ids[0]
                            })
                        else:
                            user_vals.update({
                                'company_ids': [(6, 0, [main_company.id])],
                                'company_id': main_company.id
                            })
                        oauth_user.write(user_vals)
                else:
                    oauth_user.write({'groups_id': [(4, portal_user_group.id)]})
            except AccessDenied as access_denied_exception:
                raise access_denied_exception

    def _map_roles(self, roles):
        roles_groups = []
        for role in roles:
            oaf_role_id = self.env['oaf.roles'].search([('role_value', '=', role)], limit=1)
            if oaf_role_id:
                roles_groups.extend(oaf_role_id.groups_id.ids)
        return set(roles_groups)

    def _keycloak_read_odoo_roles(self, access_token):
        decoded_values = jwt.decode(access_token, options={"verify_signature": False, "verify_aud": False})
        if decoded_values:
            available_roles = decoded_values['resource_access']['odoo'].get("roles")
            return available_roles

    def _keycloak_read_odoo_company(self, access_token):
        decoded_values = jwt.decode(access_token, options={"verify_signature": False, "verify_aud": False})
        if decoded_values:
            user_available_companies = decoded_values.get("odoo_company")
            if user_available_companies:
                return user_available_companies
            else:
                return False

    def _keycloak_user_company_mapping(self, company_country_roles):
        present_company_ids = []
        for country_loc in company_country_roles.split(','):
            company_id = self.env['res.company'].sudo().search([
                ('name', '=', country_loc.lstrip().strip().capitalize())], limit=1)
            if company_id:
                present_company_ids.append(company_id.id)
        if(len(present_company_ids)>0):
            return present_company_ids
        else:
            return False

    @api.model
    def signup(self, values, token=None):
        keycloak_roles = self._keycloak_read_odoo_roles(access_token=values.get('oauth_access_token'))

        user_country_company_ids = self._keycloak_user_company_mapping(
            self._keycloak_read_odoo_company(access_token=values.get('oauth_access_token'))
        )

        if keycloak_roles:
            roles_groups = self._map_roles(roles=keycloak_roles)
            if roles_groups:
                values.update({
                    'groups_id': [(4, group) for group in roles_groups],
                    'company_ids': [(6, 0, user_country_company_ids)],
                    'company_id': user_country_company_ids[0] if user_country_company_ids else False
                })
            else:
                values.update({
                    'groups_id': [(4, self.env.ref('base.group_user').id)],
                    'company_ids': [(6, 0, user_country_company_ids)],
                    'company_id': user_country_company_ids[0] if user_country_company_ids else False
                })
        """Update keycloak user password after signup"""
        ret = super(ResUsers, self).signup(values, token=token)
        user = self.env['res.users'].sudo().search(
            [('login', '=', ret[1])], limit=1)
        if 'password' in values and user and user.oauth_uid:
            user.update_user_pwd_keycloak(user.oauth_uid, values['password'])
        return ret
