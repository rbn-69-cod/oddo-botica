# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import timedelta
import logging

_logger = logging.getLogger(__name__)


class BatchExpiryReportWizard(models.TransientModel):
    _name = 'batch.expiry.report.wizard'
    _description = 'Batch Expiry Report Wizard'
    
    branch_id = fields.Many2one('pharmacy.branch', 'Branch')
    category_id = fields.Many2one('product.category', 'Product Category')
    date_from = fields.Date('Date From')
    date_to = fields.Date('Date To')
    
    include_expired = fields.Boolean('Include Expired', default=True)
    include_near_expiry = fields.Boolean('Include Near Expiry', default=True)
    near_expiry_days = fields.Integer('Near Expiry Days', default=30)
    
    def action_generate_report(self):
        """Generate batch expiry report"""
        domain = []
        
        # Build domain
        if self.branch_id:
            # Get branch locations
            locations = self.branch_id.location_ids
            domain.append(('location_id', 'in', locations.ids))
        
        if self.category_id:
            domain.append(('product_id.categ_id', '=', self.category_id.id))
        
        # Expiry filters
        if not self.include_expired:
            domain.append(('lot_id.is_expired', '=', False))
        
        if self.include_near_expiry and self.near_expiry_days:
            target_date = fields.Date.today() + timedelta(days=self.near_expiry_days)
            domain.append(('lot_id.expiry_date', '<=', target_date))
            domain.append(('lot_id.expiry_date', '>=', fields.Date.today()))
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Batch Expiry Report'),
            'res_model': 'stock.quant',
            'view_mode': 'tree,form',
            'domain': domain,
            'context': {
                'search_default_group_by_lot': 1,
                'search_default_group_by_product': 1,
            },
        }
