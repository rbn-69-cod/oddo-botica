# -*- coding: utf-8 -*-

from odoo import http
from odoo.http import request
import json
import logging

_logger = logging.getLogger(__name__)


class PharmacyDashboard(http.Controller):
    
    @http.route('/pharmacy/dashboard/data', type='json', auth='user')
    def get_dashboard_data(self):
        """Get comprehensive dashboard data for pharmacy"""
        try:
            dashboard_model = request.env['pharmacy.dashboard']
            data = dashboard_model.get_dashboard_data()
            return data
        except Exception as e:
            _logger.error("Error loading dashboard data: %s", str(e))
            return {'error': str(e)}
    
    @http.route('/pharmacy/dashboard/sales_chart', type='json', auth='user')
    def get_sales_chart_data(self, days=30):
        """Get sales data for chart"""
        try:
            # Get sales data for the specified period
            today = fields.Date.today()
            start_date = today - timedelta(days=days)
            
            orders = request.env['pos.order'].search([
                ('date_order', '>=', start_date),
                ('state', 'in', ['paid', 'done', 'invoiced'])
            ])
            
            # Group by date
            sales_data = {}
            for order in orders:
                date_key = order.date_order.date().strftime('%Y-%m-%d')
                if date_key not in sales_data:
                    sales_data[date_key] = {
                        'date': date_key,
                        'total_sales': 0,
                        'cash_sales': 0,
                        'mpesa_sales': 0,
                        'card_sales': 0,
                        'insurance_sales': 0,
                        'orders_count': 0
                    }
                
                sales_data[date_key]['total_sales'] += order.amount_total
                sales_data[date_key]['orders_count'] += 1
                
                # Add payment method breakdown
                for payment in order.payment_ids:
                    if payment.payment_method_id.name == 'Cash':
                        sales_data[date_key]['cash_sales'] += payment.amount
                    elif 'M-Pesa' in payment.payment_method_id.name:
                        sales_data[date_key]['mpesa_sales'] += payment.amount
                    elif 'Card' in payment.payment_method_id.name:
                        sales_data[date_key]['card_sales'] += payment.amount
                
                sales_data[date_key]['insurance_sales'] += order.insurance_amount
            
            # Convert to list and sort by date
            chart_data = sorted(sales_data.values(), key=lambda x: x['date'])
            
            return {
                'labels': [item['date'] for item in chart_data],
                'datasets': [
                    {
                        'label': 'Total Sales',
                        'data': [item['total_sales'] for item in chart_data],
                        'backgroundColor': 'rgba(54, 162, 235, 0.2)',
                        'borderColor': 'rgba(54, 162, 235, 1)',
                        'borderWidth': 1
                    },
                    {
                        'label': 'Cash Sales',
                        'data': [item['cash_sales'] for item in chart_data],
                        'backgroundColor': 'rgba(75, 192, 192, 0.2)',
                        'borderColor': 'rgba(75, 192, 192, 1)',
                        'borderWidth': 1
                    },
                    {
                        'label': 'M-Pesa Sales',
                        'data': [item['mpesa_sales'] for item in chart_data],
                        'backgroundColor': 'rgba(255, 206, 86, 0.2)',
                        'borderColor': 'rgba(255, 206, 86, 1)',
                        'borderWidth': 1
                    },
                    {
                        'label': 'Insurance Sales',
                        'data': [item['insurance_sales'] for item in chart_data],
                        'backgroundColor': 'rgba(255, 99, 132, 0.2)',
                        'borderColor': 'rgba(255, 99, 132, 1)',
                        'borderWidth': 1
                    }
                ]
            }
        except Exception as e:
            _logger.error("Error loading sales chart data: %s", str(e))
            return {'error': str(e)}
    
    @http.route('/pharmacy/dashboard/top_products', type='json', auth='user')
    def get_top_products(self, limit=10, days=30):
        """Get top selling products"""
        try:
            today = fields.Date.today()
            start_date = today - timedelta(days=days)
            
            # Get top products by sales amount
            request.env.cr.execute("""
                SELECT 
                    pp.id as product_id,
                    pp.name as product_name,
                    pt.generic_name,
                    SUM(pol.qty * pol.price_unit) as total_sales,
                    SUM(pol.qty) as total_quantity,
                    COUNT(DISTINCT pol.order_id) as order_count
                FROM pos_order_line pol
                INNER JOIN pos_order po ON pol.order_id = po.id
                INNER JOIN product_product pp ON pol.product_id = pp.id
                INNER JOIN product_template pt ON pp.product_tmpl_id = pt.id
                WHERE po.date_order >= %s
                  AND po.state IN ('paid', 'done', 'invoiced')
                GROUP BY pp.id, pp.name, pt.generic_name
                ORDER BY total_sales DESC
                LIMIT %s
            """, (start_date, limit))
            
            results = request.env.cr.dictfetchall()
            
            return {
                'products': results,
                'labels': [r['product_name'] for r in results],
                'sales_data': [r['total_sales'] for r in results],
                'quantity_data': [r['total_quantity'] for r in results]
            }
        except Exception as e:
            _logger.error("Error loading top products: %s", str(e))
            return {'error': str(e)}
    
    @http.route('/pharmacy/dashboard/expiry_alerts', type='json', auth='user')
    def get_expiry_alerts(self):
        """Get expiry alerts for dashboard"""
        try:
            # Get expired stock
            expired_lots = request.env['stock.lot'].search([('is_expired', '=', True)])
            expired_count = len(expired_lots)
            expired_value = 0
            
            for lot in expired_lots:
                quants = request.env['stock.quant'].search([
                    ('lot_id', '=', lot.id),
                    ('quantity', '>', 0)
                ])
                expired_value += sum(quants.mapped(lambda q: q.quantity * q.product_id.standard_price))
            
            # Get stock expiring in 30 days
            expiring_lots = request.env['stock.lot'].get_expiring_lots(30)
            expiring_count = len(expiring_lots)
            expiring_value = 0
            
            for lot in expiring_lots:
                quants = request.env['stock.quant'].search([
                    ('lot_id', '=', lot.id),
                    ('quantity', '>', 0)
                ])
                expiring_value += sum(quants.mapped(lambda q: q.quantity * q.product_id.standard_price))
            
            # Get detailed expiring products
            expiring_details = []
            for lot in expiring_lots[:10]:  # Top 10 expiring items
                quants = request.env['stock.quant'].search([
                    ('lot_id', '=', lot.id),
                    ('quantity', '>', 0)
                ])
                if quants:
                    expiring_details.append({
                        'product': lot.product_id.name,
                        'lot': lot.name,
                        'expiry_date': lot.expiry_date.strftime('%Y-%m-%d'),
                        'days_to_expiry': lot.days_to_expiry,
                        'quantity': sum(quants.mapped('quantity')),
                        'value': sum(quants.mapped(lambda q: q.quantity * q.product_id.standard_price))
                    })
            
            return {
                'expired_count': expired_count,
                'expired_value': expired_value,
                'expiring_count': expiring_count,
                'expiring_value': expiring_value,
                'expiring_details': expiring_details
            }
        except Exception as e:
            _logger.error("Error loading expiry alerts: %s", str(e))
            return {'error': str(e)}
    
    @http.route('/pharmacy/dashboard/insurance_summary', type='json', auth='user')
    def get_insurance_summary(self, days=30):
        """Get insurance claims summary"""
        try:
            today = fields.Date.today()
            start_date = today - timedelta(days=days)
            
            # Get claims summary
            claims = request.env['pharmacy.claim'].search([
                ('claim_date', '>=', start_date)
            ])
            
            total_claims = len(claims)
            pending_claims = len(claims.filtered(lambda c: c.status == 'submitted'))
            approved_claims = len(claims.filtered(lambda c: c.status in ['approved', 'partially_approved']))
            rejected_claims = len(claims.filtered(lambda c: c.status == 'rejected'))
            
            total_claimed = sum(claims.mapped('total_amount'))
            total_approved = sum(claims.mapped('approved_amount'))
            total_rejected = sum(claims.mapped('rejected_amount'))
            
            # Get claims by insurer
            request.env.cr.execute("""
                SELECT 
                    ins.name as insurer_name,
                    COUNT(pc.id) as claim_count,
                    SUM(pc.total_amount) as total_claimed,
                    SUM(pc.approved_amount) as total_approved
                FROM pharmacy_claim pc
                LEFT JOIN pharmacy_insurer ins ON pc.insurer_id = ins.id
                WHERE pc.claim_date >= %s
                GROUP BY ins.id, ins.name
                ORDER BY total_claimed DESC
            """, (start_date,))
            
            insurer_data = request.env.cr.dictfetchall()
            
            # Get recent claims
            recent_claims = claims.search([], order='claim_date desc', limit=10)
            recent_data = [{
                'name': claim.name,
                'patient': claim.patient_name,
                'insurer': claim.insurer_id.name,
                'amount': claim.total_amount,
                'status': claim.status,
                'date': claim.claim_date.strftime('%Y-%m-%d')
            } for claim in recent_claims]
            
            return {
                'summary': {
                    'total_claims': total_claims,
                    'pending_claims': pending_claims,
                    'approved_claims': approved_claims,
                    'rejected_claims': rejected_claims,
                    'total_claimed': total_claimed,
                    'total_approved': total_approved,
                    'total_rejected': total_rejected,
                    'approval_rate': (total_approved / total_claimed * 100) if total_claimed > 0 else 0
                },
                'insurer_data': insurer_data,
                'recent_claims': recent_data
            }
        except Exception as e:
            _logger.error("Error loading insurance summary: %s", str(e))
            return {'error': str(e)}
    
    @http.route('/pharmacy/dashboard/branch_performance', type='json', auth='user')
    def get_branch_performance(self, days=30):
        """Get branch performance comparison"""
        try:
            today = fields.Date.today()
            start_date = today - timedelta(days=days)
            
            # Get branch performance data
            request.env.cr.execute("""
                SELECT 
                    pb.id as branch_id,
                    pb.name as branch_name,
                    COUNT(DISTINCT po.id) as order_count,
                    SUM(po.amount_total) as total_sales,
                    SUM(po.insurance_amount) as insurance_sales,
                    COUNT(DISTINCT po.partner_id) as customer_count,
                    COUNT(DISTINCT po.prescription_id) as prescription_count
                FROM pos_order po
                LEFT JOIN pharmacy_branch pb ON po.branch_id = pb.id
                WHERE po.date_order >= %s
                  AND po.state IN ('paid', 'done', 'invoiced')
                GROUP BY pb.id, pb.name
                ORDER BY total_sales DESC
            """, (start_date,))
            
            branch_data = request.env.cr.dictfetchall()
            
            return {
                'branches': branch_data,
                'labels': [b['branch_name'] for b in branch_data],
                'sales_data': [b['total_sales'] for b in branch_data],
                'orders_data': [b['order_count'] for b in branch_data],
                'customers_data': [b['customer_count'] for b in branch_data]
            }
        except Exception as e:
            _logger.error("Error loading branch performance: %s", str(e))
            return {'error': str(e)}
