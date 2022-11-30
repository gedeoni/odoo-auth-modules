{
    'name': 'CE Portal',
    'version': '1.0',
    'summary': 'Application provides functionality to manage CE portal',
    'description': "1.0 - Initial version\n -This application implements the CE Portal through which client management occurs",
    "website": "https://oneacrefund.org/",
    'author': "Oluwasegun Adepoju",
    'email': 'oluwasegun.adepoju@oneacrefund.org',
    'category': 'ce portal',
    'depends': ['oaf_fineract_setup', 'sale', 'account', 'base'],
    'data': [
        'views/ce_portal_orders.xml',
        'views/ce_portal_invoice.xml',
        'views/ce_portal_repayment.xml',
        'views/ce_portal_client_management.xml',
    ],
    'qweb': [
        'static/src/xml/*.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'AGPL-3',
}
