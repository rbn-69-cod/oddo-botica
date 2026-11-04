# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)


class PharmacyCoverageRule(models.Model):
    _name = 'pharmacy.coverage.rule'
    _description = 'Insurance Coverage Rule'
    _order = 'plan_id, priority DESC, product_id, category_id'
    
    name = fields.Char('Rule Name')
    insurer_id = fields.Many2one('pharmacy.insurer', string='Insurer', related='plan_id.insurer_id', store=True)
    # Plan association
    plan_id = fields.Many2one('pharmacy.insurer.plan', 'Insurance Plan', required=True, ondelete='cascade')
    
    # Product or category coverage
    product_id = fields.Many2one('product.product', 'Product')
    category_id = fields.Many2one('product.category', 'Product Category')
    product_category_id = fields.Many2one('product.category', string='Product Category (Alias)', related='category_id', readonly=False)
    
    # Coverage percentages
    coverage_percentage = fields.Float('Coverage %', default=100.0, help='Override plan default coverage percentage')
    copay_percentage = fields.Float('Co-pay %', default=0.0, help='Override plan default co-pay percentage')
    copay_amount = fields.Float('Fixed Co-pay Amount', help='Fixed co-pay amount instead of percentage')
    
    # Quantity limits
    max_quantity_per_visit = fields.Float('Max Qty per Visit', help='Maximum quantity allowed per visit')
    max_quantity_per_month = fields.Float('Max Qty per Month', help='Maximum quantity allowed per month')
    max_amount = fields.Float('Max Amount', help='Maximum amount covered')
    min_quantity = fields.Float('Min Quantity', help='Minimum quantity for rule to apply')
    
    # Additional notes
    notes = fields.Text('Notes', help='Additional coverage notes or conditions')
    
    # Requirements
    require_generic_substitution = fields.Boolean('Require Generic Substitution', default=False)
    require_prescription = fields.Boolean('Require Prescription', default=True)
    require_preauth = fields.Boolean('Require Pre-authorization', default=False)
    requires_preauth = fields.Boolean(string='Requires Pre-auth (Alias)', related='require_preauth', readonly=False)
    preauth_threshold = fields.Float('Pre-auth Threshold', help='Require pre-auth for amounts above this threshold')
    
    # Exclusions
    is_exclusion = fields.Boolean('Is Exclusion Rule', default=False, help='This rule excludes the item from coverage')
    exclusion_reason = fields.Char('Exclusion Reason')
    
    # Active status
    active = fields.Boolean('Active', default=True)
    
    # Branch applicability
    branch_ids = fields.Many2many('pharmacy.branch', string='Branches', 
                               help='Leave empty to apply to all branches')
    
    # Patient conditions
    age_min = fields.Integer('Minimum Age', help='Minimum patient age for this rule')
    age_max = fields.Integer('Maximum Age', help='Maximum patient age for this rule')
    gender = fields.Selection([
        ('male', 'Male'),
        ('female', 'Female'),
        ('other', 'Other')
    ], string='Gender', help='Apply rule only to specific gender')
    
    # Clinical requirements
    diagnosis_codes = fields.Char('Diagnosis Codes', 
                               help='Required diagnosis codes for coverage (e.g. ICD-10)')
    valid_prescriber_types = fields.Char('Valid Prescriber Types',
                                       help='Allowed prescriber credentials (e.g. MD, DO, NP)')
    
    # Financial limits
    max_amount_per_claim = fields.Float('Max Amount per Claim',
                                     help='Maximum claim amount per submission')
    
    # Priority (higher number = higher priority)
    priority = fields.Integer('Priority', default=10, help='Higher priority rules override lower priority rules')
    
    @api.constrains('product_id', 'category_id')
    def _check_product_or_category(self):
        for rule in self:
            if not rule.product_id and not rule.category_id:
                raise ValidationError(_('Either Product or Category must be specified'))
            if rule.product_id and rule.category_id:
                raise ValidationError(_('Cannot specify both Product and Category in the same rule'))

    @api.constrains('age_min', 'age_max')
    def _check_age_range(self):
        for rule in self:
            if rule.age_min and rule.age_max and rule.age_min > rule.age_max:
                raise ValidationError(_('Minimum age cannot be greater than maximum age'))

    @api.constrains('coverage_percentage', 'copay_percentage')
    def _check_percentage_limits(self):
        for rule in self:
            if rule.coverage_percentage < 0 or rule.coverage_percentage > 100:
                raise ValidationError(_('Coverage percentage must be between 0 and 100'))
            if rule.copay_percentage < 0 or rule.copay_percentage > 100:
                raise ValidationError(_('Co-pay percentage must be between 0 and 100'))
            if rule.coverage_percentage + rule.copay_percentage > 100:
                raise ValidationError(_('Coverage percentage + Co-pay percentage cannot exceed 100'))
    
    def name_get(self):
        result = []
        for rule in self:
            if rule.product_id:
                name = f"{rule.product_id.name}"
            elif rule.category_id:
                name = f"{rule.category_id.name} (Category)"
            else:
                name = "General Rule"
            
            if rule.is_exclusion:
                name = f"EXCLUDE: {name}"
            else:
                name = f"COVER: {name} ({rule.coverage_percentage}%)"
            
            result.append((rule.id, name))
        return result
    
    @api.model
    def get_coverage_for_product(self, plan_id, product_id, quantity=1, amount=0):
        """
        Get coverage rules for a specific product under a plan
        Returns the most specific rule (product > category > general)
        """
        domain = [
            ('plan_id', '=', plan_id),
            ('active', '=', True)
        ]
        
        # Try to find product-specific rule first
        product_rule = self.search(domain + [
            ('product_id', '=', product_id)
        ], order='priority DESC', limit=1)
        
        if product_rule:
            return product_rule
        
        # Try category-specific rule
        product = self.env['product.product'].browse(product_id)
        if product.categ_id:
            category_rule = self.search(domain + [
                ('category_id', '=', product.categ_id.id)
            ], order='priority DESC', limit=1)
            
            if category_rule:
                return category_rule
        
        # Return general rule if exists
        general_rule = self.search(domain + [
            ('product_id', '=', False),
            ('category_id', '=', False)
        ], order='priority DESC', limit=1)
        
        return general_rule
    
    def check_quantity_limits(self, plan_id, product_id, quantity, patient_id=None):
        """
        Check if quantity exceeds limits for this patient/month
        Returns: (allowed, reason, max_quantity)
        """
        rule = self.get_coverage_for_product(plan_id, product_id)
        
        if not rule or rule.is_exclusion:
            return False, 'Not covered', 0
        
        # Check per-visit limit
        if rule.max_quantity_per_visit and quantity > rule.max_quantity_per_visit:
            return False, f'Exceeds per-visit limit of {rule.max_quantity_per_visit}', rule.max_quantity_per_visit
        
        # Check per-month limit (would need patient_id to track monthly usage)
        if rule.max_quantity_per_month and patient_id:
            # This would require tracking monthly usage per patient
            # For now, just warn about the limit
            pass
        
        return True, 'Allowed', quantity
    
    def calculate_coverage(self, plan_id, product_id, quantity, unit_price):
        """
        Calculate coverage amounts for a product
        Returns: {
            'covered': True/False,
            'coverage_percentage': float,
            'copay_percentage': float,
            'copay_amount': float,
            'insurance_amount': float,
            'patient_amount': float,
            'reason': string
        }
        """
        rule = self.get_coverage_for_product(plan_id, product_id)
        
        if not rule:
            return {
                'covered': False,
                'coverage_percentage': 0,
                'copay_percentage': 100,
                'copay_amount': 0,
                'insurance_amount': 0,
                'patient_amount': quantity * unit_price,
                'reason': 'No coverage rule found'
            }
        
        if rule.is_exclusion:
            return {
                'covered': False,
                'coverage_percentage': 0,
                'copay_percentage': 100,
                'copay_amount': 0,
                'insurance_amount': 0,
                'patient_amount': quantity * unit_price,
                'reason': rule.exclusion_reason or 'Excluded by coverage rule'
            }
        
        total_amount = quantity * unit_price
        
        # Use fixed copay amount if specified
        if rule.copay_amount > 0:
            copay_amount = min(rule.copay_amount, total_amount)
            insurance_amount = total_amount - copay_amount
            copay_percentage = (copay_amount / total_amount) * 100 if total_amount > 0 else 0
        else:
            # Use percentage-based copay
            copay_percentage = rule.copay_percentage
            insurance_amount = total_amount * (rule.coverage_percentage / 100)
            copay_amount = total_amount - insurance_amount
        
        return {
            'covered': True,
            'coverage_percentage': rule.coverage_percentage,
            'copay_percentage': copay_percentage,
            'copay_amount': copay_amount,
            'insurance_amount': insurance_amount,
            'patient_amount': copay_amount,
            'reason': 'Covered by insurance plan'
        }
    
    def requires_preauthorization(self, plan_id, product_id, amount=0):
        """
        Check if pre-authorization is required for this product/amount
        """
        rule = self.get_coverage_for_product(plan_id, product_id)
        
        if not rule or rule.is_exclusion:
            return False
        
        if rule.require_preauth:
            return True
        
        if rule.preauth_threshold and amount >= rule.preauth_threshold:
            return True
        
        return False
    
    def requires_generic_substitution(self, plan_id, product_id):
        """
        Check if generic substitution is required
        """
        rule = self.get_coverage_for_product(plan_id, product_id)
        
        if not rule or rule.is_exclusion:
            return False
        
        return rule.require_generic_substitution
    
    def get_applicable_rules(self, plan_id):
        """
        Get all applicable rules for a plan
        """
        return self.search([
            ('plan_id', '=', plan_id),
            ('active', '=', True)
        ], order='priority DESC')
