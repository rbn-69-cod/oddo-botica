import { Component, OnInit } from '@angular/core';
import { Router } from '@angular/router';
import { ReportService } from '../../core/services/report.service';
import { InventoryService } from '../../core/services/inventory.service';
import { AuditLogService, AuditLogResponse } from '../../core/services/audit-log.service';
import { AuthService } from '../../core/services/auth.service';
import { UserRole } from '../../core/models/user.model';
import { SalesReportResponse, CashRegisterReportResponse } from '../../core/models/report.model';
import { Medicine } from '../../core/models/medicine.model';
import { Batch } from '../../core/models/batch.model';
import { formatDateTime } from '../../core/utils/date-time.util';
import { forkJoin, of } from 'rxjs';
import { catchError } from 'rxjs/operators';

@Component({
  selector: 'app-dashboard',
  standalone: false,
  templateUrl: './dashboard.component.html',
  styleUrls: ['./dashboard.component.scss']
})
export class DashboardComponent implements OnInit {
  isLoading = true;

  // Real KPIs from backend
  salesReport: SalesReportResponse | null = null;
  cashReport: CashRegisterReportResponse | null = null;
  medicines: Medicine[] = [];
  batches: Batch[] = [];
  totalBatchesCount = 0;
  lowStockBatches: Batch[] = [];
  recentActivities: AuditLogResponse[] = [];

  todayFormatted: string = '';

  constructor(
    public authService: AuthService,
    private router: Router,
    private reportService: ReportService,
    private inventoryService: InventoryService,
    private auditLogService: AuditLogService
  ) {
    const today = new Date();
    this.todayFormatted = today.toLocaleDateString('es-PE', {
      weekday: 'long',
      year: 'numeric',
      month: 'long',
      day: 'numeric'
    });
  }

  ngOnInit(): void {
    this.loadDashboardData();
  }

