# -*- coding: utf-8 -*-
"""
Audit Log Model for Pharmacy System

Tracks all sensitive operations for regulatory compliance and security auditing.
"""

from odoo import models, fields, api
from datetime import datetime


class PharmacyAuditLog(models.Model):
    """Audit log for sensitive pharmacy operations"""
    _name = 'pharmacy.audit.log'
    _description = 'Pharmacy Audit Log'
    _order = 'create_date desc'
    _rec_name = 'operation'
    
    # Operation details
    operation = fields.Char('Operation', required=True, index=True, help='Type of operation performed')
    model_name = fields.Char('Model', required=True, index=True, help='Model on which operation was performed')
    record_id = fields.Integer('Record ID', index=True, help='ID of the affected record')
    record_name = fields.Char('Record Name', help='Name of the affected record')
    
    # User details
    user_id = fields.Many2one('res.users', 'User', required=True, index=True, help='User who performed the operation')
    user_name = fields.Char('User Name', help='Name of the user who performed the operation')
    
    # Context details
    ip_address = fields.Char('IP Address', help='IP address from which operation was performed')
    branch_id = fields.Many2one('pharmacy.branch', 'Branch', help='Branch where operation was performed')
    
    # Data changes
    old_values = fields.Text('Old Values', help='Previous values before change (JSON)')
    new_values = fields.Text('New Values', help='New values after change (JSON)')
    
    # Metadata
    create_date = fields.Datetime('Timestamp', required=True, index=True, help='When the operation was performed')
    correlation_id = fields.Char('Correlation ID', help='Correlation ID for tracking related operations')
    
    # Status
    success = fields.Boolean('Success', default=True, help='Whether the operation was successful')
    error_message = fields.Text('Error Message', help='Error message if operation failed')
    
    @api.model
    def log_operation(self, operation, model_name, record_id, record_name=None, 
                     old_values=None, new_values=None, success=True, error_message=None,
                     correlation_id=None, ip_address=None, branch_id=None):
        """
        Log an audit operation
        
        Args:
            operation: Type of operation (create, write, unlink, approve, reject, etc.)
            model_name: Model name
            record_id: Record ID
            record_name: Record name (optional)
            old_values: Previous values as JSON string
            new_values: New values as JSON string
            success: Whether operation was successful
            error_message: Error message if failed
            correlation_id: Correlation ID for tracking
            ip_address: IP address
            branch_id: Branch ID
        """
        self.create({
            'operation': operation,
            'model_name': model_name,
            'record_id': record_id,
            'record_name': record_name,
            'user_id': self.env.user.id,
            'user_name': self.env.user.name,
            'old_values': old_values,
            'new_values': new_values,
            'success': success,
            'error_message': error_message,
            'correlation_id': correlation_id,
            'ip_address': ip_address,
            'branch_id': branch_id,
        })
    
    @api.model
    def log_sensitive_operation(self, operation, record, old_values=None, new_values=None):
        """
        Log a sensitive operation with automatic context extraction
        
        Args:
            operation: Type of operation
            record: The record being operated on
            old_values: Previous values (dict)
            new_values: New values (dict)
        """
        import json
        
        # Get branch from record if available
        branch_id = None
        if hasattr(record, 'branch_id') and record.branch_id:
            branch_id = record.branch_id.id
        
        # Convert dicts to JSON
        old_json = json.dumps(old_values) if old_values else None
        new_json = json.dumps(new_values) if new_values else None
        
        self.log_operation(
            operation=operation,
            model_name=record._name,
            record_id=record.id,
            record_name=record.name if hasattr(record, 'name') else str(record.id),
            old_values=old_json,
            new_values=new_json,
            branch_id=branch_id,
        )
    
    @api.model
    def get_audit_trail(self, model_name, record_id, limit=100):
        """
        Get audit trail for a specific record
        
        Args:
            model_name: Model name
            record_id: Record ID
            limit: Maximum number of records to return
            
        Returns:
            Audit log records
        """
        return self.search([
            ('model_name', '=', model_name),
            ('record_id', '=', record_id),
        ], limit=limit, order='create_date desc')
    
    @api.model
    def get_user_activity(self, user_id, date_from=None, date_to=None, limit=100):
        """
        Get user activity log
        
        Args:
            user_id: User ID
            date_from: Start date
            date_to: End date
            limit: Maximum number of records
            
        Returns:
            Audit log records
        """
        domain = [('user_id', '=', user_id)]
        
        if date_from:
            domain.append(('create_date', '>=', date_from))
        if date_to:
            domain.append(('create_date', '<=', date_to))
        
        return self.search(domain, limit=limit, order='create_date desc')
    
    @api.model
    def get_sensitive_operations(self, date_from=None, date_to=None, limit=100):
        """
        Get all sensitive operations (controlled substances, insurance claims, etc.)
        
        Args:
            date_from: Start date
            date_to: End date
            limit: Maximum number of records
            
        Returns:
            Audit log records
        """
        sensitive_models = [
            'pharmacy.controlled_substance_register',
            'pharmacy.claim',
            'pharmacy.dispensing',
            'pharmacy.prescription',
        ]
        
        domain = [('model_name', 'in', sensitive_models)]
        
        if date_from:
            domain.append(('create_date', '>=', date_from))
        if date_to:
            domain.append(('create_date', '<=', date_to))
        
        return self.search(domain, limit=limit, order='create_date desc')
    
    @api.model
    def cleanup_old_logs(self, days_to_keep=365):
        """
        Clean up audit logs older than specified days
        
        Args:
            days_to_keep: Number of days to keep logs
        """
        from datetime import timedelta
        
        cutoff_date = datetime.now() - timedelta(days=days_to_keep)
        old_logs = self.search([
            ('create_date', '<', cutoff_date)
        ])
        
        count = len(old_logs)
        old_logs.unlink()
        
        return count


class PharmacyAuditLogMixin(models.AbstractModel):
    """Mixin to add audit logging to models"""
    _name = 'pharmacy.audit.log.mixin'
    _description = 'Pharmacy Audit Log Mixin'
    
    def _log_audit_operation(self, operation, old_values=None, new_values=None):
        """Log audit operation for this record"""
        if self._audit_log_enabled():
            self.env['pharmacy.audit.log'].log_sensitive_operation(
                operation=operation,
                record=self,
                old_values=old_values,
                new_values=new_values,
            )
    
    def _audit_log_enabled(self):
        """Check if audit logging is enabled for this model"""
        # Can be overridden or configured via system parameter
        return self.env['ir.config_parameter'].sudo().get_param(
            'pharmacy.enable_audit_logging', 'True'
        ) == 'True'
    
    def write(self, vals):
        """Override write to log changes"""
        # Get old values before write
        old_values = {}
        for record in self:
            old_values[record.id] = {}
            for field in vals.keys():
                if hasattr(record, field):
                    old_values[record.id][field] = getattr(record, field)
        
        # Perform write
        result = super().write(vals)
        
        # Log changes
        for record in self:
            new_values = {k: vals.get(k) for k in vals.keys()}
            record._log_audit_operation('write', old_values.get(record.id), new_values)
        
        return result
    
    def unlink(self):
        """Override unlink to log deletion"""
        for record in self:
            record._log_audit_operation('unlink')
        
        return super().unlink()
