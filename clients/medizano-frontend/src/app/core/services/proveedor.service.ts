import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiService } from './api.service';
import { Proveedor, PaginatedProveedores, ProveedorFiltro } from '../models/proveedor.model';

@Injectable({
  providedIn: 'root'
})
export class ProveedorService {

  constructor(private apiService: ApiService) {}

  listarProveedores(params?: ProveedorFiltro): Observable<PaginatedProveedores> {
    let query = '/v1/proveedores/paginado?';
    if (params?.filtro) {
      query += `search=${encodeURIComponent(params.filtro)}&`;
    }
    if (params?.page !== undefined) {
      query += `page=${params.page}&`;
    }
    if (params?.size !== undefined) {
      query += `size=${params.size}&`;
    }
    if (params?.sort) {
      query += `sort=${params.sort}&`;
    }
    return this.apiService.get<PaginatedProveedores>(query);
  }

  obtenerPorId(id: number): Observable<Proveedor> {
    return this.apiService.get<Proveedor>(`/v1/proveedores/${id}`);
  }

  obtenerPorRuc(ruc: string): Observable<Proveedor> {
    return this.apiService.get<Proveedor>(`/v1/proveedores/ruc/${ruc}`);
  }

  crearProveedor(proveedor: Partial<Proveedor>): Observable<Proveedor> {
    return this.apiService.post<Proveedor>('/v1/proveedores', proveedor);
  }

  actualizarProveedor(id: number, proveedor: Partial<Proveedor>): Observable<Proveedor> {
    return this.apiService.put<Proveedor>(`/v1/proveedores/${id}`, proveedor);
  }

  desactivarProveedor(id: number): Observable<any> {
    return this.apiService.delete<any>(`/v1/proveedores/${id}`);
  }
}

