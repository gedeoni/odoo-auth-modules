# Copyright 2018 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

{
    "name": "Keycloak auth integration",
    "summary": "Integrate Keycloak into your SSO",
    "version": "14.0.1.1.2",
    'category': 'Tools',
    "website": "https://github.com/OCA/server-auth",
    'author': 'Camptocamp, Odoo Community Association (OCA)',
    "license": "AGPL-3",
    "description": """
        1.1 - Initial version\n
        1.2 - Added dotenv settings \n
    """,
    "external_dependencies": {
        'python': ['python-dotenv'],
    },
    "depends": [
        "auth_oauth",
        "web"
    ],
    "data": [
        'security/ir.model.access.csv',
        'data/auth_oauth_provider.xml',
        'wizard/keycloak_sync_wiz.xml',
        'wizard/keycloak_create_wiz.xml',
        'views/auth_oauth_views.xml',
        'views/res_users_views.xml',
        'views/login.xml',
        'data/cron.xml'
    ],
}
