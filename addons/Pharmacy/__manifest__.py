# -*- coding: utf-8 -*-
{
    "name": "MediZano - ERP de Farmacia y Botica (Perú)",
    "version": "18.0.1.0.0",
    "category": "Pharmacy",
    "summary": "Sistema ERP Integral de Botica y Farmacia adaptado a Perú",
    "description": """
MediZano - Sistema ERP de Farmacia y Botica para Odoo 18
=========================================================

Sistema integral de gestión para boticas y farmacias en Perú:
- Gestión multisucursal con aislamiento de inventario por botica
- Control de lotes y fechas de vencimiento con método FEFO obligatorio
- Punto de venta (POS) farmacéutico con receta médica y productos controlados
- Billeteras digitales peruanas (Yape / Plin), efectivo y tarjetas
- Preparado para Facturación Electrónica SUNAT (Boletas, Facturas, NC/ND)
- Impuestos peruanos: IGV 18% y medicamentos exonerados (Ley 29459)
- Compras, recepción y control de mermas/discrepancias
    """,
    "author": "MediZano",
    "website": "https://www.medizano.pe",
    "license": "LGPL-3",
    "assets": {
        "web._assets_core": [
            "Pharmacy/static/src/js/pharmacy_main.js",
            "Pharmacy/static/src/js/pharmacy_pos.js",
        ],
        "point_of_sale._assets_pos": [
            "Pharmacy/static/src/css/pharmacy_pos.css",
        ],
    },
    "depends": [
        "base",
        "mail",
        "contacts",
        "product",
        "stock",
        "purchase",
        "point_of_sale",
        "account",
        "web",
        "l10n_pe",
        "l10n_pe_pos",
    ],
    "data": [
        # Security
        "security/pharmacy_security.xml",
        "security/ir.model.access.csv",
        # Data
        "data/pharmacy_accounts.xml",
        "data/pharmacy_journal.xml",
        "data/pharmacy_tax_data.xml",
        "data/pharmacy_payment_methods.xml",
        "data/pharmacy_company_config.xml",
        "data/pharmacy_data.xml",
        "data/pharmacy_sequence.xml",
        "data/pharmacy_scheduled_actions.xml",
        # Views
        "views/pharmacy_branch_views.xml",
        "views/pharmacy_patient_views.xml",
        "views/pharmacy_coverage_rule_views.xml",
        "views/pharmacy_controlled_substance_actions.xml",
        "views/pharmacy_controlled_substance_register_views.xml",
        "views/pharmacy_dosage_form_views.xml",
        "views/pharmacy_discount_rule_views.xml",
        "views/pharmacy_insurer_views.xml",
        "views/pharmacy_accounting_views.xml",
        "views/pharmacy_pricing_views.xml",
        "views/pharmacy_stock_lot_views.xml",
        "views/pos_order_pharmacy_views.xml",
        "views/pharmacy_menu.xml",
        "views/pharmacy_financial_reports_views.xml",
        "views/pharmacy_assets.xml",
        "views/pharmacy_company_views.xml",
        "views/pharmacy_dashboard_views.xml",
        "views/res_config_settings_views.xml",
        "views/res_partner_views.xml",
        "views/account_move_views.xml",
        # Reports
        "reports/pharmacy_report_views.xml",
        # POS
        # Wizards
        "wizards/pharmacy_wizard_views.xml",
        # Configuration
        # 'data/pharmacy_config_data.xml',
    ],
    'demo': [
        'demo/pharmacy_demo.xml',
    ],
    "installable": True,
    "auto_install": False,
    "application": True,
    "sequence": 100,
    # 'images': [                              # Commented out - directory doesn't exist
    #     'static/description/banner.png',
    #     'static/description/main.png',
    # ],
    "price": 0.00,
    "currency": "PEN",
    "live_test_url": "https://www.medizano.pe",
    "post_init_hook": "post_init_hook",
    # 'uninstall_hook': 'uninstall_hook',      # Commented out - function doesn't exist
}
