import { Component, OnInit } from '@angular/core';
import { FormBuilder, FormGroup, Validators } from '@angular/forms';
import { ActivatedRoute } from '@angular/router';
import { forkJoin, of } from 'rxjs';
import { catchError, finalize } from 'rxjs/operators';
import { ReportService } from '../../core/services/report.service';
import { DialogService } from '../../core/services/dialog.service';
import { CashRegisterReportResponse, SalesReportResponse, GstReportResponse, StockReportResponse } from '../../core/models/report.model';

type ReportTab = 'sales' | 'cash' | 'gst' | 'stock';

@Component({
  selector: 'app-reports',
  standalone: false,
  templateUrl: './reports.component.html',
  styleUrls: ['./reports.component.scss']
})
export class ReportsComponent implements OnInit {
  reportForm: FormGroup;
  salesReport: SalesReportResponse | null = null;
  cashRegisterReport: CashRegisterReportResponse | null = null;
  gstReport: GstReportResponse | null = null;
  stockReport: StockReportResponse | null = null;
  isLoading = false;
  activeTab: ReportTab = 'sales';
  lastSyncAt: Date | null = null;

  constructor(
    private fb: FormBuilder,
    private reportService: ReportService,
    private dialogService: DialogService,
    private route: ActivatedRoute
  ) {
    const today = new Date();
    const firstDay = new Date(today.getFullYear(), today.getMonth(), 1);
    
    this.reportForm = this.fb.group({
      startDate: [this.formatDate(firstDay), Validators.required],
      endDate: [this.formatDate(today), Validators.required]
    });
  }

  loadCashRegisterReport(): void {
    if (this.reportForm.invalid) {
      return;
    }

    this.isLoading = true;
    const { startDate, endDate } = this.reportForm.value;

    this.reportService.getCashRegisterReport(startDate, endDate).subscribe({
      next: (report) => {
        this.cashRegisterReport = report;
        this.isLoading = false;
      },
      error: (error) => {
        console.error('Error loading cash register report:', error);
        this.dialogService.error('Error al cargar la caja diaria: ' + (error.message || 'Error desconocido'));
        this.isLoading = false;
      }
    });
  }

  ngOnInit(): void {
    this.route.data.subscribe(data => {
      this.activeTab = data['tab'] === 'cash' ? 'cash' : 'sales';
      if (this.activeTab === 'cash') {
        const today = this.formatDate(new Date());
        this.reportForm.patchValue({ startDate: today, endDate: today });
      }
      this.syncAllReports();
    });
  }

  formatDate(date: Date): string {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  }

  setQuickRange(range: 'today' | 'week' | 'month'): void {
    const end = new Date();
    const start = new Date(end);
    if (range === 'week') {
      start.setDate(end.getDate() - 6);
    } else if (range === 'month') {
      start.setDate(1);
    }
    this.reportForm.patchValue({
      startDate: this.formatDate(start),
      endDate: this.formatDate(end)
    });
    this.syncAllReports();
  }

  setCashDate(offsetDays = 0): void {
    const date = new Date();
    date.setDate(date.getDate() + offsetDays);
    const value = this.formatDate(date);
    this.reportForm.patchValue({ startDate: value, endDate: value });
    this.syncAllReports();
  }

  onCashDateChange(): void {
    const date = this.reportForm.get('startDate')?.value;
    if (!date) return;
    this.reportForm.patchValue({ endDate: date }, { emitEvent: false });
  }

  syncAllReports(): void {
    if (this.reportForm.invalid || this.isLoading) return;
    const { startDate, endDate } = this.reportForm.value;
    if (startDate > endDate) {
      this.dialogService.warning('La fecha inicial no puede ser posterior a la fecha final.');
      return;
    }

    this.isLoading = true;
    forkJoin({
      sales: this.reportService.getDailySalesReport(startDate, endDate).pipe(catchError(error => {
        console.error('Error sincronizando ventas:', error);
        return of(null);
      })),
      cash: this.reportService.getCashRegisterReport(startDate, endDate).pipe(catchError(error => {
        console.error('Error sincronizando caja:', error);
        return of(null);
      }))
    }).pipe(finalize(() => this.isLoading = false)).subscribe(result => {
      if (result.sales) this.salesReport = result.sales;
      if (result.cash) this.cashRegisterReport = result.cash;
      this.lastSyncAt = new Date();

      if (!result.sales && !result.cash) {
        this.dialogService.error('No se pudo sincronizar la información con Odoo. Intenta nuevamente.');
      }
    });
  }

  get activeReportTitle(): string {
    return ({ sales: 'Ventas', cash: 'Caja diaria', gst: 'Impuestos', stock: 'Inventario' } as Record<ReportTab, string>)[this.activeTab];
  }

  get activeReportHint(): string {
    return ({
      sales: 'Rendimiento comercial y comprobantes emitidos',
      cash: 'Ingresos por método de pago y responsable',
      gst: 'Base imponible e IGV del periodo',
      stock: 'Existencias, valorización y alertas de inventario'
    } as Record<ReportTab, string>)[this.activeTab];
  }

  loadSalesReport(): void {
    if (this.reportForm.invalid) {
      return;
    }

    this.isLoading = true;
    const { startDate, endDate } = this.reportForm.value;

    this.reportService.getDailySalesReport(startDate, endDate).subscribe({
      next: (report) => {
        this.salesReport = report;
        this.isLoading = false;
      },
      error: (error) => {
        console.error('Error loading sales report:', error);
        this.dialogService.error('Error al cargar el reporte de ventas: ' + (error.message || 'Error desconocido'));
        this.isLoading = false;
      }
    });
  }

  loadActiveReport(): void {
    this.syncAllReports();
  }

  loadGstReport(): void {
    if (this.reportForm.invalid) {
      return;
    }

    this.isLoading = true;
    const { startDate, endDate } = this.reportForm.value;

    this.reportService.getGstReport(startDate, endDate).subscribe({
      next: (report) => {
        this.gstReport = report;
        this.isLoading = false;
      },
      error: (error) => {
        console.error('Error loading GST report:', error);
        this.dialogService.error('Error al cargar el reporte de IGV: ' + (error.message || 'Error desconocido'));
        this.isLoading = false;
      }
    });
  }

  loadStockReport(): void {
    this.isLoading = true;
    this.reportService.getStockReport().subscribe({
      next: (report) => {
        this.stockReport = report;
        this.isLoading = false;
      },
      error: (error) => {
        console.error('Error loading stock report:', error);
        this.dialogService.error('Error al cargar el reporte de inventario: ' + (error.message || 'Error desconocido'));
        this.isLoading = false;
      }
    });
  }

  onTabChange(tab: ReportTab): void {
    this.activeTab = tab;
  }

  trackByDate(index: number, daily: any): any {
    return daily.date || index;
  }

  trackByCashierId(index: number, item: any): any {
    return item.cashierId || index;
  }

  trackByHsn(index: number, item: any): any {
    return item.hsnCode || index;
  }

  trackByMedicineId(index: number, item: any): any {
    return item.medicineId || index;
  }

  trackByBatchId(index: number, item: any): any {
    return item.batchId || index;
  }
}
