import { Component, OnInit } from '@angular/core';
import { FormBuilder, FormGroup, Validators } from '@angular/forms';
import { BillingService } from '../../core/services/billing.service';
import { ReturnService } from '../../core/services/return.service';
import { DialogService } from '../../core/services/dialog.service';
import { BillResponse, BillItemResponse } from '../../core/models/billing.model';
import { ReturnRequest, ReturnItemRequest, ReturnResponse } from '../../core/models/return.model';
import { formatDateTime } from '../../core/utils/date-time.util';
import { AuditLogService } from '../../core/services/audit-log.service';

@Component({
  selector: 'app-returns',
  standalone: false,
  templateUrl: './returns.component.html',
  styleUrls: ['./returns.component.scss']
})
export class ReturnsComponent implements OnInit {
  searchForm: FormGroup;
  bill: BillResponse | null = null;
  returnForm: FormGroup;
  selectedItems: { item: BillItemResponse; returnQuantity: number }[] = [];
  processedReturn: ReturnResponse | null = null;
  isLoading = false;
  isProcessing = false;
  showReturnHistory = false;
  returnHistory: ReturnResponse[] = [];
  isLoadingHistory = false;

  constructor(
    private fb: FormBuilder,
    private billingService: BillingService,
    private returnService: ReturnService,
    private dialogService: DialogService,
    private auditLogService: AuditLogService
  ) {
    this.searchForm = this.fb.group({
      billNumber: ['', Validators.required]
    });

    this.returnForm = this.fb.group({
      reason: ['', Validators.required]
    });
  }

  ngOnInit(): void {
    this.loadReturnHistory();
  }

  loadReturnHistory(): void {
    this.isLoadingHistory = true;
    this.returnService.getAllReturns().subscribe({
      next: (returns) => {
        this.returnHistory = returns.sort((a, b) => 
          new Date(b.returnDate).getTime() - new Date(a.returnDate).getTime()
        );
        this.isLoadingHistory = false;
      },
      error: (error) => {
        this.dialogService.error(error.message || 'Error al cargar el historial de devoluciones');
        this.isLoadingHistory = false;
      }
    });
  }

  searchBill(): void {
    if (this.searchForm.invalid) {
      return;
    }

    this.isLoading = true;
    const billNumber = this.searchForm.get('billNumber')?.value;

    this.billingService.getBillByBillNumber(billNumber).subscribe({
      next: (bill) => {
        if (bill.cancelled) {
          this.dialogService.warning('Esta venta fue anulada');
          this.bill = null;
          return;
        }

        if (bill.paymentStatus !== 'PAID') {
          this.dialogService.warning('Solo se pueden procesar devoluciones de ventas pagadas');
          this.bill = null;
          return;
        }

        this.bill = bill;
        this.selectedItems = [];
        this.isLoading = false;
      },
      error: (error) => {
        this.dialogService.error(error.message || 'No se encontró la venta');
        this.bill = null;
        this.isLoading = false;
      }
    });
  }

  toggleItem(item: BillItemResponse): void {
    const index = this.selectedItems.findIndex(si => si.item.id === item.id);
    if (index >= 0) {
      this.selectedItems.splice(index, 1);
    } else {
      this.selectedItems.push({ item, returnQuantity: item.quantity });
    }
  }

  isItemSelected(itemId: number): boolean {
    return this.selectedItems.some(si => si.item.id === itemId);
  }

  updateReturnQuantity(itemId: number, quantity: number): void {
    const selectedItem = this.selectedItems.find(si => si.item.id === itemId);
    if (selectedItem) {
      if (quantity > selectedItem.item.quantity) {
        this.dialogService.warning(`No puedes devolver más que la cantidad original (${selectedItem.item.quantity})`);
        return;
      }
      selectedItem.returnQuantity = quantity;
    }
  }

  getReturnQuantity(itemId: number): number {
    const selectedItem = this.selectedItems.find(si => si.item.id === itemId);
    return selectedItem ? selectedItem.returnQuantity : 0;
  }

  getItemRefund(itemId: number): number {
    const selectedItem = this.selectedItems.find(si => si.item.id === itemId);
    if (!selectedItem) return 0;
    const refundPerUnit = selectedItem.item.totalAmount / selectedItem.item.quantity;
    return refundPerUnit * selectedItem.returnQuantity;
  }

  getTotalRefund(): number {
    return this.selectedItems.reduce((sum, si) => {
      const refundPerUnit = si.item.totalAmount / si.item.quantity;
      return sum + (refundPerUnit * si.returnQuantity);
    }, 0);
  }

  processReturn(): void {
    if (this.returnForm.invalid || !this.bill) {
      return;
    }

    if (this.selectedItems.length === 0) {
      this.dialogService.warning('Selecciona los productos que deseas devolver');
      return;
    }

    this.isProcessing = true;

    const items: ReturnItemRequest[] = this.selectedItems.map(si => ({
      billItemId: si.item.id,
      quantity: si.returnQuantity
    }));

    const request: ReturnRequest = {
      billId: this.bill.id,
      reason: this.returnForm.get('reason')?.value,
      items
    };

    this.returnService.processReturn(request).subscribe({
      next: (returnResponse) => {
        this.auditLogService.recordActivity({
          action: 'REFUND_PROCESSED', entityType: 'RETURN', entityId: String(returnResponse.id || returnResponse.returnNumber),
          description: `Reembolso procesado: ${returnResponse.returnNumber}`
        }).subscribe({ error: () => undefined });
        this.processedReturn = returnResponse;
        this.dialogService.success(`Devolución procesada correctamente. Número: ${returnResponse.returnNumber}`);
        this.loadReturnHistory();
        this.isProcessing = false;
      },
      error: (error) => {
        this.dialogService.error(error.message || 'Error al procesar la devolución');
        this.isProcessing = false;
      }
    });
  }

  resetForm(): void {
    this.bill = null;
    this.selectedItems = [];
    this.processedReturn = null;
    this.searchForm.reset();
    this.returnForm.reset();
  }

  clearProcessedReturn(): void {
    this.processedReturn = null;
    this.resetForm();
  }

  toggleHistoryView(): void {
    this.showReturnHistory = !this.showReturnHistory;
    if (this.showReturnHistory) {
      this.loadReturnHistory();
    }
  }

  formatDate(dateString: string): string {
    return formatDateTime(dateString);
  }

  getTotalRefunded(): number {
    return this.returnHistory.reduce((sum, r) => sum + r.refundAmount, 0);
  }

  trackByItemId(index: number, item: BillItemResponse): any {
    return item.id || index;
  }
}
