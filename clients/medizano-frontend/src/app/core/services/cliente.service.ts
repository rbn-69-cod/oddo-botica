import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiService } from './api.service';
import { Cliente } from '../models/cliente.model';

@Injectable({
  providedIn: 'root'
})
export class ClienteService {
  constructor(private apiService: ApiService) {}

  listarClientes(todos: boolean = false): Observable<Cliente[]> {
    return this.apiService.get<Cliente[]>(`/v1/clientes?todos=${todos}`);
  }

  obtenerPorId(id: number): Observable<Cliente> {
    return this.apiService.get<Cliente>(`/v1/clientes/${id}`);
  }

  obtenerPorDocumento(documento: string): Observable<Cliente> {
    return this.apiService.get<Cliente>(`/v1/clientes/documento/${documento}`);
  }

  crearCliente(cliente: Partial<Cliente>): Observable<Cliente> {
    return this.apiService.post<Cliente>('/v1/clientes', cliente);
  }

  actualizarCliente(id: number, cliente: Partial<Cliente>): Observable<Cliente> {
    return this.apiService.put<Cliente>(`/v1/clientes/${id}`, cliente);
  }

  eliminarCliente(id: number): Observable<void> {
    return this.apiService.delete<void>(`/v1/clientes/${id}`);
  }
}

