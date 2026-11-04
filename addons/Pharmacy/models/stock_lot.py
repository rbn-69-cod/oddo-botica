# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import logging
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)


class StockLot(models.Model):
    _inherit = 'stock.lot'
    
    # Expiry information
    expiry_date = fields.Date('Fecha de Vencimiento', required=False, tracking=True, index=True)
    manufacturing_date = fields.Date('Fecha de Fabricación', tracking=True)
    
    # Expiry alerts (computed fields)
    expiry_alert_90 = fields.Boolean('Alerta 90 Días', compute='_compute_expiry_alerts', store=True)
    expiry_alert_60 = fields.Boolean('Alerta 60 Días', compute='_compute_expiry_alerts', store=True)
    expiry_alert_30 = fields.Boolean('Alerta 30 Días', compute='_compute_expiry_alerts', store=True)
    
    # Status fields
    is_expired = fields.Boolean('Lote Vencido', compute='_compute_expiry_status', store=True)
    is_quarantined = fields.Boolean('En Cuarentena', default=False, tracking=True)
    quarantine_reason = fields.Selection([
        ('expired', 'Vencido'),
        ('damaged', 'Dañado / Roto'),
        ('recalled', 'Retiro de Mercado / DIGEMID'),
        ('quality_issue', 'Observación de Calidad'),
        ('other', 'Otro')
    ], string='Motivo de Cuarentena')
    quarantine_notes = fields.Text('Notas de Cuarentena')
    
    # Additional fields for pharmacy
    batch_number = fields.Char('Número de Lote de Fabricante', help="Número de lote del laboratorio fabricante")
    manufacturer = fields.Char('Laboratorio / Fabricante')
    storage_location = fields.Char('Ubicación Física de Almacenamiento')
    
    # Computed fields
    days_to_expiry = fields.Integer('Días para Vencer', compute='_compute_days_to_expiry', store=True)
    expiry_status = fields.Selection([
        ('expired', 'Vencido'),
        ('expiring_30', 'Vence en 30 Días'),
        ('expiring_60', 'Vence en 60 Días'),
        ('expiring_90', 'Vence en 90 Días'),
        ('good', 'Vigente')
    ], string='Estado de Vencimiento', compute='_compute_expiry_status', store=True)
    
    # Stock information
    total_quantity = fields.Float(compute='_compute_total_quantity', store=True)
    available_quantity = fields.Float(compute='_compute_available_quantity', store=True)
    
    @api.depends('expiry_date')
    def _compute_days_to_expiry(self):
        today = fields.Date.today()
        for lot in self:
            if lot.expiry_date:
                lot.days_to_expiry = (lot.expiry_date - today).days
            else:
                lot.days_to_expiry = 0
    
    @api.depends('expiry_date', 'days_to_expiry')
    def _compute_expiry_alerts(self):
        for lot in self:
            if lot.days_to_expiry <= 90 and lot.days_to_expiry > 60:
                lot.expiry_alert_90 = True
                lot.expiry_alert_60 = False
                lot.expiry_alert_30 = False
            elif lot.days_to_expiry <= 60 and lot.days_to_expiry > 30:
                lot.expiry_alert_90 = True
                lot.expiry_alert_60 = True
                lot.expiry_alert_30 = False
            elif lot.days_to_expiry <= 30 and lot.days_to_expiry > 0:
                lot.expiry_alert_90 = True
                lot.expiry_alert_60 = True
                lot.expiry_alert_30 = True
            else:
                lot.expiry_alert_90 = False
                lot.expiry_alert_60 = False
                lot.expiry_alert_30 = False
    
    @api.depends('expiry_date', 'days_to_expiry')
    def _compute_expiry_status(self):
        for lot in self:
            if lot.days_to_expiry < 0:
                lot.is_expired = True
                lot.expiry_status = 'expired'
            elif lot.days_to_expiry <= 30:
                lot.is_expired = False
                lot.expiry_status = 'expiring_30'
            elif lot.days_to_expiry <= 60:
                lot.is_expired = False
                lot.expiry_status = 'expiring_60'
            elif lot.days_to_expiry <= 90:
                lot.is_expired = False
                lot.expiry_status = 'expiring_90'
            else:
                lot.is_expired = False
                lot.expiry_status = 'good'
    
    @api.model
    def action_send_expiry_alerts(self):
        """Send expiry alerts for lots about to expire (scheduled action)"""
        # Find lots expiring in the next 30 days
        expiring_soon = self.search([
            ('expiry_date', '>', fields.Date.today()),
            ('expiry_date', '<=', fields.Date.today() + timedelta(days=30)),
            ('is_quarantined', '=', False)
        ])
        
        if not expiring_soon:
            return 0
        
        # Batch fetch pharmacy managers once (avoid N+1 query)
        manager_group = (
            self.env.ref('Pharmacy.group_pharmacy_manager', raise_if_not_found=False)
            or self.env.ref('pharmacy.group_pharmacy_manager', raise_if_not_found=False)
        )
        if not manager_group:
            return len(expiring_soon)
        managers = self.env['res.users'].search([
            ('groups_id', 'in', manager_group.id)
        ])
        
        # Pre-fetch partner data
        managers.read(['partner_id', 'name'])
        
        for lot in expiring_soon:
            lot._send_expiry_alert_notification(managers)
        
        return len(expiring_soon)
    
    def _send_expiry_alert_notification(self, managers=None):
        """Send expiry alert notification for this lot"""
        self.ensure_one()
        
        # Use pre-fetched managers if provided, otherwise fetch
        if managers is None:
            manager_group = (
                self.env.ref('Pharmacy.group_pharmacy_manager', raise_if_not_found=False)
                or self.env.ref('pharmacy.group_pharmacy_manager', raise_if_not_found=False)
            )
            if not manager_group:
                return
            managers = self.env['res.users'].search([
                ('groups_id', 'in', manager_group.id)
            ])
        
        # Send notification to all managers
        for user in managers:
            self.message_post(
                body=f"<b>Alerta de Vencimiento de Lote</b><br/>"
                     f"Medicamento: {self.product_id.name}<br/>"
                     f"Lote: {self.name}<br/>"
                     f"Fecha de Vencimiento: {self.expiry_date}<br/>"
                     f"Días para Vencer: {self.days_to_expiry}<br/>"
                     f"Cantidad Disponible: {self.available_quantity}<br/>"
                     f"Estado: {dict(self._fields['expiry_status'].selection).get(self.expiry_status, self.expiry_status)}",
                subject=f"Alerta de Vencimiento: {self.product_id.name} - {self.name}",
                partner_ids=[user.partner_id.id]
            )
    
    @api.depends('quant_ids')
    def _compute_total_quantity(self):
        for lot in self:
            lot.total_quantity = sum(lot.quant_ids.mapped('quantity'))
    
    @api.depends('quant_ids')
    def _compute_available_quantity(self):
        for lot in self:
            # Only count quantity in internal locations (not customer/supplier)
            available_quants = lot.quant_ids.filtered(
                lambda q: q.location_id.usage in ['internal', 'transit']
            )
            lot.available_quantity = sum(available_quants.mapped('quantity'))
    
    @api.constrains('expiry_date')
    def _check_expiry_date(self):
        for lot in self:
            if lot.expiry_date and lot.expiry_date < fields.Date.today():
                # Auto-quarantine expired lots
                if not lot.is_quarantined:
                    lot.is_quarantined = True
                    lot.quarantine_reason = 'expired'
                    lot.quarantine_notes = f'Auto-quarantined on {fields.Date.today()} due to expiry date {lot.expiry_date}'
                    _logger.warning(f"Lot {lot.name} auto-quarantined due to expiry")
                    
                    # Send notification
                    lot._send_expiry_notification()
    
    @api.constrains('manufacturing_date', 'expiry_date')
    def _check_dates(self):
        for lot in self:
            if lot.manufacturing_date and lot.expiry_date:
                if lot.manufacturing_date >= lot.expiry_date:
                    raise ValidationError(_('La fecha de fabricación debe ser anterior a la fecha de vencimiento'))
    
    def action_quarantine(self, reason, notes=''):
        """Quarantine this lot"""
        self.write({
            'is_quarantined': True,
            'quarantine_reason': reason,
            'quarantine_notes': notes,
        })
        
        # Move all stock to quarantine location
        self._move_to_quarantine()
    
    def action_release_quarantine(self):
        """Release lot from quarantine"""
        if self.is_expired:
            raise ValidationError(_('No se puede liberar un lote vencido de la cuarentena'))
        
        self.write({
            'is_quarantined': False,
            'quarantine_reason': False,
            'quarantine_notes': False,
        })
    
    def _move_to_quarantine(self):
        """Move all stock of this lot to quarantine locations"""
        for quant in self.quant_ids:
            if quant.location_id.usage == 'internal' and quant.quantity > 0:
                # Find quarantine location for this branch
                branch = quant.location_id.branch_id
                if branch:
                    quarantine_location = branch.get_quarantine_location()
                    if quarantine_location:
                        # Create stock move to quarantine
                        self.env['stock.move']._create_split_move(quant, quarantine_location)
    
    def _send_expiry_notification(self):
        """Send notification about expired/quarantined lot"""
        self.ensure_one()
        
        # Find pharmacy managers to notify
        manager_group = (
            self.env.ref('Pharmacy.group_pharmacy_manager', raise_if_not_found=False)
            or self.env.ref('pharmacy.group_pharmacy_manager', raise_if_not_found=False)
        )
        users = self.env['res.users'].search([
            ('groups_id', 'in', manager_group.id)
        ]) if manager_group else []
        
        # Send notification
        for user in users:
            self.message_post(
                body=f"<b>Lot Quarantined Due to Expiry</b><br/>"
                     f"Product: {self.product_id.name}<br/>"
                     f"Lot: {self.name}<br/>"
                     f"Expiry Date: {self.expiry_date}<br/>"
                     f"Quantity: {self.available_quantity}<br/>"
                     f"Reason: Expired",
                subject=f"Expired Lot Quarantined: {self.name}",
                partner_ids=[user.partner_id.id]
            )
    
    def get_location_quantities(self):
        """Get quantity breakdown by location"""
        location_quantities = {}
        
        for quant in self.quant_ids:
            if quant.quantity > 0:
                location_name = quant.location_id.complete_name
                if location_name not in location_quantities:
                    location_quantities[location_name] = {
                        'location_id': quant.location_id.id,
                        'quantity': 0,
                        'branch': quant.location_id.branch_id.name if quant.location_id.branch_id else 'Unassigned'
                    }
                location_quantities[location_name]['quantity'] += quant.quantity
        
        return location_quantities
    
    def check_sale_allowed(self, quantity=1):
        """
        Check if sale is allowed for this lot
        Returns dict with allowed status and reason
        """
        result = {
            'allowed': True,
            'reason': '',
            'warnings': []
        }
        
        # Check if lot is expired
        if self.is_expired:
            result['allowed'] = False
            result['reason'] = 'El lote ha vencido y no se puede vender'
            return result
        
        # Check if lot is quarantined
        if self.is_quarantined:
            result['allowed'] = False
            result['reason'] = f'El lote está en cuarentena: {self.quarantine_reason}'
            return result
        
        # Check minimum expiry days
        if self.product_id and self.days_to_expiry < self.product_id.min_expiry_days:
            result['warnings'].append(f'El lote vence en {self.days_to_expiry} días')
        
        # Check available quantity
        if self.available_quantity < quantity:
            result['allowed'] = False
            result['reason'] = f'Stock insuficiente. Disponible: {self.available_quantity}, Solicitado: {quantity}'
            return result
        
        return result
    
    def get_expiry_info(self):
        """Get formatted expiry information"""
        if not self.expiry_date:
            return "Sin fecha de vencimiento"
        
        info = f"Vence: {self.expiry_date}"
        
        if self.is_expired:
            info += " (VENCIDO)"
        elif self.days_to_expiry <= 30:
            info += f" (Vence en {self.days_to_expiry} días)"
        elif self.days_to_expiry <= 90:
            info += f" (Vence en {self.days_to_expiry} días)"
        
        return info
    
    def get_batch_info(self):
        """Get formatted batch information"""
        parts = []
        
        if self.name:
            parts.append(f"Lot: {self.name}")
        if self.batch_number:
            parts.append(f"Batch: {self.batch_number}")
        if self.manufacturer:
            parts.append(f"Manufacturer: {self.manufacturer}")
        if self.expiry_date:
            parts.append(f"Expiry: {self.expiry_date}")
        
        return " | ".join(parts)
    
    @api.model
    def get_expiring_lots(self, days=30):
        """Get lots expiring within specified days"""
        target_date = fields.Date.today() + timedelta(days=days)
        
        return self.search([
            ('expiry_date', '<=', target_date),
            ('expiry_date', '>=', fields.Date.today()),
            ('is_expired', '=', False),
        ])
    
    @api.model
    def get_expired_lots(self):
        """Get all expired lots"""
        return self.search([('is_expired', '=', True)])
    
    @api.model
    def get_quarantined_lots(self):
        """Get all quarantined lots"""
        return self.search([('is_quarantined', '=', True)])
    
    @api.model
    def update_expiry_alerts(self):
        """Scheduled action to update expiry alerts"""
        lots = self.search([('expiry_date', '!=', False)])
        
        updated_count = 0
        for lot in lots:
            # Trigger recomputation of expiry status
            lot._compute_expiry_status()
            lot._compute_expiry_alerts()
            updated_count += 1
        
        _logger.info(f"Updated expiry alerts for {updated_count} lots")
        
        # Auto-quarantine expired lots
        expired_lots = lots.filtered(lambda l: l.is_expired and not l.is_quarantined)
        for lot in expired_lots:
            lot.action_quarantine('expired', 'Auto-quarantined due to expiry')
        
        _logger.info(f"Auto-quarantined {len(expired_lots)} expired lots")
    
    def action_view_stock_moves(self):
        """View stock moves for this lot"""
        return {
            'name': _('Movimientos de Stock'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.move.line',
            'view_mode': 'list,form',
            'domain': [('lot_id', '=', self.id)],
            'context': {'default_lot_id': self.id},
        }
    
    def action_print_expiry_label(self):
        """Print expiry label for this lot"""
        return self.env.ref('Pharmacy.action_report_lot_expiry_label').report_action(self)
    
    def write(self, vals):
        # If expiry date is being updated, check if it affects expiry status
        if 'expiry_date' in vals:
            old_expiry_date = self.expiry_date
            new_expiry_date = fields.Date.from_string(vals['expiry_date']) if vals['expiry_date'] else False
            
            # If lot was expired and new date is not expired, release from quarantine
            if old_expiry_date and new_expiry_date and old_expiry_date < fields.Date.today() and new_expiry_date >= fields.Date.today():
                if self.is_quarantined and self.quarantine_reason == 'expired':
                    vals['is_quarantined'] = False
                    vals['quarantine_reason'] = False
                    vals['quarantine_notes'] = False
        
        return super().write(vals)
