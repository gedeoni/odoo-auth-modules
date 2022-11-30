# Copyright 2018 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

{
    "name": "OAF Roles",
    "summary": "OAF Roles",
    "version": "1.2",
    'category': "Sales/Point of Sale",
    "website": "https://oneacrefund.org/",
    'author': "Miracle",
    "license": "AGPL-3",
    "description": """
        OAF Roles Mapping with Odoo Modules and Available Groups
    """,
    "depends": [
        "oaf_countries_and_companies",
        "auth_keycloak",
        "sales_team",
        "account",
        "base",
        "stock",
        "purchase",
        "point_of_sale",
        "multi_shops",
        "oaf_stock_transfer"
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/data.xml",
        "views/roles_view.xml",
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
