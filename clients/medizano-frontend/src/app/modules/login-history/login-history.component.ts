import { Component, OnInit } from '@angular/core';
import { AuditLogService, AuditLogResponse } from '../../core/services/audit-log.service';
import { DialogService } from '../../core/services/dialog.service';
import { formatDateTime, formatRelativeTime } from '../../core/utils/date-time.util';

@Component({
  selector: 'app-login-history',
  standalone: false,
  templateUrl: './login-history.component.html',
  styleUrls: ['./login-history.component.scss']
})
export class LoginHistoryComponent implements OnInit {
  loginLogoutLogs: AuditLogResponse[] = [];
  filteredLogs: AuditLogResponse[] = [];
  isLoading = false;
  searchTerm = '';
  selectedType: string = 'ALL'; // ALL, LOGIN, LOGOUT

  constructor(
    private auditLogService: AuditLogService,
    private dialogService: DialogService
  ) {}

  ngOnInit(): void {
    this.loadLoginLogoutLogs();
  }

  loadLoginLogoutLogs(): void {
    this.isLoading = true;
    this.auditLogService.getLoginLogoutLogs().subscribe({
      next: (logs) => {
        // Limit to top 50 activities (backend should already limit, but adding safety check)
        this.loginLogoutLogs = logs.slice(0, 50);
        this.filteredLogs = this.loginLogoutLogs;
        this.isLoading = false;
      },
      error: (error) => {
        console.error('Error loading login/logout logs:', error);
        this.isLoading = false;
      }
    });
  }

  filterLogs(): void {
    this.filteredLogs = this.loginLogoutLogs.filter(log => {
      const matchesSearch = !this.searchTerm || 
        log.username.toLowerCase().includes(this.searchTerm.toLowerCase()) ||
        log.fullName.toLowerCase().includes(this.searchTerm.toLowerCase());
      
      const matchesType = this.selectedType === 'ALL' || 
        (this.selectedType === 'LOGIN' && log.action === 'USER_LOGIN') ||
        (this.selectedType === 'LOGOUT' && log.action === 'USER_LOGOUT');
      
      return matchesSearch && matchesType;
    });
  }

  getActionType(action: string): string {
    return action === 'USER_LOGIN' ? 'INGRESO' : 'SALIDA';
  }

  getRoleLabel(role: string): string {
    const labels: Record<string, string> = {
      ADMIN: 'Administrador', CASHIER: 'Cajero', STOCK_MONITOR: 'Supervisor de inventario',
      STOCK_KEEPER: 'Encargado de almacén', CUSTOMER_SUPPORT: 'Atención al cliente',
      ANALYST: 'Analista', MANAGER: 'Gerente'
    };
    return labels[role] || role;
  }

  getActionBadgeClass(action: string): string {
    return action === 'USER_LOGIN' ? 'badge-login' : 'badge-logout';
  }

  formatDate(dateString: string): string {
    return formatDateTime(dateString, true);
  }

  getTimeAgo(dateString: string): string {
    return formatRelativeTime(dateString);
  }

  clearLoginHistory(): void {
    this.dialogService.confirm(
      '¿Deseas eliminar todo el historial de accesos? Esta acción no se puede deshacer.',
      'Limpiar historial de accesos'
    ).then((confirmed) => {
      if (confirmed) {
        this.isLoading = true;
        this.auditLogService.deleteLoginLogoutLogs().subscribe({
          next: () => {
            this.loginLogoutLogs = [];
            this.filteredLogs = [];
            this.isLoading = false;
            this.dialogService.success('El historial de accesos se eliminó correctamente.');
          },
          error: (error) => {
            console.error('Error clearing login history:', error);
            this.dialogService.error('No se pudo limpiar el historial. Inténtalo nuevamente.');
            this.isLoading = false;
          }
        });
      }
    });
  }
}
