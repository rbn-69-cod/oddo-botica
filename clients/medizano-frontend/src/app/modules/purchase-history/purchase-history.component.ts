import { Component, OnInit } from '@angular/core';
import { BillingService } from '../../core/services/billing.service';
import { DialogService } from '../../core/services/dialog.service';
import { BillResponse } from '../../core/models/billing.model';
import { formatDateTime, parseBackendDate } from '../../core/utils/date-time.util';

@Component({
  selector: 'app-purchase-history',
  standalone: false,
  templateUrl: './purchase-history.component.html',
  styleUrls: ['./purchase-history.component.scss']
})
export class PurchaseHistoryComponent implements OnInit {
  bills: BillResponse[] = [];
  isLoading = false;
  searchTerm = '';

  constructor(
    private billingService: BillingService,
    private dialogService: DialogService
  ) {}

  ngOnInit(): void {
    this.loadPurchaseHistory();
  }

  loadPurchaseHistory(): void {
    this.isLoading = true;
    this.billingService.getAllBills().subscribe({
      next: (bills) => {
        this.bills = bills;
        this.isLoading = false;
      },
      error: (error) => {
        console.error('Error loading purchase history:', error);
        this.dialogService.error('Error al cargar el historial de ventas: ' + (error.message || 'Error desconocido'));
        this.isLoading = false;
      }
    });
  }

  get filteredBills(): BillResponse[] {
    if (!this.searchTerm.trim()) {
      return this.bills;
    }
    const term = this.searchTerm.toLowerCase().trim();
    return this.bills.filter(bill =>
      bill.billNumber.toLowerCase().includes(term) ||
      (bill.customerName && bill.customerName.toLowerCase().includes(term)) ||
      (bill.customerPhone && bill.customerPhone.toLowerCase().includes(term)) ||
      bill.items.some(item => item.medicineName.toLowerCase().includes(term))
    );
  }

  get totalSales(): number {
    return this.filteredBills.reduce((sum, bill) => sum + bill.totalAmount, 0);
  }

  get totalBills(): number {
    return this.filteredBills.length;
  }

  get totalItems(): number {
    return this.filteredBills.reduce((sum, bill) => 
      sum + bill.items.reduce((itemSum, item) => itemSum + item.quantity, 0), 0
    );
  }

  trackByBillId(index: number, bill: BillResponse): any {
    return bill.id || index;
  }

  formatDate(dateString: string): string {
    return parseBackendDate(dateString).toLocaleDateString('es-PE', {
      timeZone: 'America/Lima',
      year: 'numeric',
      month: 'short',
      day: 'numeric'
    });
  }

  formatDateTime(dateString: string): string {
    return formatDateTime(dateString);
  }

  getPaymentStatusClass(status: string): string {
    switch (status) {
      case 'PAID':
        return 'badge-success';
      case 'PENDING':
      case 'PARTIALLY_PAID':
        return 'badge-warning';
      case 'REFUNDED':
        return 'badge-error';
      default:
        return 'badge-warning';
    }
  }

  getPaymentStatusLabel(status: string): string {
    switch (status) {
      case 'PAID':
        return 'Pagado';
      case 'PENDING':
        return 'Pendiente';
      case 'PARTIALLY_PAID':
        return 'Pago parcial';
      case 'REFUNDED':
        return 'Devuelto';
      default:
        return status;
    }
  }

  getTotalPaid(bill: BillResponse): number {
    return bill.payments
      .filter(p => p.status === 'COMPLETED')
      .reduce((sum, payment) => sum + payment.amount, 0);
  }

  getRemainingBalance(bill: BillResponse): number {
    const totalPaid = this.getTotalPaid(bill);
    return bill.totalAmount - totalPaid;
  }

  isOverpaid(bill: BillResponse): boolean {
    return this.getRemainingBalance(bill) < 0;
  }

  getOverpaymentAmount(bill: BillResponse): number {
    const remaining = this.getRemainingBalance(bill);
    return remaining < 0 ? Math.abs(remaining) : 0;
  }

  reprintBillPdf(bill: BillResponse): void {
    if (!bill?.id) {
      this.dialogService.error('No se pudo identificar el comprobante.');
      return;
    }

    this.isLoading = true;
    this.billingService.downloadBillPdf(bill.id).subscribe({
      next: (blob) => {
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `Comprobante_${bill.billNumber}.pdf`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        window.URL.revokeObjectURL(url);
        this.isLoading = false;
      },
      error: (error) => {
        console.error('Error reprinting bill PDF:', error);
        this.dialogService.error('Error al reimprimir PDF: ' + (error.message || 'Error desconocido'));
        this.isLoading = false;
      }
    });
  }
}
