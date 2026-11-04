# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)


class PharmacyPatientInsurance(models.Model):
    _name = 'pharmacy.patient.insurance'
    _description = 'Patient Insurance Policy'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'valid_from desc'
    _rec_name = 'display_name'
    
    patient_id = fields.Many2one('pharmacy.patient', 'Patient', required=True, ondelete='cascade',
                                help='The patient who holds this insurance policy')
    insurer_id = fields.Many2one('pharmacy.insurer', 'Insurer', required=True)
    plan_id = fields.Many2one('pharmacy.insurer.plan', 'Insurance Plan', required=True)
    member_number = fields.Char('Member Number', required=True, tracking=True)
    
    # Direct link to customer for convenience
    customer_id = fields.Many2one('res.partner', 'Customer', related='patient_id.partner_id', 
                                 store=False, readonly=True,
                                 help='The customer record linked to this patient')
    
    # Validity period
    valid_from = fields.Date('Valid From', required=True, tracking=True)
    valid_to = fields.Date('Valid To', required=True, tracking=True)
    
    # Coverage details
    status = fields.Selection([
        ('active', 'Active'),
        ('suspended', 'Suspended'),
        ('expired', 'Expired')
    ], string='Status', default='active', tracking=True, compute='_compute_status', store=True)
    
    copay_percentage = fields.Float('Co-pay Percentage', default=0.0, tracking=True)
    coverage_percentage = fields.Float('Coverage Percentage', related='plan_id.coverage_percentage', store=True)
    
    # Additional information
    policy_number = fields.Char('Policy Number')
    card_number = fields.Char('Card Number')
    relationship_to_member = fields.Selection([
        ('self', 'Self'),
        ('spouse', 'Spouse'),
        ('child', 'Child'),
        ('parent', 'Parent'),
        ('other', 'Other')
    ], string='Relationship to Member', default='self')
    
    notes = fields.Text('Notes')
    
    # Computed fields
    display_name = fields.Char(compute='_compute_display_name', store=True)
    is_expired = fields.Boolean(compute='_compute_status', store=True)
    days_to_expiry = fields.Integer(compute='_compute_days_to_expiry', store=True)
    
    company_id = fields.Many2one('res.company', 'Company', required=True,
                                default=lambda self: self.env.company)
    
    @api.depends('patient_id', 'insurer_id', 'member_number')
    def _compute_display_name(self):
        for insurance in self:
            insurance.display_name = f"{insurance.patient_id.name} - {insurance.insurer_id.name} ({insurance.member_number})"
    
    @api.depends('valid_from', 'valid_to')
    def _compute_status(self):
        today = fields.Date.today()
        for insurance in self:
            if not insurance.valid_to or not insurance.valid_from:
                insurance.status = 'active'
                insurance.is_expired = False
            elif insurance.valid_to < today:
                insurance.status = 'expired'
                insurance.is_expired = True
            elif insurance.valid_from > today:
                insurance.status = 'suspended'
                insurance.is_expired = False
            else:
                insurance.status = 'active'
                insurance.is_expired = False
    
    @api.depends('valid_to')
    def _compute_days_to_expiry(self):
        today = fields.Date.today()
        for insurance in self:
            if insurance.valid_to:
                insurance.days_to_expiry = (insurance.valid_to - today).days
            else:
                insurance.days_to_expiry = 0
    
    @api.constrains('valid_from', 'valid_to')
    def _check_dates(self):
        for insurance in self:
            if insurance.valid_from and insurance.valid_to:
                if insurance.valid_from >= insurance.valid_to:
                    raise ValidationError(_('Valid From date must be before Valid To date'))
    
    @api.constrains('member_number')
    def _check_member_number_unique(self):
        for insurance in self:
            # Check uniqueness within the same insurer
            duplicates = self.search([
                ('insurer_id', '=', insurance.insurer_id.id),
                ('member_number', '=', insurance.member_number),
                ('id', '!=', insurance.id)
            ])
            if duplicates:
                raise ValidationError(_('Member number must be unique within the same insurer'))
    
    def action_extend_validity(self, new_valid_to):
        """Extend the validity period of the insurance policy"""
        if not self.valid_to or new_valid_to <= self.valid_to:
            raise ValidationError(_('New valid to date must be after current valid to date'))
        
        self.write({'valid_to': new_valid_to})
    
    def action_suspend(self):
        """Suspend the insurance policy"""
        self.write({'status': 'suspended'})
    
    def action_activate(self):
        """Activate the insurance policy"""
        today = fields.Date.today()
        if not self.valid_to or not self.valid_from:
            raise ValidationError(_('Insurance policy must have valid from and to dates'))
        if self.valid_to < today:
            raise ValidationError(_('Cannot activate expired policy. Please extend validity first.'))
        
        if self.valid_from > today:
            self.write({'valid_from': today})
        
        self.write({'status': 'active'})
    
    def check_coverage(self, product_id, quantity=1, date=None):
        """
        Check if a product is covered under this insurance policy
        Returns: dict with coverage details
        """
        if self.status != 'active':
            return {
                'covered': False,
                'reason': 'Insurance policy is not active'
            }
        
        if date and (not self.valid_from or not self.valid_to or self.valid_from > date or self.valid_to < date):
            return {
                'covered': False,
                'reason': 'Insurance policy not valid on this date'
            }
        
        # Check coverage rules from the plan
        coverage_result = self.plan_id.check_coverage(product_id, quantity)
        
        # Apply patient-specific copay if different from plan
        if self.copay_percentage != self.plan_id.copay_percentage:
            coverage_result['copay_percentage'] = self.copay_percentage
            coverage_result['coverage_percentage'] = 100 - self.copay_percentage
        
        return coverage_result
    
    def get_coverage_summary(self):
        """Get a summary of coverage details"""
        return {
            'insurer': self.insurer_id.name,
            'plan': self.plan_id.name,
            'member_number': self.member_number,
            'coverage_percentage': self.coverage_percentage,
            'copay_percentage': self.copay_percentage,
            'valid_from': self.valid_from,
            'valid_to': self.valid_to,
            'status': self.status,
            'days_to_expiry': self.days_to_expiry,
        }
