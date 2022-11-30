# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging

import json

import uuid

import werkzeug.urls
import werkzeug.utils

import requests

from odoo.addons.auth_oauth.controllers.main import OAuthLogin
from odoo.addons.web.controllers.main import Home

from odoo import http, _
from odoo.http import request
from werkzeug.urls import url_quote_plus
from werkzeug.urls import url_encode

from odoo.exceptions import UserError

try:
    from json.decoder import JSONDecodeError
except ImportError:
    # py2
    JSONDecodeError = ValueError

_logger = logging.getLogger(__name__)


# ----------------------------------------------------------
# Controller
# ----------------------------------------------------------
class OAuthLoginKeycloak(OAuthLogin):
    def list_providers(self):
        try:
            providers = request.env['auth.oauth.provider'].sudo().search_read(
                [('enabled', '=', True)]
            )
        except Exception:
            providers = []
        for provider in providers:
            # return_url = request.httprequest.url_root + 'auth_oauth/signin'
            return_url = 'http://' + request.httprequest.host + '/auth_oauth/signin'
            state = self.get_state(provider)
            params = dict(
                response_type='token',
                client_id=provider['client_id'],
                redirect_uri=return_url,
                # scope=provider['scope'],
                state=json.dumps(state),
                # a nonce is mandatory for keycloak
                # otherwise it returns a Bad Request code
                # see https://tools.ietf.org/html/rfc6819
                nonce=str(uuid.uuid4()),
            )
            provider['auth_link'] = "%s?%s" % (
                provider['auth_endpoint'],
                url_encode(params)
            )
        return providers


#----------------------------------------------------------
# Odoo Web web Controllers
#----------------------------------------------------------
class LoginHome(Home):

    @http.route('/web/login', type='http', auth="none")
    def web_login(self, redirect=None, **kw):
        def get_state(provider):
            redirect = request.params.get('redirect') or 'web'
            if not redirect.startswith(('//', 'http://', 'https://')):
                redirect = '%s%s' % (request.httprequest.url_root,
                                     redirect[1:] if redirect[0] == '/' else redirect)
            state = dict(
                d=request.session.db,
                p=provider['id'],
                r=url_quote_plus(redirect),
            )
            token = request.params.get('token')
            if token:
                state['t'] = token
            return state
        if request.uid:
            return super(LoginHome, self).web_login(redirect, **kw)
        else:
            # provider = request.env.ref('auth_keycloak.default_keycloak_provider').sudo()
            provider = request.env['auth.oauth.provider'].sudo().search([('enabled', '=', True)], limit=1)
            return_url = 'http://' + request.httprequest.host + '/auth_oauth/signin'
            state = get_state(provider)
            params = dict(
                response_type='token',
                client_id=provider['client_id'],
                redirect_uri=return_url,
                # scope=provider['scope'],
                state=json.dumps(state),
                # a nonce is mandatory for keycloak
                # otherwise it returns a Bad Request code
                # see https://tools.ietf.org/html/rfc6819
                nonce=str(uuid.uuid4()),
            )
            auth_link = "%s?%s" % (
                provider['auth_endpoint'],
                url_encode(params)
            )
            if 'normal_login' in request.httprequest.url:
                return super(LoginHome, self).web_login(redirect, **kw)
            else:
                if provider.allow_redirect:
                    return werkzeug.utils.redirect(auth_link)
                else:
                    return super(LoginHome, self).web_login(redirect, **kw)

    def _get_keycloak_token(self):
        """Retrieve auth token from Keycloak and return access_token"""
        # provider_id = request.env.ref('auth_keycloak.default_keycloak_provider')
        provider_id = request.env['auth.oauth.provider'].sudo().search([('enabled', '=', True)], limit=1)
        url = provider_id.sudo().validation_endpoint.replace('/introspect', '')
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
        return resp.json()

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
            raise UserError(
                _('Something went wrong. Please check logs.')
            )

    @http.route('/web/session/logout', type='http', auth="user")
    def logout(self, redirect='/web'):
        # provider_id = request.env.ref('auth_keycloak.default_keycloak_provider')
        provider_id = request.env['auth.oauth.provider'].sudo().search([('enabled', '=', True)], limit=1)
        if provider_id:
            try:
                url = '%s/%s/logout' % (provider_id.sudo().users_endpoint, request.env.user.oauth_uid)
                headers = {
                    'Authorization': 'Bearer %s' % self._get_keycloak_token()['access_token'],
                    'Content-Type': 'application/x-www-form-urlencoded'
                }
                requests.post(url, headers=headers)
            except Exception as e:
                pass
        request.session.logout(keep_db=True)
        return werkzeug.utils.redirect(redirect, 303)
