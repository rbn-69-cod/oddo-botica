export interface ReturnItemRequest {
  billItemId: number;
  quantity: number;
}

export interface ReturnRequest {
  billId: number;
  reason: string;
  operationType: 'REFUND' | 'EXCHANGE';
  disposition: 'RESTOCK' | 'QUARANTINE';
  items: ReturnItemRequest[];
}

export interface ReturnItemResponse {
  id: number;
  medicineId: number;
  medicineName: string;
  batchId: number;
  batchNumber: string;
  quantity: number;
  refundAmount: number;
}

export type ReturnType = 'FULL' | 'PARTIAL';

export interface ReturnResponse {
  id: number;
  returnNumber: string;
  billId: number;
  billNumber: string;
  processedById: number;
  processedByName: string;
  returnDate: string;
  refundAmount: number;
  reason: string;
  returnType: ReturnType;
  operationType?: 'REFUND' | 'EXCHANGE';
  disposition?: 'RESTOCK' | 'QUARANTINE';
  createdAt: string;
  items: ReturnItemResponse[];
}





