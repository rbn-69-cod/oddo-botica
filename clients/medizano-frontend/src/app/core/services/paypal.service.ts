import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, BehaviorSubject, of } from 'rxjs';
import { tap, catchError, map } from 'rxjs/operators';
import { environment } from '../../../environments/environment';
import {
  PayPalConfigResponse,
  PayPalOrderRequest,
  PayPalOrderResponse,
  PayPalCaptureResponse,
  PaymentConfigResponse
} from '../models/billing.model';

declare global {
  interface Window {
    paypal?: any;
  }
}

@Injectable({
  providedIn: 'root'
})
export class PayPalService {
  private apiUrl = `${environment.apiUrl || '/api'}/v1/pagos`;
  private clientIdSubject = new BehaviorSubject<string | null>(null);
  public clientId$ = this.clientIdSubject.asObservable();
  private sdkLoaded = false;

  constructor(private http: HttpClient) {}

  /**
   * Obtiene la configuración pública de PayPal (Client ID y moneda)
   */
  getConfig(): Observable<PayPalConfigResponse> {
    return this.http.get<PaymentConfigResponse>(`${this.apiUrl}/config`).pipe(
      map(config => ({
        clientId: config.payPalClientId || '',
        currency: config.payPalCurrency || 'USD',
        baseUrl: config.payPalBaseUrl || ''
      })),
      tap((config) => {
        if (config?.clientId) {
          this.clientIdSubject.next(config.clientId);
          this.loadPayPalSdk(config.clientId, config.currency || 'USD');
        }
      }),
      catchError((error) => {
        console.warn('No se pudo obtener la configuración de PayPal:', error);
        return of({ clientId: '', currency: 'USD', baseUrl: '' });
      })
    );
  }

  /**
   * Carga dinámicamente el SDK oficial JavaScript de PayPal Sandbox
   */
  public loadPayPalSdk(clientId: string, currency: string = 'USD'): Promise<boolean> {
    return new Promise((resolve) => {
      if (typeof window === 'undefined') {
        resolve(false);
        return;
      }

      if (window.paypal && this.sdkLoaded) {
        resolve(true);
        return;
      }

      const existingScript = document.getElementById('paypal-sdk-script');
      if (existingScript) {
        existingScript.remove();
      }

      const script = document.createElement('script');
      script.id = 'paypal-sdk-script';
      script.src = `https://www.paypal.com/sdk/js?client-id=${encodeURIComponent(clientId)}&currency=${encodeURIComponent(currency)}&intent=capture`;
      script.async = true;

      script.onload = () => {
        this.sdkLoaded = true;
        resolve(true);
      };

      script.onerror = (err) => {
        console.error('Error al cargar PayPal SDK:', err);
        resolve(false);
      };

      document.body.appendChild(script);
    });
  }

  /**
   * Crea una orden en PayPal Sandbox llamando al backend de pago-ms
   */
  crearOrden(request: PayPalOrderRequest): Observable<PayPalOrderResponse> {
    return this.http.post<PayPalOrderResponse>(`${this.apiUrl}/paypal/order`, request);
  }

  /**
   * Captura la orden aprobada llamando al backend de pago-ms
   */
  capturarOrden(paypalOrderId: string): Observable<PayPalCaptureResponse> {
    return this.http.post<PayPalCaptureResponse>(`${this.apiUrl}/paypal/capture/${paypalOrderId}`, {});
  }

  /**
   * Consulta el estado oficial y captura automáticamente cuando PayPal informa
   * que el comprador ya aprobó la orden.
   */
  reconciliarOrden(paypalOrderId: string): Observable<PayPalCaptureResponse> {
    return this.http.post<PayPalCaptureResponse>(
      `${this.apiUrl}/paypal/reconcile/${encodeURIComponent(paypalOrderId)}`, {}
    );
  }
}
