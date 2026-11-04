import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiService } from './api.service';
import { Compra, CompraRequest, RecepcionCompraRequest, PaginatedCompras } from '../models/compra.model';

@Injectable({
  providedIn: 'root'
})
export class CompraService {

  constructor(private apiService: ApiService) {}

  listarCompras(
    page: number = 0, 
    size: number = 20, 
    search?: string, 
    estado?: string, 
    proveedorId?: number,
    sort: string = 'id,desc'
  ): Observable<PaginatedCompras> {
    let url = `/v1/compras?page=${page}&size=${size}&sort=${sort}`;
    if (search && search.trim()) {
      url += `&search=${encodeURIComponent(search.trim())}`;
    }
    if (estado && estado.trim() && estado !== 'TODOS') {
      url += `&estado=${encodeURIComponent(estado.trim())}`;
    }
    if (proveedorId) {
      url += `&proveedorId=${proveedorId}`;
    }
    return this.apiService.get<PaginatedCompras>(url);
  }

  obtenerPorId(id: number): Observable<Compra> {
    return this.apiService.get<Compra>(`/v1/compras/${id}`);
  }

  crearCompra(compra: CompraRequest): Observable<Compra> {
    return this.apiService.post<Compra>('/v1/compras', compra);
  }

  confirmarRecepcion(compraId: number, recepcion: RecepcionCompraRequest): Observable<Compra> {
    return this.apiService.post<Compra>(`/v1/compras/${compraId}/recepcion`, recepcion);
  }

  cancelarCompra(compraId: number, motivo?: string): Observable<Compra> {
    return this.apiService.post<Compra>(`/v1/compras/${compraId}/cancelar`, { motivo });
  }

  actualizarEstado(compraId: number, nuevoEstado: string, observaciones?: string): Observable<Compra> {
    let url = `/v1/compras/${compraId}/estado?nuevoEstado=${nuevoEstado}`;
    if (observaciones) {
      url += `&observaciones=${encodeURIComponent(observaciones)}`;
    }
    return this.apiService.patch<Compra>(url, {});
  }
}

