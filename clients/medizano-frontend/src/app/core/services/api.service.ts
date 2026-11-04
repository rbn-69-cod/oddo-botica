import { Injectable } from '@angular/core';
import { HttpClient, HttpErrorResponse, HttpHeaders } from '@angular/common/http';
import { Observable, throwError } from 'rxjs';
import { catchError } from 'rxjs/operators';

import { environment } from '../../../environments/environment';

@Injectable({
  providedIn: 'root'
})
export class ApiService {

  private apiUrl = environment.apiUrl || '/api';


  constructor(private http: HttpClient) {}

  private getHeaders(): HttpHeaders {
    return new HttpHeaders({
      'Content-Type': 'application/json'
    });
  }

  get<T>(endpoint: string): Observable<T> {
    return this.http
      .get<T>(`${this.apiUrl}${endpoint}`, { headers: this.getHeaders(), withCredentials: true })
      .pipe(catchError(error => this.handleError(error)));
  }

  post<T>(endpoint: string, body: any): Observable<T> {
    return this.http
      .post<T>(`${this.apiUrl}${endpoint}`, body, { headers: this.getHeaders(), withCredentials: true })
      .pipe(catchError(error => this.handleError(error)));
  }

  put<T>(endpoint: string, body: any): Observable<T> {
    return this.http
      .put<T>(`${this.apiUrl}${endpoint}`, body, { headers: this.getHeaders(), withCredentials: true })
      .pipe(catchError(error => this.handleError(error)));
  }

  patch<T>(endpoint: string, body: any): Observable<T> {
    return this.http
      .patch<T>(`${this.apiUrl}${endpoint}`, body, { headers: this.getHeaders(), withCredentials: true })
      .pipe(catchError(error => this.handleError(error)));
  }

  delete<T>(endpoint: string): Observable<T> {
    return this.http
      .delete<T>(`${this.apiUrl}${endpoint}`, { headers: this.getHeaders(), withCredentials: true })
      .pipe(catchError(error => this.handleError(error)));
  }

  getBlob(endpoint: string): Observable<Blob> {
    return this.http
      .get(`${this.apiUrl}${endpoint}`, {
        headers: this.getHeaders(),
        responseType: 'blob'
      })
      .pipe(catchError(error => this.handleError(error)));
  }

  private handleError(error: HttpErrorResponse): Observable<never> {
    let errorMessage = 'Ocurrió un error inesperado';

    if (error.error instanceof ErrorEvent) {
      errorMessage = `Error: ${error.error.message}`;
    } else {
      if (error.error?.message) {
        errorMessage = this.translateKnownMessage(error.error.message);
      } else if (error.error?.error) {
        errorMessage = this.translateKnownMessage(error.error.error);
        if (error.error.fieldErrors && Array.isArray(error.error.fieldErrors)) {
          const fieldErrors = error.error.fieldErrors
            .map((fe: any) => `${fe.field}: ${this.translateKnownMessage(fe.message)}`)
            .join('\n');
          errorMessage += '\n' + fieldErrors;
        }
      } else {
        switch (error.status) {
          case 0:
            errorMessage = 'No se pudo establecer conexión con el servidor (ERR_CONNECTION_REFUSED / Red). Verifica que los servicios estén activos.';
            break;
          case 400:
            errorMessage = 'Solicitud incorrecta. Revisa los datos enviados.';
            break;
          case 401:
            errorMessage = 'Usuario o contraseña incorrectos o sesión expirada.';
            break;
          case 403:
            errorMessage = 'Acceso denegado: No cuentas con los permisos necesarios para realizar esta acción.';
            break;
          case 404:
            errorMessage = 'El recurso solicitado no fue encontrado en el servidor.';
            break;
          case 405:
            errorMessage = 'La operación solicitada no está permitida para este recurso (Method Not Allowed).';
            break;
          case 500:
            errorMessage = 'Error interno en el servidor. Por favor intenta más tarde.';
            break;
          case 503:
            errorMessage = 'Servicio no disponible: El microservicio correspondiente se encuentra reiniciando o inaccesible.';
            break;
          default:
            errorMessage = `No se pudo completar la solicitud. Código: ${error.status}`;
        }
      }
    }

    return throwError(() => new Error(errorMessage));
  }

  private translateKnownMessage(message: string): string {
    if (!message) {
      return 'Ocurrió un error inesperado';
    }

    const normalized = message.toLowerCase();

    if (normalized.includes('invalid username or password') || normalized.includes('bad credentials') || normalized.includes('no autorizado o token')) {
      return 'Usuario o contraseña incorrectos. Revisa tus credenciales e intenta nuevamente.';
    }

    if (normalized.includes('access denied') || normalized.includes('permission')) {
      return 'No tienes permiso para realizar esta acción.';
    }

    if (normalized.includes('authentication failed')) {
      return 'No se pudo autenticar. Revisa tus credenciales.';
    }

    if (normalized.includes('method not allowed')) {
      return 'La operación solicitada no está permitida para este recurso (Method Not Allowed).';
    }

    if (normalized.includes('barcode is required')) {
      return 'Ingresa o escanea un código válido.';
    }

    if (normalized.includes('barcode prefix is required')) {
      return 'Ingresa al menos un caracter del código.';
    }

    if (normalized.includes('medicine not found with barcode')) {
      return 'No se encontró un producto con este código. Verifica que el código esté registrado.';
    }

    if (normalized.includes('barcode not found or already sold')) {
      return 'No se encontró el código o ya fue vendido.';
    }

    if (normalized.includes('barcode not found')) {
      return 'No se encontró un producto con este código.';
    }

    if (normalized.includes('medicine with barcode') && normalized.includes('has expired')) {
      return 'El producto asociado a este código está vencido.';
    }

    if (normalized.includes('medicine with barcode') && normalized.includes('is out of stock')) {
      return 'El producto asociado a este código no tiene stock disponible.';
    }

    if (normalized.includes('medicine not found with id')) {
      return 'No se encontró el producto solicitado.';
    }

    if (normalized.includes('bill not found')) {
      return 'No se encontró la venta solicitada.';
    }

    if (normalized.includes('quantity is required')) {
      return 'Ingresa la cantidad.';
    }

    if (normalized.includes('quantity must be at least 1')) {
      return 'La cantidad debe ser al menos 1.';
    }

    return message;
  }
}
