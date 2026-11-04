# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import logging
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)


class PharmacyPrescription(models.Model):
    _name = 'pharmacy.prescription'
    _description = 'Pharmacy Prescription'
    _order = 'prescription_date desc'
    _rec_name = 'display_name'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    
    name = fields.Char('Prescription Number', required=True, copy=False, readonly=True,
                       default=lambda self: _('New'))
    display_name = fields.Char(compute='_compute_display_name', store=True)
    
    # Patient and Prescriber
    patient_id = fields.Many2one('pharmacy.patient', 'Patient', required=True, tracking=True)
    prescriber_name = fields.Char('Prescriber Name', required=True, tracking=True)
    prescriber_license = fields.Char('Prescriber License', tracking=True)
    prescriber_phone = fields.Char('Prescriber Phone')
    prescriber_email = fields.Char('Prescriber Email')
    
    # Prescription details
    prescription_date = fields.Date('Prescription Date', required=True, tracking=True,
                                    default=fields.Date.today)
    diagnosis = fields.Text('Diagnosis', tracking=True)
    notes = fields.Text('Notes')
    
    # Status and validity
    status = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('partially_dispensed', 'Partially Dispensed'),
        ('fully_dispensed', 'Fully Dispensed'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled')
    ], string='Status', default='draft', tracking=True)
    
    expiry_date = fields.Date('Expiry Date', compute='_compute_expiry_date', store=True)
    validity_days = fields.Integer('Validity Days', default=90, tracking=True)
    
    # Related records
    line_ids = fields.One2many('pharmacy.prescription.line', 'prescription_id', 'Prescription Lines')
    dispensing_ids = fields.One2many('pharmacy.dispensing', 'prescription_id', 'Dispensing Records')
    
    # Computed fields
    total_items = fields.Integer(compute='_compute_totals', store=True)
    total_quantity_prescribed = fields.Float(compute='_compute_totals', store=True)
    total_quantity_dispensed = fields.Float(compute='_compute_totals', store=True)
    dispensing_percentage = fields.Float(compute='_compute_totals', store=True)
    
    # Branch context
    branch_id = fields.Many2one('pharmacy.branch', 'Branch', tracking=True)
    
    company_id = fields.Many2one('res.company', 'Company', required=True,
                                default=lambda self: self.env.company)
    
    @api.depends('name', 'patient_id')
    def _compute_display_name(self):
        for prescription in self:
            prescription.display_name = f"{prescription.name} - {prescription.patient_id.name}"
    
    @api.depends('prescription_date', 'validity_days')
    def _compute_expiry_date(self):
        for prescription in self:
            if prescription.prescription_date and prescription.validity_days:
                prescription.expiry_date = prescription.prescription_date + timedelta(days=prescription.validity_days)
            else:
                prescription.expiry_date = False
    
    @api.depends('line_ids', 'dispensing_ids')
    def _compute_totals(self):
        for prescription in self:
            prescription.total_items = len(prescription.line_ids)
            prescription.total_quantity_prescribed = sum(prescription.line_ids.mapped('quantity_prescribed'))
            prescription.total_quantity_dispensed = sum(prescription.line_ids.mapped('quantity_dispensed'))
            
            if prescription.total_quantity_prescribed > 0:
                prescription.dispensing_percentage = (prescription.total_quantity_dispensed / 
                                                     prescription.total_quantity_prescribed) * 100
            else:
                prescription.dispensing_percentage = 0
    
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self._generate_prescription_number()
        
        prescriptions = super().create(vals_list)
        
        # Auto-activate if lines are added
        for prescription in prescriptions:
            if prescription.line_ids and prescription.status == 'draft':
                prescription.action_activate()
        
        return prescriptions
    
    def _generate_prescription_number(self):
        """Generate unique prescription number"""
        sequence = self.env['ir.sequence'].next_by_code('pharmacy.prescription') or _('New')
        return f"RX{sequence}"
    
    def action_activate(self):
        """Activate the prescription"""
        if not self.line_ids:
            raise ValidationError(_('Cannot activate prescription without any prescription lines'))
        
        self.write({'status': 'active'})
        
        # Auto-create dispensing records if configured
        for prescription in self:
            if prescription.branch_id:
                try:
                    prescription._create_pending_dispensing_records()
                except Exception as e:
                    _logger.warning(f"Failed to auto-create dispensing records for prescription {prescription.name}: {str(e)}")
    
    def action_cancel(self):
        """Cancel the prescription"""
        if self.status in ['partially_dispensed', 'fully_dispensed']:
            raise ValidationError(_('Cannot cancel prescription that has been partially or fully dispensed'))
        
        self.write({'status': 'cancelled'})
    
    def action_expire(self):
        """Mark prescription as expired"""
        self.write({'status': 'expired'})
    
    def check_dispensing_allowed(self, product_id, quantity):
        """
        Check if dispensing is allowed for this prescription
        Returns: dict with allowed status and remaining quantity
        """
        if self.status not in ['active', 'partially_dispensed']:
            return {
                'allowed': False,
                'reason': f'Prescription status is {self.status}',
                'remaining_quantity': 0
            }
        
        # Check expiry
        if self.expiry_date and self.expiry_date < fields.Date.today():
            self.action_expire()
            return {
                'allowed': False,
                'reason': 'Prescription has expired',
                'remaining_quantity': 0
            }
        
        # Find the prescription line for this product
        line = self.line_ids.filtered(lambda l: l.product_id.id == product_id)
        if not line:
            return {
                'allowed': False,
                'reason': 'Product not found in prescription',
                'remaining_quantity': 0
            }
        
        # Check remaining quantity
        remaining = line.quantity_remaining
        if remaining <= 0:
            return {
                'allowed': False,
                'reason': 'Prescription quantity already fully dispensed',
                'remaining_quantity': 0
            }
        
        if quantity > remaining:
            return {
                'allowed': False,
                'reason': f'Quantity exceeds remaining prescription quantity ({remaining})',
                'remaining_quantity': remaining
            }
        
        return {
            'allowed': True,
            'remaining_quantity': remaining - quantity
        }
    
    def _create_pending_dispensing_records(self):
        """Create pending dispensing records for all prescription lines"""
        self.ensure_one()
        
        for line in self.line_ids:
            if line.quantity_prescribed > 0:
                dispensing_vals = {
                    'prescription_id': self.id,
                    'prescription_line_id': line.id,
                    'patient_id': self.patient_id.id,
                    'product_id': line.product_id.id,
                    'quantity': line.quantity_prescribed,
                    'branch_id': self.branch_id.id,
                    'company_id': self.company_id.id,
                    'dispensed_by': self.env.user.id,
                    'dispensed_date': fields.Datetime.now(),
                    'dosage_instructions': line.dosage_instructions,
                }
                
                try:
                    self.env['pharmacy.dispensing'].create(dispensing_vals)
                    _logger.info(f"Created pending dispensing record for product {line.product_id.name} in prescription {self.name}")
                except Exception as e:
                    _logger.error(f"Failed to create dispensing record for line {line.id}: {str(e)}")
    
    def record_dispensing(self, product_id, quantity, lot_id, branch_id, dispensed_by):
        """
        Record dispensing against this prescription
        """
        check_result = self.check_dispensing_allowed(product_id, quantity)
        if not check_result['allowed']:
            raise ValidationError(check_result['reason'])
        
        # Create dispensing record
        dispensing = self.env['pharmacy.dispensing'].create({
            'prescription_id': self.id,
            'patient_id': self.patient_id.id,
            'product_id': product_id,
            'quantity': quantity,
            'lot_id': lot_id,
            'branch_id': branch_id,
            'dispensed_by': dispensed_by,
        })
        
        # Update prescription status if fully dispensed
        if self.dispensing_percentage >= 100:
            self.write({'status': 'fully_dispensed'})
        elif self.dispensing_percentage > 0:
            self.write({'status': 'partially_dispensed'})
        
        return dispensing
    
    def get_dispensing_history(self):
        """Get dispensing history for this prescription"""
        return self.dispensing_ids.sorted('dispensed_date', reverse=True)
    
    def action_view_dispensing(self):
        """View dispensing records for this prescription"""
        return {
            'name': _('Dispensing Records'),
            'type': 'ir.actions.act_window',
            'res_model': 'pharmacy.dispensing',
            'view_mode': 'list,form',
            'domain': [('prescription_id', '=', self.id)],
            'context': {'default_prescription_id': self.id},
        }
    
    def print_prescription(self):
        """Print prescription report"""
        return self.env.ref('Pharmacy.action_report_prescription').report_action(self)
    
    @api.model
    def get_expired_prescriptions(self):
        """Get all expired prescriptions"""
        today = fields.Date.today()
        return self.search([
            ('expiry_date', '<', today),
            ('status', 'in', ['active', 'partially_dispensed'])
        ])
    
    @api.model
    def update_expired_prescriptions(self):
        """Scheduled action to update expired prescriptions"""
        expired = self.get_expired_prescriptions()
        for prescription in expired:
            prescription.action_expire()
        
        _logger.info(f"Updated {len(expired)} expired prescriptions")


