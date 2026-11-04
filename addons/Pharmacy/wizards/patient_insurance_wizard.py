# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class PatientInsuranceWizard(models.TransientModel):
    _name = 'patient.insurance.wizard'
    _description = 'Patient Insurance Enrollment Wizard'
    
    patient_id = fields.Many2one('pharmacy.patient', 'Patient', required=True)
    insurer_id = fields.Many2one('pharmacy.insurer', 'Insurer', required=True)
    plan_id = fields.Many2one('pharmacy.insurer.plan', 'Insurance Plan', required=True,
                              domain="[('insurer_id', '=', insurer_id)]")
    
    member_number = fields.Char('Member Number', required=True)
    policy_number = fields.Char('Policy Number')
    relationship_to_member = fields.Selection([
        ('self', 'Self'),
        ('spouse', 'Spouse'),
        ('child', 'Child'),
        ('parent', 'Parent'),
        ('other', 'Other')
    ], string='Relationship to Member', default='self')
    
    valid_from = fields.Date('Valid From', required=True, default=fields.Date.today)
    valid_to = fields.Date('Valid To')
    
    coverage_percentage = fields.Float('Coverage Percentage', related='plan_id.coverage_percentage', readonly=True)
    copay_percentage = fields.Float('Co-pay Percentage', related='plan_id.copay_percentage', readonly=True)
    monthly_limit = fields.Float('Monthly Limit', related='plan_id.monthly_limit', readonly=True)
    per_visit_limit = fields.Float('Per Visit Limit', related='plan_id.per_visit_limit', readonly=True)
    
    @api.onchange('insurer_id')
    def _onchange_insurer_id(self):
        """Reset plan when insurer changes"""
        self.plan_id = False
    
    @api.constrains('valid_from', 'valid_to')
    def _check_dates(self):
        for wizard in self:
            if wizard.valid_to and wizard.valid_from > wizard.valid_to:
                raise ValidationError(_('Valid From date must be before Valid To date'))
    
    def action_enroll(self):
        """Enroll patient in insurance plan"""
        # Check if patient already has this insurance
        existing = self.env['pharmacy.patient.insurance'].search([
            ('patient_id', '=', self.patient_id.id),
            ('insurer_id', '=', self.insurer_id.id),
            ('member_number', '=', self.member_number),
            ('active', '=', True),
        ])
        
        if existing:
            raise ValidationError(_('Patient already enrolled in this insurance plan with this member number'))
        
        # Create patient insurance record
        insurance = self.env['pharmacy.patient.insurance'].create({
            'patient_id': self.patient_id.id,
            'insurer_id': self.insurer_id.id,
            'plan_id': self.plan_id.id,
            'member_number': self.member_number,
            'policy_number': self.policy_number,
            'relationship_to_member': self.relationship_to_member,
            'valid_from': self.valid_from,
            'valid_to': self.valid_to,
            'coverage_percentage': self.coverage_percentage,
            'copay_percentage': self.copay_percentage,
            'monthly_limit': self.monthly_limit,
            'per_visit_limit': self.per_visit_limit,
        })
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Patient Insurance'),
            'res_model': 'pharmacy.patient.insurance',
            'res_id': insurance.id,
            'view_mode': 'form',
            'target': 'current',
        }
