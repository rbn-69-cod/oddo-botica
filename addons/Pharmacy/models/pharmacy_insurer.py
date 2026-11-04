# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)


class PharmacyInsurer(models.Model):
    _name = 'pharmacy.insurer'
    _description = 'Insurance Company'
    _order = 'name'
    _rec_name = 'display_name'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    
    name = fields.Char('Insurer Name', required=True, tracking=True)
    code = fields.Char('Insurer Code', required=True, tracking=True, index=True, copy=False)
    display_name = fields.Char(compute='_compute_display_name', store=True)
    
    # Contact information
    contact_person = fields.Char('Contact Person', tracking=True)
    phone = fields.Char('Phone', tracking=True)
    email = fields.Char('Email', tracking=True)
    website = fields.Char('Website', tracking=True)
    claim_processing_days = fields.Integer('Claim Processing Days', default=30)
    notes = fields.Text('Notes')
    
    # Address
    street = fields.Char()
    street2 = fields.Char()
    city = fields.Char()
    state_id = fields.Many2one('res.country.state', 'State')
    zip = fields.Char('Zip')
    country_id = fields.Many2one('res.country', 'Country')
    
    # Business details
    payment_terms = fields.Text('Payment Terms')
    billing_frequency = fields.Selection([
        ('per_claim', 'Per Claim'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly')
    ], string='Billing Frequency', default='monthly', tracking=True)
    
    consolidate_branches = fields.Boolean('Consolidate Branches', default=False,
                                          help='Invoice all branches together or separate invoices per branch')
    
    auto_create_payment = fields.Boolean('Auto-Create Payment', default=False,
                                        help='Automatically create payment record when claim is approved')
    
    partner_id = fields.Many2one('res.partner', 'Associated Partner', help="Partner record for invoicing")
    payment_term_id = fields.Many2one('account.payment.term', string='Payment Term')
    
    # Related records
    plan_ids = fields.One2many('pharmacy.insurer.plan', 'insurer_id', 'Insurance Plans')
    claim_ids = fields.One2many('pharmacy.claim', 'insurer_id', 'Claims')
    
    # Statistics
    total_claims = fields.Integer(compute='_compute_statistics', store=True)
    total_claimed_amount = fields.Float(compute='_compute_statistics', store=True)
    total_approved_amount = fields.Float(compute='_compute_statistics', store=True)
    approval_rate = fields.Float(compute='_compute_statistics', store=True)
    outstanding_amount = fields.Float(compute='_compute_statistics', store=True)
    
    active = fields.Boolean('Active', default=True, tracking=True)
    company_id = fields.Many2one('res.company', 'Company', required=True,
                                default=lambda self: self.env.company)
    
    @api.depends('name', 'code')
    def _compute_display_name(self):
        for insurer in self:
            insurer.display_name = f"[{insurer.code}] {insurer.name}"
    
    @api.depends('claim_ids')
    def _compute_statistics(self):
        for insurer in self:
            claims = insurer.claim_ids
            
            insurer.total_claims = len(claims)
            insurer.total_claimed_amount = sum(claims.mapped('total_amount'))
            insurer.total_approved_amount = sum(claims.mapped('approved_amount'))
            
            if insurer.total_claimed_amount > 0:
                insurer.approval_rate = (insurer.total_approved_amount / insurer.total_claimed_amount) * 100
            else:
                insurer.approval_rate = 0
            
            # Outstanding amount (approved but not paid)
            outstanding_claims = claims.filtered(lambda c: c.status in ['approved', 'partially_approved'])
            insurer.outstanding_amount = sum(outstanding_claims.mapped('approved_amount'))
    
    @api.constrains('code')
    def _check_code_unique(self):
        for insurer in self:
            if self.search_count([('code', '=', insurer.code), ('id', '!=', insurer.id)]):
                raise ValidationError(_('Insurer code must be unique!'))
    
    def action_view_plans(self):
        """View insurance plans"""
        return {
            'name': _('Insurance Plans'),
            'type': 'ir.actions.act_window',
            'res_model': 'pharmacy.insurer.plan',
            'view_mode': 'list,form',
            'domain': [('insurer_id', '=', self.id)],
            'context': {'default_insurer_id': self.id},
        }
    
    def action_view_claims(self):
        """View claims"""
        return {
            'name': _('Claims'),
            'type': 'ir.actions.act_window',
            'res_model': 'pharmacy.claim',
            'view_mode': 'list,form',
            'domain': [('insurer_id', '=', self.id)],
            'context': {'default_insurer_id': self.id},
        }
    
    def generate_monthly_invoice(self, date_from=None, date_to=None):
        """Generate monthly invoice for all approved claims"""
        if not date_from:
            date_from = fields.Date.today().replace(day=1)
        if not date_to:
            # Last day of current month
            from datetime import timedelta
            next_month = date_from.replace(day=28) + timedelta(days=4)
            date_to = next_month - timedelta(days=next_month.day)
        
        # Get approved claims for the period
        claims = self.env['pharmacy.claim'].search([
            ('insurer_id', '=', self.id),
            ('status', 'in', ['approved', 'partially_approved']),
            ('approval_date', '>=', date_from),
            ('approval_date', '<=', date_to),
        ])
        
        if not claims:
            raise UserError(_('No approved claims found for the specified period'))
        
        # Group claims by branch if not consolidating
        if not self.consolidate_branches:
            branches = claims.mapped('branch_id')
            invoices = []
            
            for branch in branches:
                branch_claims = claims.filtered(lambda c: c.branch_id == branch)
                invoice = self._create_invoice_for_claims(branch_claims, branch)
                invoices.append(invoice)
            
            return invoices
        else:
            # Single invoice for all branches
            invoice = self._create_invoice_for_claims(claims)
            return [invoice]
    
    def _create_invoice_for_claims(self, claims, branch=None):
        """Create invoice for specified claims"""
        if not self.partner_id:
            raise UserError(_('Please associated a partner with this insurer first.'))

        # Create invoice
        invoice_vals = {
            'move_type': 'out_invoice',
            'partner_id': self.partner_id.id,
            'invoice_date': fields.Date.today(),
            'company_id': self.company_id.id,
            'branch_id': branch.id if branch else False,
            'narration': f'Insurance claims for period {claims[0].approval_date} to {claims[-1].approval_date}',
            'invoice_line_ids': [],
        }
        
        # Create invoice lines
        for claim in claims:
            for claim_line in claim.line_ids:
                if claim_line.status == 'approved':
                    invoice_line_vals = {
                        'product_id': claim_line.product_id.id,
                        'name': f'Claim {claim.name} - {claim_line.product_id.name}',
                        'quantity': claim_line.quantity,
                        'price_unit': claim_line.approved_amount / claim_line.quantity if claim_line.quantity > 0 else 0,
                        'account_id': claim_line.product_id.property_account_income_id.id or 
                                     claim_line.product_id.categ_id.property_account_income_categ_id.id,
                    }
                    invoice_vals['invoice_line_ids'].append((0, 0, invoice_line_vals))
        
        invoice = self.env['account.move'].create(invoice_vals)
        return invoice


class PharmacyInsurerPlan(models.Model):
    _name = 'pharmacy.insurer.plan'
    _description = 'Insurance Plan'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'
    _rec_name = 'display_name'
    
    company_id = fields.Many2one(
        'res.company',
        required=True,
        default=lambda self: self.env.company,
        index=True
    )
    insurer_id = fields.Many2one('pharmacy.insurer', 'Insurer', required=True, ondelete='cascade')
    name = fields.Char('Plan Name', required=True)
    code = fields.Char('Plan Code')
    plan_type = fields.Selection([
        ('standard', 'Standard'),
        ('silver', 'Silver'),
        ('gold', 'Gold'),
        ('platinum', 'Platinum'),
    ], string='Plan Type', default='standard')
    display_name = fields.Char(compute='_compute_display_name', store=True)
    
    # Coverage details
    coverage_percentage = fields.Float('Coverage Percentage', default=100.0, tracking=True)
    copay_percentage = fields.Float('Co-pay Percentage', default=0.0, tracking=True)
    
    # Requirements
    require_preauth = fields.Boolean('Require Pre-authorization', default=False)
    require_prescription = fields.Boolean('Require Prescription', default=True)
    require_generic_substitution = fields.Boolean('Require Generic Substitution', default=False)
    
    # Limits
    monthly_limit = fields.Float('Monthly Limit per Member', help='Maximum claim amount per member per month')
    max_amount_per_month = fields.Float(string='Max Amount per Month (Alias)', related='monthly_limit', readonly=False)
    per_visit_limit = fields.Float('Per Visit Limit', help='Maximum claim amount per visit')
    max_amount_per_visit = fields.Float(string='Max Amount per Visit (Alias)', related='per_visit_limit', readonly=False)
    max_amount_per_year = fields.Float('Max Amount per Year', help='Maximum claim amount per member per year')
    notes = fields.Text('Notes')
    
    # Coverage rules and exclusions
    coverage_rule_ids = fields.One2many('pharmacy.coverage.rule', 'plan_id', 'Coverage Rules')
    exclusion_ids = fields.Many2many('product.category', 'pharmacy_plan_exclusion_rel',
                                     'plan_id', 'category_id', 'Excluded Categories')
    
    # Branch applicability
    branch_ids = fields.Many2many('pharmacy.branch', 'pharmacy_plan_branch_rel',
                                  'plan_id', 'branch_id', 'Applicable Branches',
                                  help='Leave empty to apply to all branches')
    
    active = fields.Boolean('Active', default=True)
    
    @api.depends('insurer_id', 'name')
    def _compute_display_name(self):
        for plan in self:
            plan.display_name = f"{plan.insurer_id.name} - {plan.name}"
    
    @api.constrains('coverage_percentage', 'copay_percentage')
    def _check_percentages(self):
        for plan in self:
            if plan.coverage_percentage < 0 or plan.coverage_percentage > 100:
                raise ValidationError(_('Coverage percentage must be between 0 and 100'))
            if plan.copay_percentage < 0 or plan.copay_percentage > 100:
                raise ValidationError(_('Co-pay percentage must be between 0 and 100'))
            if plan.coverage_percentage + plan.copay_percentage > 100:
                raise ValidationError(_('Coverage percentage and co-pay percentage cannot exceed 100%'))
    
    def check_coverage(self, product_id, quantity=1, date=None):
        """
        Check if a product is covered under this plan
        Returns: dict with coverage details
        """
        product = self.env['product.product'].browse(product_id)
        
        # Check category exclusions
        if product.categ_id in self.exclusion_ids:
            return {
                'covered': False,
                'reason': f'Product category {product.categ_id.name} is excluded',
                'coverage_percentage': 0,
                'copay_percentage': 100,
            }
        
        # Check specific coverage rules
        rule = self.coverage_rule_ids.filtered(lambda r: 
            (r.product_id and r.product_id.id == product_id) or
            (r.category_id and r.category_id == product.categ_id)
        )
        
        if rule:
            # Use the most specific rule (product-level overrides category-level)
            rule = rule.sorted(lambda r: r.product_id and 1 or 0, reverse=True)[0]
            
            # Check quantity limits
            if rule.max_quantity_per_visit and quantity > rule.max_quantity_per_visit:
                return {
                    'covered': False,
                    'reason': f'Quantity exceeds per-visit limit of {rule.max_quantity_per_visit}',
                    'coverage_percentage': 0,
                    'copay_percentage': 100,
                }
            
            return {
                'covered': True,
                'coverage_percentage': rule.coverage_percentage,
                'copay_percentage': rule.copay_amount and (rule.copay_amount / (product.lst_price * quantity)) * 100 or rule.copay_percentage,
                'require_generic_substitution': rule.require_generic_substitution,
                'max_quantity_per_visit': rule.max_quantity_per_visit,
                'max_quantity_per_month': rule.max_quantity_per_month,
            }
        
        # Default plan coverage
        return {
            'covered': True,
            'coverage_percentage': self.coverage_percentage,
            'copay_percentage': self.copay_percentage,
            'require_generic_substitution': self.require_generic_substitution,
            'monthly_limit': self.monthly_limit,
            'per_visit_limit': self.per_visit_limit,
        }
    
    def get_applicable_branches(self):
        """Get branches where this plan is applicable"""
        if self.branch_ids:
            return self.branch_ids
        else:
            return self.env['pharmacy.branch'].search([('active', '=', True)])
    
    def action_view_claims(self):
        """View claims for this plan"""
        return {
            'name': _('Claims'),
            'type': 'ir.actions.act_window',
            'res_model': 'pharmacy.claim',
            'view_mode': 'list,form',
            'domain': [('plan_id', '=', self.id)],
            'context': {'default_plan_id': self.id},
        }


