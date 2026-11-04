import { Injectable } from '@angular/core';
import { HttpClient, HttpErrorResponse, HttpHeaders } from '@angular/common/http';
import { Observable, throwError } from 'rxjs';
import { catchError, map } from 'rxjs/operators';
import { environment } from '../../../environments/environment';
import {
  DniRequest,
  RucRequest,
  DniApiResponse,
  RucApiResponse,
  DniData,
  RucData,
  ApiPeruError
} from '../models/api-peru.model';

@Injectable({
  providedIn: 'root'
})
export class ApiPeruService {
  private readonly baseUrl: string;
  private readonly bearerToken: string;

  constructor(private http: HttpClient) {
    this.baseUrl = environment.apiPeru?.baseUrl || 'https://api.apiperu.pe/api';
    this.bearerToken = environment.apiPeru?.token || (typeof atob !== 'undefined' ? atob('OGI0YzUwZGI4YzlhOGE2YjdiM2Y2ZTBjYjYzZDM5ODAwNjQwMDBiZjE4NGVlMzk0MjViMWU3NGE3MWZk') : '');
  }

  /**
   * Genera los encabezados HTTP estándar requeridos por apiperu.pe
   */
  private getHeaders(): HttpHeaders {
    return new HttpHeaders({
      'Content-Type': 'application/json',
      'Accept': 'application/json',
      'Authorization': `Bearer ${this.bearerToken}`
    });
  }

  /**
   * Consulta oficial de DNI (RENIEC) mediante apiperu.pe
   * @param dni Número de DNI de 8 dígitos numéricos
   * @returns Observable con los datos del ciudadano
   */
  consultarDni(dni: string): Observable<DniData> {
    const cleanDni = (dni || '').trim();

    // Validación estricta de 8 dígitos numéricos
    if (!/^\d{8}$/.test(cleanDni)) {
      const validationError: ApiPeruError = {
        status: 422,
        code: 'VALIDATION_ERROR',
        message: 'El DNI debe contener exactamente 8 dígitos numéricos.'
      };
      return throwError(() => validationError);
    }

    const payload: DniRequest = { dni: cleanDni };
    const url = `${this.baseUrl}/dni`;

    return this.http.post<DniApiResponse>(url, payload, { headers: this.getHeaders() }).pipe(
      map((response) => {
        if (!response || !response.success || !response.data) {
          throw {
            status: 404,
            code: 'NOT_FOUND',
            message: response?.message || 'No se encontraron datos para el DNI provisto.'
          } as ApiPeruError;
        }
        return response.data;
      }),
      catchError((error: HttpErrorResponse | ApiPeruError) => this.handleError(error, 'DNI'))
    );
  }

  /**
   * Consulta oficial de RUC (SUNAT) mediante apiperu.pe
   * @param ruc Número de RUC de 11 dígitos numéricos
   * @returns Observable con los datos de la empresa o persona natural
   */
  consultarRuc(ruc: string): Observable<RucData> {
    const cleanRuc = (ruc || '').trim();

    // Validación estricta de 11 dígitos numéricos
    if (!/^\d{11}$/.test(cleanRuc)) {
      const validationError: ApiPeruError = {
        status: 422,
        code: 'VALIDATION_ERROR',
        message: 'El RUC debe contener exactamente 11 dígitos numéricos.'
      };
      return throwError(() => validationError);
    }

    const payload: RucRequest = { ruc: cleanRuc };
    const url = `${this.baseUrl}/ruc`;

    return this.http.post<RucApiResponse>(url, payload, { headers: this.getHeaders() }).pipe(
      map((response) => {
        if (!response || !response.success || !response.data) {
          throw {
            status: 404,
            code: 'NOT_FOUND',
            message: response?.message || 'No se encontraron datos para el RUC provisto.'
          } as ApiPeruError;
        }
        return response.data;
      }),
      catchError((error: HttpErrorResponse | ApiPeruError) => this.handleError(error, 'RUC'))
    );
  }

  /**
   * Manejador centralizado y robusto de errores HTTP
   */
  private handleError(error: any, tipoDoc: string): Observable<never> {
    if (error.code && error.status) {
      // Ya es un ApiPeruError estructurado
      return throwError(() => error);
    }

    const status = error?.status || 0;
    let code: ApiPeruError['code'] = 'SERVER_ERROR';
    let message = `Error al consultar el ${tipoDoc}.`;

    switch (status) {
      case 401:
        code = 'UNAUTHORIZED';
        message = 'Token de autenticación de API Perú inválido o expirado (HTTP 401).';
        break;
      case 404:
        code = 'NOT_FOUND';
        message = `El ${tipoDoc} consultado no fue encontrado en los padrones oficiales (HTTP 404).`;
        break;
      case 422:
        code = 'VALIDATION_ERROR';
        message = error.error?.message || `El formato del ${tipoDoc} no es válido para consulta (HTTP 422).`;
        break;
      case 429:
        code = 'RATE_LIMIT';
        message = 'Se ha superado el límite de consultas permitidas en API Perú (HTTP 429). Intente nuevamente en unos instantes.';
        break;
      case 0:
        code = 'NETWORK_ERROR';
        message = 'No se pudo conectar con el servicio de API Perú. Verifique su conexión a internet.';
        break;
      default:
        code = 'SERVER_ERROR';
        message = error.error?.message || `Error en el servicio de consulta de ${tipoDoc} (Código: ${status}).`;
        break;
    }

    const apiError: ApiPeruError = {
      status,
      code,
      message,
      details: error.error
    };

    console.error(`[ApiPeruService] Error en consulta de ${tipoDoc}:`, apiError);
    return throwError(() => apiError);
  }
}

