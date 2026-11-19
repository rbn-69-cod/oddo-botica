import { Component, OnInit } from '@angular/core';
import { FormBuilder, FormGroup, Validators } from '@angular/forms';
import { forkJoin, of } from 'rxjs';
import { catchError, finalize } from 'rxjs/operators';
import { ReportService } from '../../core/services/report.service';
import { DialogService } from '../../core/services/dialog.service';
import {
  CashRegisterReportResponse,
  SalesReportResponse,
  StockReportResponse
} from '../../core/models/report.model';

type ReportView = 'day' | 'totals';

@Component({
  selector: 'app-reports',
  standalone: false,
  templateUrl: './reports.component.html',
  styleUrls: ['./reports.component.scss']
})
export class ReportsComponent implements OnInit {
  activeView: ReportView = 'day';
  isLoading = false;
  lastSyncAt: Date | null = null;

  dayForm: FormGroup;
  totalsForm: FormGroup;

  dailySales: SalesReportResponse | null = null;
  dailyCash: CashRegisterReportResponse | null = null;

  totalSales: SalesReportResponse | null = null;
  stockReport: StockReportResponse | null = null;

  constructor(
    private fb: FormBuilder,
    private reportService: ReportService,
    private dialogService: DialogService
  ) {
    const today = new Date();
    const firstDay = new Date(today.getFullYear(), today.getMonth(), 1);
    const todayStr = this.formatDate(today);

    this.dayForm = this.fb.group({
      date: [todayStr, Validators.required]
    });

    this.totalsForm = this.fb.group({
      startDate: [this.formatDate(firstDay), Validators.required],
      endDate: [todayStr, Validators.required]
    });
  }

  ngOnInit(): void {
    this.loadDayReport();
  }

  formatDate(date: Date): string {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, '0');
    const d = String(date.getDate()).padStart(2, '0');
    return `${y}-${m}-${d}`;
  }

  switchView(view: ReportView): void {
    if (this.activeView === view) return;
    this.activeView = view;
    if (view === 'day' && !this.dailyCash && !this.dailySales) {
      this.loadDayReport();
    } else if (view === 'totals' && !this.totalSales && !this.stockReport) {
      this.loadTotalsReport();
    }
  }

  setDayOffset(offsetDays: number): void {
    const d = new Date();
    d.setDate(d.getDate() + offsetDays);
    this.dayForm.patchValue({ date: this.formatDate(d) });
    this.loadDayReport();
  }

  setTotalsRange(range: 'week' | 'month' | 'year'): void {
    const end = new Date();
    const start = new Date(end);
    if (range === 'week') {
      start.setDate(end.getDate() - 6);
    } else if (range === 'month') {
      start.setDate(1);
    } else {
      start.setMonth(0, 1);
    }
    this.totalsForm.patchValue({
      startDate: this.formatDate(start),
      endDate: this.formatDate(end)
    });
    this.loadTotalsReport();
  }

  loadDayReport(): void {
    if (this.dayForm.invalid || this.isLoading) return;
    const date = this.dayForm.value.date;
    this.isLoading = true;

    forkJoin({
      sales: this.reportService.getDailySalesReport(date, date).pipe(catchError(() => of(null))),
      cash: this.reportService.getCashRegisterReport(date, date).pipe(catchError(() => of(null)))
    })
      .pipe(finalize(() => (this.isLoading = false)))
      .subscribe(({ sales, cash }) => {
        this.dailySales = sales;
        this.dailyCash = cash;
        this.lastSyncAt = new Date();
        if (!sales && !cash) {
          this.dialogService.error('No se pudo cargar el reporte del día.');
        }
      });
  }

  loadTotalsReport(): void {
    if (this.totalsForm.invalid || this.isLoading) return;
    const { startDate, endDate } = this.totalsForm.value;
    if (startDate > endDate) {
      this.dialogService.warning('La fecha inicial no puede ser mayor a la final.');
      return;
    }

    this.isLoading = true;
    forkJoin({
      sales: this.reportService.getDailySalesReport(startDate, endDate).pipe(catchError(() => of(null))),
      stock: this.reportService.getStockReport().pipe(catchError(() => of(null)))
    })
      .pipe(finalize(() => (this.isLoading = false)))
      .subscribe(({ sales, stock }) => {
        this.totalSales = sales;
        this.stockReport = stock;
        this.lastSyncAt = new Date();
        if (!sales && !stock) {
          this.dialogService.error('No se pudieron cargar los reportes totales.');
        }
      });
  }

  get dayDigitalTotal(): number {
    const upi = this.dailyCash?.totalUpi ?? this.dailySales?.totalUpi ?? 0;
    const card = this.dailyCash?.totalCard ?? this.dailySales?.totalCard ?? 0;
    return upi + card;
  }

  get daySalesAmount(): number {
    return this.dailyCash?.netCollected ?? this.dailySales?.totalSales ?? 0;
  }

  get dayBillsCount(): number {
    return this.dailyCash?.totalBills ?? this.dailySales?.totalBills ?? 0;
  }

  get dayCashAmount(): number {
    return this.dailyCash?.totalCash ?? this.dailySales?.totalCash ?? 0;
  }

  get totalsDigitalAmount(): number {
    return (this.totalSales?.totalUpi ?? 0) + (this.totalSales?.totalCard ?? 0);
  }

  trackByDate(index: number, item: any): any {
    return item.date || index;
  }

  trackByCashierId(index: number, item: any): any {
    return item.cashierId || index;
  }
}
