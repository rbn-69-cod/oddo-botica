# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)


class PosSession(models.Model):
    _inherit = 'pos.session'
    
    # Pharmacy fields
    branch_id = fields.Many2one(related='config_id.branch_id', store=True, readonly=True)
    pharmacist_id = fields.Many2one('res.users', 'Pharmacist on Duty',
                                    domain="[('is_pharmacist', '=', True)]")
    
    # Cash-up fields
    cashup_ids = fields.One2many('pharmacy.cashup', 'session_id', 'Cash-up Records')
    
    # Statistics
    total_prescriptions = fields.Integer(compute='_compute_pharmacy_stats', store=True)
    total_insurance_sales = fields.Float(compute='_compute_pharmacy_stats', store=True)
    total_controlled_sales = fields.Integer(compute='_compute_pharmacy_stats', store=True)
    
    @api.depends('order_ids')
    def _compute_pharmacy_stats(self):
        for session in self:
            orders = session.order_ids
            
            # Count prescriptions
            session.total_prescriptions = len(orders.mapped('prescription_id'))
            
            # Sum insurance sales
            insurance_orders = orders.filtered(lambda o: o.is_insurance_sale)
            session.total_insurance_sales = sum(insurance_orders.mapped('insurance_amount'))
            
            # Count controlled substance sales
            controlled_orders = orders.filtered(
                lambda o: o.lines.mapped('product_id.is_controlled_substance')
            )
            session.total_controlled_sales = len(controlled_orders)
    
    def action_view_cashup(self):
        """View cash-up records for this session"""
        return {
            'name': _('Cash-up Records'),
            'type': 'ir.actions.act_window',
            'res_model': 'pharmacy.cashup',
            'view_mode': 'list,form',
            'domain': [('session_id', '=', self.id)],
            'context': {'default_session_id': self.id},
        }
    
    def action_create_cashup(self):
        """Create cash-up record for this session"""
        if self.state != 'closed':
            raise UserError(_('Session must be closed before creating cash-up'))
        
        # Check if cash-up already exists
        existing = self.env['pharmacy.cashup'].search([
            ('session_id', '=', self.id)
        ])
        if existing:
            raise UserError(_('Cash-up already exists for this session'))
        
        # Calculate expected amounts
        payments = self.env['pos.payment'].search([('pos_order_id.session_id', '=', self.id)])
        
        cash_payments = payments.filtered(lambda p: p.payment_method_id.name == 'Cash')
        mpesa_payments = payments.filtered(lambda p: 'M-Pesa' in p.payment_method_id.name)
        card_payments = payments.filtered(lambda p: 'Card' in p.payment_method_id.name)
        
        cashup_vals = {
            'session_id': self.id,
            'branch_id': self.branch_id.id,
            'cashier_id': self.user_id.id,
            'date': fields.Date.today(),
            'expected_cash': sum(cash_payments.mapped('amount')),
            'expected_mpesa': sum(mpesa_payments.mapped('amount')),
            'expected_card': sum(card_payments.mapped('amount')),
        }
        
        cashup = self.env['pharmacy.cashup'].create(cashup_vals)
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Cash-up'),
            'res_model': 'pharmacy.cashup',
            'res_id': cashup.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    def get_session_summary(self):
        """Get detailed session summary including pharmacy metrics"""
        orders = self.order_ids.filtered(lambda o: o.state in ['paid', 'done', 'invoiced'])
        
        summary = {
            'basic': {
                'total_orders': len(orders),
                'total_sales': sum(orders.mapped('amount_total')),
                'total_customers': len(orders.mapped('partner_id')),
            },
            'pharmacy': {
                'prescriptions': self.total_prescriptions,
                'insurance_sales': self.total_insurance_sales,
                'controlled_sales': self.total_controlled_sales,
                'dispensing_records': len(self.env['pharmacy.dispensing'].search([
                    ('pos_order_id.session_id', '=', self.id)
                ])),
            },
            'payment_breakdown': {},
            'top_products': {},
            'insurance_breakdown': {},
        }
        
        # Payment breakdown - batch fetch all payments for this session
        payments = self.env['pos.payment'].search([('pos_order_id.session_id', '=', self.id)])
        for payment in payments:
            method = payment.payment_method_id.name
            if method not in summary['payment_breakdown']:
                summary['payment_breakdown'][method] = 0
            summary['payment_breakdown'][method] += payment.amount
        
        # Top products
        product_sales = {}
        for order in orders:
            for line in order.lines:
                product = line.product_id.name
                if product not in product_sales:
                    product_sales[product] = {'quantity': 0, 'amount': 0}
                product_sales[product]['quantity'] += line.qty
                product_sales[product]['amount'] += line.price_subtotal_incl
        
        # Sort by amount and get top 10
        summary['top_products'] = dict(
            sorted(product_sales.items(), key=lambda x: x[1]['amount'], reverse=True)[:10]
        )
        
        # Insurance breakdown
        insurance_orders = orders.filtered(lambda o: o.is_insurance_sale)
        for order in insurance_orders:
            insurer = order.insurer_id.name
            if insurer not in summary['insurance_breakdown']:
                summary['insurance_breakdown'][insurer] = {'orders': 0, 'amount': 0}
            summary['insurance_breakdown'][insurer]['orders'] += 1
            summary['insurance_breakdown'][insurer]['amount'] += order.insurance_amount
        
        return summary