class PharmacyPrescriptionLine(models.Model):
    _name = 'pharmacy.prescription.line'
    _description = 'Prescription Line'
    _order = 'id'
    
    prescription_id = fields.Many2one('pharmacy.prescription', 'Prescription', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', 'Product', required=True)
    
    # Quantities
    quantity_prescribed = fields.Float('Quantity Prescribed', required=True, default=1.0)
    quantity_dispensed = fields.Float('Quantity Dispensed', readonly=True, compute='_compute_quantity_dispensed', store=True)
    quantity_remaining = fields.Float('Quantity Remaining', compute='_compute_quantity_remaining', store=True)
    
    # Dosage instructions
    dosage_instructions = fields.Text('Dosage Instructions')
    frequency = fields.Char('Frequency', help="e.g., 3 times daily")
    duration_days = fields.Integer('Duration (Days)')
    
    # Substitution rules
    allow_generic_substitution = fields.Boolean('Allow Generic Substitution', default=True)
    require_pharmacist_approval = fields.Boolean('Require Pharmacist Approval', default=False)
    
    # Related dispensing records
    dispensing_ids = fields.One2many('pharmacy.dispensing', 'prescription_line_id', 'Dispensing Records')
    
    # Product details (related fields for display)
    product_name = fields.Char(related='product_id.name', readonly=True)
    generic_name = fields.Char(related='product_id.generic_name', readonly=True)
    strength = fields.Char(related='product_id.strength', readonly=True)
    dosage_form = fields.Selection(related='product_id.dosage_form', readonly=True)
    
    @api.depends('dispensing_ids')
    def _compute_quantity_dispensed(self):
        for line in self:
            line.quantity_dispensed = sum(line.dispensing_ids.mapped('quantity'))
    
    @api.depends('quantity_prescribed', 'quantity_dispensed')
    def _compute_quantity_remaining(self):
        for line in self:
            line.quantity_remaining = line.quantity_prescribed - line.quantity_dispensed
    
    @api.constrains('quantity_prescribed')
    def _check_quantity_prescribed(self):
        for line in self:
            if line.quantity_prescribed <= 0:
                raise ValidationError(_('Quantity prescribed must be greater than 0'))
    
    def get_dosage_summary(self):
        """Get formatted dosage summary"""
        parts = []
        if self.frequency:
            parts.append(self.frequency)
        if self.duration_days:
            parts.append(f"for {self.duration_days} days")
        if self.dosage_instructions:
            parts.append(self.dosage_instructions)
        
        return ' '.join(parts)

    def unlink(self):
        """Override unlink to handle related records properly"""
        for prescription in self:
            # Check for active dispensing records
            active_dispensing = self.env['pharmacy.dispensing'].search([
                ('prescription_id', '=', prescription.id),
                ('dispensed_date', '>=', fields.Date.today())
            ])
            
            if active_dispensing:
                raise UserError(_(
                    'Cannot delete prescription %s. There are %d active dispensing records. '
                    'Please complete dispensing first.' % (
                        prescription.name, len(active_dispensing)
                    )
                ))
            
            # Check for related insurance claims
            related_claims = self.env['pharmacy.claim'].search([
                ('prescription_id', '=', prescription.id),
                ('status', 'in', ['submitted', 'approved', 'partially_approved'])
            ])
            
            if related_claims:
                raise UserError(_(
                    'Cannot delete prescription %s. There are %d insurance claims in progress. '
                    'Please resolve claims first.' % (
                        prescription.name, len(related_claims)
                    )
                ))
        
        return super(PharmacyPrescription, self).unlink()
