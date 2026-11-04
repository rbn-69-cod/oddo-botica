#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Create materialized views for performance optimization

Materialized views pre-compute complex aggregations for faster reporting.
Run this script in Odoo shell:
    python odoo-bin shell -d pharmacy_db -c /path/to/odoo.conf
    exec(open('/path/to/create_materialized_views.py').read())
"""

import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def create_materialized_views():
    """Create materialized views for pharmacy aggregations"""
    
    env = api.Environment(cr, SUPERUSER_ID, {})
    
    views_to_create = [
        {
            'name': 'mv_pharmacy_daily_sales',
            'query': '''
                SELECT 
                    date(o.date_order) as date,
                    o.branch_id,
                    COUNT(*) as order_count,
                    SUM(o.amount_total) as total_sales,
                    SUM(o.amount_tax) as total_tax,
                    AVG(o.amount_total) as avg_order_value,
                    COUNT(DISTINCT o.patient_id) as unique_patients,
                    COUNT(DISTINCT o.partner_id) as unique_customers
                FROM pos_order o
                WHERE o.state IN ('paid', 'done', 'invoiced')
                GROUP BY date(o.date_order), o.branch_id
            ''',
            'refresh': 'CONCURRENTLY'
        },
        {
            'name': 'mv_pharmacy_daily_dispensing',
            'query': '''
                SELECT 
                    d.dispensed_date as date,
                    d.branch_id,
                    d.product_id,
                    COUNT(*) as dispensing_count,
                    SUM(d.quantity_dispensed) as total_quantity,
                    COUNT(DISTINCT d.patient_id) as unique_patients
                FROM pharmacy_dispensing d
                WHERE d.dispensed_date IS NOT NULL
                GROUP BY d.dispensed_date, d.branch_id, d.product_id
            ''',
            'refresh': 'CONCURRENTLY'
        },
        {
            'name': 'mv_pharmacy_daily_claims',
            'query': '''
                SELECT 
                    c.submission_date as date,
                    c.branch_id,
                    c.insurer_id,
                    COUNT(*) as claim_count,
                    SUM(c.total_claimed_amount) as total_claimed,
                    SUM(c.insurance_amount) as total_insurance,
                    SUM(c.copay_amount) as total_copay,
                    COUNT(CASE WHEN c.status = 'approved' THEN 1 END) as approved_count,
                    COUNT(CASE WHEN c.status = 'rejected' THEN 1 END) as rejected_count,
                    COUNT(CASE WHEN c.status = 'pending' THEN 1 END) as pending_count
                FROM pharmacy_claim c
                WHERE c.submission_date IS NOT NULL
                GROUP BY c.submission_date, c.branch_id, c.insurer_id
            ''',
            'refresh': 'CONCURRENTLY'
        },
        {
            'name': 'mv_pharmacy_product_stock',
            'query': '''
                SELECT 
                    p.id as product_id,
                    p.default_code,
                    p.name as product_name,
                    COALESCE(SUM(q.quantity), 0) as total_quantity,
                    COALESCE(SUM(CASE WHEN l.expiry_date < CURRENT_DATE THEN q.quantity ELSE 0 END), 0) as expired_quantity,
                    COALESCE(SUM(CASE WHEN l.expiry_date BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '30 days' THEN q.quantity ELSE 0 END), 0) as expiring_soon_quantity,
                    COUNT(DISTINCT l.id) as lot_count,
                    MIN(l.expiry_date) as nearest_expiry_date
                FROM product_product p
                LEFT JOIN stock_quant q ON q.product_id = p.id
                LEFT JOIN stock_lot l ON l.id = q.lot_id
                WHERE p.is_pharma_product = true
                GROUP BY p.id, p.default_code, p.name
            ''',
            'refresh': 'CONCURRENTLY'
        },
        {
            'name': 'mv_pharmacy_patient_activity',
            'query': '''
                SELECT 
                    p.id as patient_id,
                    p.patient_code,
                    p.name as patient_name,
                    COUNT(DISTINCT o.id) as total_orders,
                    SUM(o.amount_total) as total_spent,
                    MAX(o.date_order) as last_order_date,
                    COUNT(DISTINCT pr.id) as total_prescriptions,
                    COUNT(DISTINCT d.id) as total_dispensing,
                    COUNT(DISTINCT c.id) as total_claims
                FROM pharmacy_patient p
                LEFT JOIN pos_order o ON o.patient_id = p.id AND o.state IN ('paid', 'done', 'invoiced')
                LEFT JOIN pharmacy_prescription pr ON pr.patient_id = p.id
                LEFT JOIN pharmacy_dispensing d ON d.patient_id = p.id
                LEFT JOIN pharmacy_claim c ON c.patient_id = p.id
                GROUP BY p.id, p.patient_code, p.name
            ''',
            'refresh': 'CONCURRENTLY'
        },
        {
            'name': 'mv_pharmacy_insurer_performance',
            'query': '''
                SELECT 
                    i.id as insurer_id,
                    i.code as insurer_code,
                    i.name as insurer_name,
                    COUNT(DISTINCT c.id) as total_claims,
                    SUM(c.total_claimed_amount) as total_claimed,
                    SUM(c.insurance_amount) as total_paid,
                    COUNT(CASE WHEN c.status = 'approved' THEN 1 END) as approved_claims,
                    COUNT(CASE WHEN c.status = 'rejected' THEN 1 END) as rejected_claims,
                    ROUND(
                        CASE 
                            WHEN COUNT(*) > 0 THEN 
                                (COUNT(CASE WHEN c.status = 'approved' THEN 1 END) * 100.0 / COUNT(*))
                            ELSE 0 
                        END, 2
                    ) as approval_rate,
                    AVG(c.approval_date - c.submission_date) as avg_approval_time
                FROM pharmacy_insurer i
                LEFT JOIN pharmacy_claim c ON c.insurer_id = i.id
                GROUP BY i.id, i.code, i.name
            ''',
            'refresh': 'CONCURRENTLY'
        },
    ]
    
    created_count = 0
    skipped_count = 0
    error_count = 0
    
    for view in views_to_create:
        try:
            # Check if view already exists
            cr.execute(f"""
                SELECT matviewname FROM pg_matviews 
                WHERE matviewname = '{view['name']}'
            """)
            
            if cr.fetchone():
                _logger.info(f"Materialized view {view['name']} already exists")
                skipped_count += 1
                continue
            
            # Create materialized view
            cr.execute(f"""
                CREATE MATERIALIZED VIEW {view['name']} AS
                {view['query']}
                WITH DATA
            """)
            
            # Create indexes on the view
            if 'daily_sales' in view['name']:
                cr.execute(f"CREATE INDEX idx_{view['name']}_date ON {view['name']} (date)")
                cr.execute(f"CREATE INDEX idx_{view['name']}_branch ON {view['name']} (branch_id)")
            elif 'product_stock' in view['name']:
                cr.execute(f"CREATE INDEX idx_{view['name']}_product ON {view['name']} (product_id)")
            elif 'patient_activity' in view['name']:
                cr.execute(f"CREATE INDEX idx_{view['name']}_patient ON {view['name']} (patient_id)")
            
            _logger.info(f"Created materialized view {view['name']}")
            created_count += 1
            
        except Exception as e:
            _logger.error(f"Failed to create materialized view {view['name']}: {str(e)}")
            error_count += 1
    
    _logger.info(f"Materialized view creation complete: {created_count} created, {skipped_count} skipped, {error_count} errors")
    
    return {
        'created': created_count,
        'skipped': skipped_count,
        'errors': error_count
    }


def refresh_materialized_views(view_name=None):
    """
    Refresh materialized views
    
    Args:
        view_name: Specific view to refresh, or None to refresh all
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    
    views = [
        'mv_pharmacy_daily_sales',
        'mv_pharmacy_daily_dispensing',
        'mv_pharmacy_daily_claims',
        'mv_pharmacy_product_stock',
        'mv_pharmacy_patient_activity',
        'mv_pharmacy_insurer_performance',
    ]
    
    if view_name:
        views = [view_name]
    
    refreshed_count = 0
    error_count = 0
    
    for view in views:
        try:
            cr.execute(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {view}")
            _logger.info(f"Refreshed materialized view {view}")
            refreshed_count += 1
        except Exception as e:
            _logger.error(f"Failed to refresh materialized view {view}: {str(e)}")
            error_count += 1
    
    return {
        'refreshed': refreshed_count,
        'errors': error_count
    }


def setup_refresh_schedule():
    """
    Set up scheduled action to refresh materialized views daily
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    
    cron_vals = {
        'name': 'Refresh Pharmacy Materialized Views',
        'model_id': env.ref('base.ir_cron').id,
        'state': 'code',
        'code': '''
model = env['pharmacy.dashboard']
# Refresh all materialized views
cr.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY mv_pharmacy_daily_sales")
cr.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY mv_pharmacy_daily_dispensing")
cr.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY mv_pharmacy_daily_claims")
cr.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY mv_pharmacy_product_stock")
cr.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY mv_pharmacy_patient_activity")
cr.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY mv_pharmacy_insurer_performance")
''',
        'interval_number': 1,
        'interval_type': 'days',
        'numbercall': -1,
        'doall': False,
        'active': True,
        'user_id': env.ref('base.user_root').id,
    }
    
    # Check if cron already exists
    existing = env['ir.cron'].search([('name', '=', cron_vals['name'])])
    
    if existing:
        existing.write(cron_vals)
        _logger.info("Updated existing scheduled action for materialized view refresh")
    else:
        env['ir.cron'].create(cron_vals)
        _logger.info("Created scheduled action for materialized view refresh")


if __name__ == '__main__':
    result = create_materialized_views()
    print(f"\nMaterialized view creation summary:")
    print(f"  Created: {result['created']}")
    print(f"  Skipped: {result['skipped']}")
    print(f"  Errors: {result['errors']}")
    
    # Set up refresh schedule
    setup_refresh_schedule()
    print("\nScheduled action for daily refresh configured")
