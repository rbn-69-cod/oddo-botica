import { Component, OnInit } from '@angular/core';
import { AuditLogService, AuditLogResponse } from '../../core/services/audit-log.service';
import { DialogService } from '../../core/services/dialog.service';
import { formatDateTime } from '../../core/utils/date-time.util';

@Component({
  selector: 'app-user-activity',
  standalone: false,
  templateUrl: './user-activity.component.html',
  styleUrls: ['./user-activity.component.scss']
})
export class UserActivityComponent implements OnInit {
  auditLogs: AuditLogResponse[] = [];
  filteredLogs: AuditLogResponse[] = [];
  isLoading = false;
  searchTerm = '';
  selectedAction: string = 'ALL';
  selectedUser: string = 'ALL';
  
  uniqueUsers: string[] = [];
  uniqueActions: string[] = [];

  constructor(
    private auditLogService: AuditLogService,
    private dialogService: DialogService
  ) {}

  ngOnInit(): void {
    this.loadAuditLogs();
  }

  loadAuditLogs(): void {
    this.isLoading = true;
    this.auditLogService.getAllAuditLogs().subscribe({
      next: (logs) => {
        // Los accesos tienen su propia pantalla: aquí solo se muestran
        // operaciones realizadas dentro del sistema.
        this.auditLogs = logs
          .filter(log => log.action !== 'USER_LOGIN' && log.action !== 'USER_LOGOUT')
          .slice(0, 50);
        this.filteredLogs = this.auditLogs;
        this.extractUniqueValues();
        this.isLoading = false;
      },
      error: (error) => {
        console.error('Error loading audit logs:', error);
        this.isLoading = false;
      }
    });
  }

  extractUniqueValues(): void {
    this.uniqueUsers = [...new Set(this.auditLogs.map(log => log.username))].sort();
    this.uniqueActions = [...new Set(this.auditLogs.map(log => log.action))].sort();
  }

  filterLogs(): void {
    this.filteredLogs = this.auditLogs.filter(log => {
      const matchesSearch = !this.searchTerm || 
        log.username.toLowerCase().includes(this.searchTerm.toLowerCase()) ||
        log.fullName.toLowerCase().includes(this.searchTerm.toLowerCase()) ||
        log.description.toLowerCase().includes(this.searchTerm.toLowerCase()) ||
        log.entityType.toLowerCase().includes(this.searchTerm.toLowerCase());
      
      const matchesAction = this.selectedAction === 'ALL' || log.action === this.selectedAction;
      const matchesUser = this.selectedUser === 'ALL' || log.username === this.selectedUser;
      
      return matchesSearch && matchesAction && matchesUser;
    });
  }

  getActionBadgeClass(action: string): string {
    if (action.includes('LOGIN') || action.includes('LOGOUT')) {
      return 'badge-login';
    } else if (action.includes('CREATE') || action.includes('ADD')) {
      return 'badge-success';
    } else if (action.includes('UPDATE') || action.includes('ADJUST')) {
      return 'badge-warning';
    } else if (action.includes('DELETE') || action.includes('CANCEL')) {
      return 'badge-danger';
    }
    return 'badge-info';
  }

  formatDate(dateString: string): string {
    return formatDateTime(dateString);
  }

  getRoleLabel(role: string): string {
    const labels: Record<string, string> = {
      ADMIN: 'Administrador', CASHIER: 'Cajero', STOCK_MONITOR: 'Supervisor de inventario',
      STOCK_KEEPER: 'Encargado de almacén', CUSTOMER_SUPPORT: 'Atención al cliente',
      ANALYST: 'Analista', MANAGER: 'Gerente'
    };
    return labels[role] || role;
  }

  getActionLabel(action: string): string {
    const labels: Record<string, string> = {
        BILL_CREATED: 'Venta registrada', BILL_CANCELLED: 'Venta anulada', PURCHASE_CREATED: 'Pedido de compra creado',
      PAYMENT_RECEIVED: 'Pago recibido', REFUND_PROCESSED: 'Reembolso procesado',
      STOCK_ADJUSTED: 'Inventario ajustado', STOCK_UPDATED: 'Inventario actualizado',
      PRICE_OVERRIDE: 'Precio modificado', MEDICINE_ADDED: 'Medicamento agregado',
      MEDICINE_UPDATED: 'Medicamento actualizado', MEDICINE_DELETED: 'Medicamento eliminado',
      BATCH_ADDED: 'Lote agregado', BATCH_UPDATED: 'Lote actualizado', BATCH_DELETED: 'Lote eliminado',
      USER_LOGIN: 'Ingreso al sistema', USER_LOGOUT: 'Cierre de sesión',
      USER_PASSWORD_CHANGED: 'Contraseña actualizada', USER_STATUS_CHANGED: 'Estado de usuario actualizado'
    };
    return labels[action] || action.replace(/_/g, ' ');
  }

  getEntityLabel(entity: string): string {
    const labels: Record<string, string> = {
      USER: 'Usuario', MEDICINE: 'Medicamento', BATCH: 'Lote', BILL: 'Venta',
      RETURN: 'Devolución', STOCK: 'Inventario', PAYMENT: 'Pago'
    };
    return labels[entity.toUpperCase()] || entity;
  }

  getDescriptionLabel(description: string): string {
    return description
      .replace('User logged in', 'El usuario ingresó al sistema')
      .replace('User logged out', 'El usuario cerró sesión')
      .replace('Bill created:', 'Venta registrada:')
      .replace('Bill cancelled:', 'Venta anulada:')
      .replace('Medicine created:', 'Medicamento creado:')
      .replace('Medicine updated:', 'Medicamento actualizado:')
      .replace('Medicine deleted:', 'Medicamento eliminado:')
      .replace('Medicine status updated', 'Estado del medicamento actualizado')
      .replace('Batch created:', 'Lote creado:')
      .replace('Batch updated:', 'Lote actualizado:')
      .replace('Batch deleted:', 'Lote eliminado:')
      .replace('Stock updated for batch:', 'Inventario actualizado para el lote:')
      .replace('Return processed:', 'Devolución procesada:')
      .replace('Password changed', 'Contraseña actualizada');
  }

  clearAllLogs(): void {
    this.dialogService.confirm(
      '¿Deseas eliminar todos los registros de actividad? Esta acción no se puede deshacer.',
      'Limpiar actividad de usuarios'
    ).then((confirmed) => {
      if (confirmed) {
        this.isLoading = true;
        this.auditLogService.deleteAllAuditLogs().subscribe({
          next: () => {
            this.auditLogs = [];
            this.filteredLogs = [];
            this.uniqueUsers = [];
            this.uniqueActions = [];
            this.isLoading = false;
            this.dialogService.success('Los registros de actividad se eliminaron correctamente.');
          },
          error: (error) => {
            console.error('Error clearing audit logs:', error);
            this.dialogService.error('No se pudieron limpiar los registros. Inténtalo nuevamente.');
            this.isLoading = false;
          }
        });
      }
    });
  }
}
