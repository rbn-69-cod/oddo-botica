# -*- coding: utf-8 -*-

# Pharmacy Management System for Odoo 18
# All model imports - properly ordered to avoid dependency issues

from . import (
    # Core models first
    res_partner,
    res_users,
    
    # Product and inventory models
    product_template,
    stock_location,
    stock_lot,
    stock_picking,
    stock_picking_variance,
    
    # Pharmacy core models
    pharmacy_branch,
    pharmacy_patient,
    pharmacy_patient_insurance,
    pharmacy_insurer,
    pharmacy_coverage_rule,
    pharmacy_discount_rule,
    pharmacy_dosage_form,
    
    # Prescription and dispensing
    pharmacy_prescription,
    pharmacy_dispensing,
    pharmacy_controlled_substance_register,
    
    # Financial models
    pharmacy_accounting,
    pharmacy_pricing,
    pharmacy_claim,
    
    # POS models
    pos_config,
    pos_order,
    pos_session,
    
    # Integration models
    pharmacy_mpesa_integration,
    pharmacy_sunat_integration,
    decolecta_service,
    res_config_settings,
    
    # Audit and compliance
    pharmacy_audit_log,
    
    # Dashboard and analytics
    pharmacy_dashboard,
    
    # Reports
    pharmacy_reports,
    pharmacy_bsc,
)
