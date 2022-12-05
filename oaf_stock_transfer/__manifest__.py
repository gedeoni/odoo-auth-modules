{
    "name": "OAF Stock Transfer",
    "summary": "OAF Stock Transfer",
    "version": "1.0",
    'category': "Customization",
    "website": "https://oneacrefund.org/",
    'author': "Robert Mauti",
    "email":"roberts.mauti@oneacrefund.org",
    "license": "AGPL-3",
    "description": """
        1.0 - Initial version\n

    """,
    "depends": [
        "point_of_sale",'multi_shops'
    ],
    "data": [
        'security/security.xml',
        'views/stock_view.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': True,
    'license': 'LGPL-3',
}