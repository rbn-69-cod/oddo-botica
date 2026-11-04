export interface BillItemRequest {
  medicineId?: number;
  barcode?: string;
  quantity: number;
  unitPrice?: number;
  batchId?: number;
  batchNumber?: string;
}

export interface PaymentRequest {
  mode: PaymentMode;
  amount: number;
  paymentReference?: string;
}

export enum PaymentMode {
  CASH = 'CASH',
  PAYPAL = 'PAYPAL',
  MERCADO_PAGO = 'MERCADO_PAGO'
}


export interface CreateBillRequest {
  items: BillItemRequest[];
  customerName?: string;
  customerPhone?: string;
  customerEmail?: string;
  payments?: PaymentRequest[];
}

export interface BillItemResponse {
  id: number;
  medicineId: number;
  medicineName: string;
  batchId?: number;
  batchNumber: string;
  quantity: number;
  unitPrice: number;
  gstPercentage: number;
  gstAmount: number;
  totalAmount: number;
}

export interface PaymentResponse {
  id: number;
  paymentReference: string;
  mode: PaymentMode;
  amount: number;
  status: PaymentStatus;
  paymentDate: string;
}

export enum PaymentStatus {
  PENDING = 'PENDING',
  COMPLETED = 'COMPLETED',
  APPROVED = 'APPROVED',
  FAILED = 'FAILED',
  REFUNDED = 'REFUNDED'
}

export interface BillResponse {
  id: number;
  billNumber: string;
  billDate: string;
  cashierId: number;
  cashierName: string;
  customerName?: string;
  customerPhone?: string;
  customerEmail?: string;
  subtotal: number;
  totalGst: number;
  totalAmount: number;
  paymentStatus: BillPaymentStatus;
  cancelled: boolean;
  cancellationReason?: string;
  items: BillItemResponse[];
  payments: PaymentResponse[];
  createdAt: string;
}

export enum BillPaymentStatus {
  PENDING = 'PENDING',
  PAID = 'PAID',
  PARTIALLY_PAID = 'PARTIALLY_PAID',
  REFUNDED = 'REFUNDED'
}

// Unified Payment Gateways Config
export interface PaymentConfigResponse {
  payPalClientId?: string;
  payPalCurrency?: string;
  payPalBaseUrl?: string;
  mpPublicKey?: string;
  mpCurrency?: string;
}

// PayPal Sandbox interfaces
export interface PayPalConfigResponse {
  clientId: string;
  currency: string;
  baseUrl: string;
}

export interface PayPalOrderRequest {
  ordenId: number;
  returnUrl?: string;
  cancelUrl?: string;
}

export interface PayPalOrderResponse {
  ordenId: number;
  numeroOrden: string;
  paypalOrderId: string;
  status: string;
  approveUrl: string;
  amountPen: number;
  amountUsd: number;
  currency: string;
  clientId: string;
}

export interface PayPalCaptureResponse {
  pagoId: number;
  ordenId: number;
  numeroOrden: string;
  paypalOrderId: string;
  paypalCaptureId: string;
  status: string;
  amount: number;
  currency: string;
  timestamp: string;
  orderConfirmed?: boolean;
}

// Mercado Pago interfaces
export interface MercadoPagoPreferenceRequest {
  ordenId: number;
  customerEmail?: string;
  backUrl?: string;
}

export interface MercadoPagoPreferenceResponse {
  ordenId: number;
  numeroOrden: string;
  preferenceId: string;
  initPoint: string;
  sandboxInitPoint: string;
  amountPen: number;
  currency: string;
  publicKey?: string;
}

export interface MercadoPagoVerifyRequest {
  ordenId: number;
  paymentId: string;
  preferenceId?: string;
}

export interface MercadoPagoPaymentResponse {
  pagoId: number;
  ordenId: number;
  numeroOrden: string;
  paymentId: string;
  preferenceId?: string;
  status: string;
  statusDetail?: string;
  amount: number;
  currency: string;
  timestamp: string;
  orderConfirmed?: boolean;
}

export interface PaymentStatusRecord {
  id: number;
  ordenId: number;
  numeroOrden: string;
  amount: number;
  currency: string;
  status: string;
  provider: string;
  externalStatus?: string;
  orderConfirmed?: boolean;
  paymentDate?: string;
  createdAt?: string;
}

export interface EmailReceiptItemDTO {
  name: string;
  quantity: number;
  unitPrice: number;
  total: number;
}

export interface EmailReceiptRequest {
  to: string;
  seriesNumber: string;
  customerName?: string;
  customerDoc?: string;
  cashier?: string;
  paymentMode?: string;
  date?: string;
  subtotal: number;
  igv: number;
  total: number;
  items: EmailReceiptItemDTO[];
}

export interface EmailReceiptResponse {
  success: boolean;
  recipient: string;
  seriesNumber: string;
  message: string;
  timestamp: string;
}
