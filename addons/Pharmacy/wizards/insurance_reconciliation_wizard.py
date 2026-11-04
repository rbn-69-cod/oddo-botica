# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging
import base64

_logger = logging.getLogger(__name__)


class InsuranceReconciliationWizard(models.TransientModel):
    _name = 'insurance.reconciliation.wizard'
    _description = 'Insurance Claims Reconciliation Wizard'
    
    insurer_id = fields.Many2one('pharmacy.insurer', 'Insurer', required=True)
    date_from = fields.Date('Date From', required=True)
    date_to = fields.Date('Date To', required=True)
    
    reconciliation_type = fields.Selection([
        ('manual', 'Manual Reconciliation'),
        ('import', 'Import Statement'),
    ], string='Reconciliation Type', required=True, default='manual')
    
    claim_ids = fields.Many2many('pharmacy.claim', 'insurance_reconciliation_claim_rel',
                                 'wizard_id', 'claim_id', 'Claims to Reconcile',
                                 domain="[('insurer_id', '=', insurer_id), ('status', 'in', ['approved', 'partially_approved'])]")
    
    statement_file = fields.Binary('Statement File')
    filename = fields.Char('Filename')
    
    @api.onchange('insurer_id', 'date_from', 'date_to')
    def _onchange_dates(self):
        """Update claim domain when dates change"""
        if self.insurer_id and self.date_from and self.date_to:
            self.claim_ids = self.env['pharmacy.claim'].search([
                ('insurer_id', '=', self.insurer_id.id),
                ('claim_date', '>=', self.date_from),
                ('claim_date', '<=', self.date_to),
                ('status', 'in', ['approved', 'partially_approved', 'paid']),
            ])
    
    def action_reconcile(self):
        """Reconcile claims"""
        if not self.claim_ids:
            raise ValidationError(_('Please select at least one claim to reconcile'))
        
        if self.reconciliation_type == 'import':
            if not self.statement_file:
                raise ValidationError(_('Please upload statement file'))
            return self._import_and_reconcile()
        else:
            return self._manual_reconcile()
    
    def _manual_reconcile(self):
        """Manual reconciliation - mark selected claims as paid"""
        self.claim_ids.action_mark_paid()
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Reconciliation Complete'),
                'message': _('%d claims marked as paid') % len(self.claim_ids),
                'type': 'success',
                'sticky': False,
            }
        }
    
    def _import_and_reconcile(self):
        """Import statement and reconcile claims"""
        # TODO: Implement statement import logic
        # This would parse the uploaded file and match claims
        raise ValidationError(_('Statement import not yet implemented'))
