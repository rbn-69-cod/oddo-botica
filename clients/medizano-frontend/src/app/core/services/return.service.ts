import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiService } from './api.service';
import { ReturnRequest, ReturnResponse } from '../models/return.model';

@Injectable({
  providedIn: 'root'
})
export class ReturnService {
  constructor(private apiService: ApiService) {}

  processReturn(request: ReturnRequest): Observable<ReturnResponse> {
    return this.apiService.post<ReturnResponse>('/cashier/returns', request);
  }

  getAllReturns(): Observable<ReturnResponse[]> {
    return this.apiService.get<ReturnResponse[]>('/cashier/returns');
  }

  getReturnById(id: number): Observable<ReturnResponse> {
    return this.apiService.get<ReturnResponse>(`/cashier/returns/${id}`);
  }

  getReturnsByBillId(billId: number): Observable<ReturnResponse[]> {
    return this.apiService.get<ReturnResponse[]>(`/cashier/returns/bill/${billId}`);
  }
}