  get todayIso(): string {
    const now = new Date();
    const year = now.getFullYear();
    const month = String(now.getMonth() + 1).padStart(2, '0');
    const day = String(now.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  }

  loadDashboardData(): void {
    this.isLoading = true;
    const today = this.todayIso;
    const canViewReports = this.authService.hasAnyRole([UserRole.ADMIN, UserRole.ANALYST, UserRole.MANAGER]);
    const canViewMedicines = this.authService.hasAnyRole([UserRole.ADMIN, UserRole.CASHIER, UserRole.STOCK_KEEPER, UserRole.STOCK_MONITOR]);
    const canViewStock = this.authService.hasAnyRole([UserRole.ADMIN, UserRole.CASHIER, UserRole.STOCK_KEEPER, UserRole.STOCK_MONITOR]);
    const canViewAudit = this.authService.hasRole(UserRole.ADMIN);

    forkJoin({
      sales: canViewReports ? this.reportService.getDailySalesReport(today, today).pipe(catchError(() => of(null))) : of(null),
      cash: canViewReports ? this.reportService.getCashRegisterReport(today, today).pipe(catchError(() => of(null))) : of(null),
      medicines: canViewMedicines ? this.inventoryService.getAllMedicines().pipe(catchError(() => of([]))) : of([] as Medicine[]),
      batches: canViewStock ? this.inventoryService.getAllBatches().pipe(catchError(() => of([]))) : of([] as Batch[]),
      lowStock: canViewStock ? this.inventoryService.getLowStockBatches(10).pipe(catchError(() => of([]))) : of([] as Batch[]),
      audit: canViewAudit ? this.auditLogService.getAllAuditLogs().pipe(catchError(() => of([]))) : of([] as AuditLogResponse[])
    }).subscribe({
      next: (res) => {
        this.salesReport = res.sales;
        this.cashReport = res.cash;
        const allBatches = res.batches || [];
        this.batches = allBatches;
        this.totalBatchesCount = allBatches.length;
        
        // Mapear stock real desde los lotes activos a los medicamentos (con Number() explícito)
        const stockMap = new Map<number, number>();
        const stockByName = new Map<string, number>();
        allBatches.forEach(b => {
          const medId = Number(b.medicineId);
          const quantity = Number(b.quantityAvailable) || 0;
          if (medId) stockMap.set(medId, (stockMap.get(medId) || 0) + quantity);
          const batchName = this.normalizeMedicineName(b.medicineName);
          if (batchName) stockByName.set(batchName, (stockByName.get(batchName) || 0) + quantity);
        });

        this.medicines = (res.medicines || []).map(m => {
          const medId = Number(m.id);
          // Catalogo e Inventario pueden tener IDs internos distintos; el nombre
          // del lote permite sincronizar el stock real entre ambos servicios.
          const actualStock = stockMap.has(medId)
            ? stockMap.get(medId)!
            : (stockByName.get(this.normalizeMedicineName(m.name)) || 0);
          return {
            ...m,
            totalStock: actualStock,
            availableStock: actualStock,
            outOfStock: actualStock <= 0,
            lowStock: actualStock > 0 && actualStock <= (m.lowStockThreshold || 10)
          };
        });

        // Las alertas pueden incluir lotes históricos vacíos. El tablero solo
        // debe mostrar los lotes que existen en el inventario físico vigente.
        const activeBatchIds = new Set(allBatches.map(batch => Number(batch.id)));
        this.lowStockBatches = (res.lowStock || []).filter(batch => activeBatchIds.has(Number(batch.id)));
        this.recentActivities = (res.audit || []).slice(0, 5);
        this.isLoading = false;
      },
      error: () => {
        this.isLoading = false;
      }
    });
  }

  get totalSalesToday(): number {
    return this.salesReport?.totalSales || 0;
  }

  get totalBillsToday(): number {
    return this.salesReport?.totalBills || 0;
  }

  get cashInRegisterToday(): number {
    return this.cashReport?.totalCash || 0;
  }

  get activeMedicinesCount(): number {
    return this.medicines.filter(m => m.status === 'ACTIVE').length;
  }

  get catalogProductsCount(): number {
    const fromCatalog = this.activeMedicinesCount;
    if (fromCatalog > 0) return fromCatalog;
    return new Set(this.batches.map(batch => this.normalizeMedicineName(batch.medicineName)).filter(Boolean)).size;
  }

  get refundsToday(): number {
    return this.cashReport?.totalRefunds || 0;
  }

  get netCashToday(): number {
    return this.cashReport?.netCollected ?? this.cashInRegisterToday;
  }

  get expiringSoonBatches(): Batch[] {
    const today = new Date();
    const limit = new Date(today);
    limit.setDate(limit.getDate() + 90);
    return this.batches
      .filter(batch => {
        const expiry = new Date(batch.expiryDate);
        return Number(batch.quantityAvailable) > 0 && !batch.expired && expiry >= today && expiry <= limit;
      })
      .sort((a, b) => new Date(a.expiryDate).getTime() - new Date(b.expiryDate).getTime());
  }

  get healthyStockPercent(): number {
    if (!this.batches.length) return 0;
    const healthy = this.batches.filter(batch => Number(batch.quantityAvailable) > 10 && !batch.expired).length;
    return Math.round((healthy / this.batches.length) * 100);
  }

  get inventoryOverviewBatches(): Batch[] {
    return [...this.batches]
      .filter(batch => Number(batch.quantityAvailable) > 0)
      .sort((a, b) => {
        const dateDifference = new Date(a.expiryDate).getTime() - new Date(b.expiryDate).getTime();
        return dateDifference || a.medicineName.localeCompare(b.medicineName, 'es');
      });
  }

  get inventoryAlertsCount(): number {
    const alertIds = new Set<number>();
    this.lowStockBatches.forEach(batch => alertIds.add(Number(batch.id)));
    this.expiringSoonBatches.forEach(batch => alertIds.add(Number(batch.id)));
    return alertIds.size;
  }

  get inventoryStatusLabel(): string {
    if (this.outOfStockMedicinesCount > 0) return `${this.outOfStockMedicinesCount} sin stock`;
    if (this.inventoryAlertsCount > 0) return `${this.inventoryAlertsCount} por revisar`;
    return 'Inventario al día';
  }

  isExpiringSoon(batch: Batch): boolean {
    return this.expiringSoonBatches.some(item => Number(item.id) === Number(batch.id));
  }

  isLowStock(batch: Batch): boolean {
    return this.lowStockBatches.some(item => Number(item.id) === Number(batch.id));
  }

  daysUntilExpiry(expiryDate: string): number {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const expiry = new Date(`${expiryDate}T00:00:00`);
    return Math.max(0, Math.ceil((expiry.getTime() - today.getTime()) / 86400000));
  }

  get outOfStockMedicinesCount(): number {
    return this.medicines.filter(m => m.outOfStock).length;
  }

  get totalUnitsInStock(): number {
    const catalogTotal = this.medicines.reduce((acc, m) => acc + (m.totalStock || 0), 0);
    if (catalogTotal > 0 || !this.batches.length) return catalogTotal;
    return this.batches.reduce((acc, batch) => acc + (Number(batch.quantityAvailable) || 0), 0);
  }

  get inStockMedicinesCount(): number {
    return this.medicines.filter(m => !m.outOfStock).length;
  }

  formatDate(dateString: string): string {
    return formatDateTime(dateString, true);
  }

  navigate(path: string): void {
    this.router.navigate([path]);
  }

  private normalizeMedicineName(name?: string): string {
    return (name || '')
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .trim()
      .toLowerCase()
      .replace(/\s+/g, ' ');
  }
}
