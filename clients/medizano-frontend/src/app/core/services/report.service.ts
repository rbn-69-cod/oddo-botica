import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { catchError, map } from 'rxjs/operators';
import { ApiService } from './api.service';
import { CashRegisterReportResponse, SalesReportResponse, GstReportResponse, StockReportResponse } from '../models/report.model';

@Injectable({
  providedIn: 'root'
})
export class ReportService {
  constructor(private apiService: ApiService) {}

  getDailySalesReport(startDate: string, endDate: string): Observable<SalesReportResponse> {
    return this.apiService.get<SalesReportResponse>(
      `/admin/reports/sales?startDate=${startDate}&endDate=${endDate}`
    );
  }

  getGstReport(startDate: string, endDate: string): Observable<GstReportResponse> {
    return this.apiService.get<GstReportResponse>(
      `/admin/reports/gst?startDate=${startDate}&endDate=${endDate}`
    );
  }

  getCashRegisterReport(startDate: string, endDate: string): Observable<CashRegisterReportResponse> {
    return this.apiService.get<CashRegisterReportResponse>(
      `/admin/reports/cash-register?startDate=${startDate}&endDate=${endDate}`
    ).pipe(
      catchError(() => this.getDailySalesReport(startDate, endDate).pipe(
        map((report) => this.buildCashRegisterFallback(report))
      ))
    );
  }

  getCashierSalesReport(cashierId: number, startDate: string, endDate: string): Observable<SalesReportResponse> {
    return this.apiService.get<SalesReportResponse>(
      `/admin/reports/cashier/${cashierId}?startDate=${startDate}&endDate=${endDate}`
    );
  }

  getStockReport(): Observable<StockReportResponse> {
    return this.apiService.get<StockReportResponse>('/admin/reports/stock');
  }

  private buildCashRegisterFallback(report: SalesReportResponse): CashRegisterReportResponse {
    const totalCollected = (report.totalCash || 0) + (report.totalUpi || 0) + (report.totalCard || 0);
    const subtotal = Math.max(0, (report.totalSales || 0) - (report.totalGst || 0));

    return {
      startDate: report.startDate,
      endDate: report.endDate,
      totalBills: report.totalBills || 0,
      totalPayments: 0,
      subtotal,
      totalGst: report.totalGst || 0,
      totalSales: report.totalSales || 0,
      totalCash: report.totalCash || 0,
      totalUpi: report.totalUpi || 0,
      totalCard: report.totalCard || 0,
      totalCollected,
      totalRefunds: 0,
      netCollected: totalCollected,
      refundCount: 0,
      roundingAdjustment: 0,
      cashierBreakdown: []
    };
  }
}
