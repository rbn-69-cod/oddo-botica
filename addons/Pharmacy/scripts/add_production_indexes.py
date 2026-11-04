#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Add production-grade database indexes for performance optimization

Run this script in Odoo shell:
    python odoo-bin shell -d pharmacy_db -c /path/to/odoo.conf
    exec(open('/path/to/add_production_indexes.py').read())
"""

import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)

def add_indexes():
    """Add database indexes for frequently queried fields"""
    
    # Index definitions: (table_name, index_name, fields)
    indexes_to_add = [
        # Pharmacy Patient
        ('pharmacy_patient', 'idx_pharmacy_patient_status', 'status'),
        ('pharmacy_patient', 'idx_pharmacy_patient_active', 'active'),
        ('pharmacy_patient', 'idx_pharmacy_patient_partner_id', 'partner_id'),
        
        # Pharmacy Patient Insurance
        ('pharmacy_patient_insurance', 'idx_patient_insurance_status', 'status'),
        ('pharmacy_patient_insurance', 'idx_patient_insurance_valid_from', 'valid_from'),
        ('pharmacy_patient_insurance', 'idx_patient_insurance_valid_to', 'valid_to'),
        ('pharmacy_patient_insurance', 'idx_patient_insurance_patient_id', 'patient_id'),
        ('pharmacy_patient_insurance', 'idx_patient_insurance_insurer_id', 'insurer_id'),
        
        # Pharmacy Prescription
        ('pharmacy_prescription', 'idx_prescription_status', 'status'),
        ('pharmacy_prescription', 'idx_prescription_date', 'prescription_date'),
        ('pharmacy_prescription', 'idx_prescription_patient_id', 'patient_id'),
        ('pharmacy_prescription', 'idx_prescription_branch_id', 'branch_id'),
        
        # Pharmacy Claim
        ('pharmacy_claim', 'idx_claim_status', 'status'),
        ('pharmacy_claim', 'idx_claim_submission_date', 'submission_date'),
        ('pharmacy_claim', 'idx_claim_approval_date', 'approval_date'),
        ('pharmacy_claim', 'idx_claim_insurer_id', 'insurer_id'),
        ('pharmacy_claim', 'idx_claim_branch_id', 'branch_id'),
        ('pharmacy_claim', 'idx_claim_pos_order_id', 'pos_order_id'),
        
        # Pharmacy Dispensing
        ('pharmacy_dispensing', 'idx_dispensing_patient_id', 'patient_id'),
        ('pharmacy_dispensing', 'idx_dispensing_product_id', 'product_id'),
        ('pharmacy_dispensing', 'idx_dispensing_branch_id', 'branch_id'),
        ('pharmacy_dispensing', 'idx_dispensing_date', 'dispensed_date'),
        
        # Stock Lot
        ('stock_lot', 'idx_stock_lot_expiry_date', 'expiry_date'),
        ('stock_lot', 'idx_stock_lot_is_expired', 'is_expired'),
        ('stock_lot', 'idx_stock_lot_is_quarantined', 'is_quarantined'),
        ('stock_lot', 'idx_stock_lot_product_id', 'product_id'),
        
        # POS Order
        ('pos_order', 'idx_pos_order_state', 'state'),
        ('pos_order', 'idx_pos_order_date_order', 'date_order'),
        ('pos_order', 'idx_pos_order_session_id', 'session_id'),
        ('pos_order', 'idx_pos_order_branch_id', 'branch_id'),
        ('pos_order', 'idx_pos_order_partner_id', 'partner_id'),
        
        # POS Session
        ('pos_session', 'idx_pos_session_state', 'state'),
        ('pos_session', 'idx_pos_session_start_at', 'start_at'),
        ('pos_session', 'idx_pos_session_stop_at', 'stop_at'),
        ('pos_session', 'idx_pos_session_config_id', 'config_id'),
        
        # Stock Picking
        ('stock_picking', 'idx_stock_picking_state', 'state'),
        ('stock_picking', 'idx_stock_picking_scheduled_date', 'scheduled_date'),
        ('stock_picking', 'idx_stock_picking_location_id', 'location_id'),
        ('stock_picking', 'idx_stock_picking_location_dest_id', 'location_dest_id'),
        
        # Account Move (for financial queries)
        ('account_move', 'idx_account_move_state', 'state'),
        ('account_move', 'idx_account_move_invoice_date', 'invoice_date'),
        ('account_move', 'idx_account_move_move_type', 'move_type'),
    ]
    
    env = api.Environment(cr, SUPERUSER_ID, {})
    
    added_count = 0
    skipped_count = 0
    error_count = 0
    
    for table_name, index_name, fields in indexes_to_add:
        try:
            # Check if index already exists
            cr.execute(f"""
                SELECT indexname FROM pg_indexes 
                WHERE tablename = '{table_name}' AND indexname = '{index_name}'
            """)
            
            if cr.fetchone():
                _logger.info(f"Index {index_name} already exists on {table_name}")
                skipped_count += 1
                continue
            
            # Create index
            cr.execute(f"""
                CREATE INDEX CONCURRENTLY {index_name} 
                ON {table_name} ({fields})
            """)
            
            _logger.info(f"Created index {index_name} on {table_name} ({fields})")
            added_count += 1
            
        except Exception as e:
            _logger.error(f"Failed to create index {index_name} on {table_name}: {str(e)}")
            error_count += 1
    
    _logger.info(f"Index creation complete: {added_count} added, {skipped_count} skipped, {error_count} errors")
    
    return {
        'added': added_count,
        'skipped': skipped_count,
        'errors': error_count
    }

if __name__ == '__main__':
    result = add_indexes()
    print(f"\nIndex creation summary:")
    print(f"  Added: {result['added']}")
    print(f"  Skipped: {result['skipped']}")
    print(f"  Errors: {result['errors']}")
