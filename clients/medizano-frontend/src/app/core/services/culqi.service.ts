import { Injectable, NgZone } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, BehaviorSubject, of } from 'rxjs';
import { tap, catchError } from 'rxjs/operators';
import { environment } from '../../../environments/environment';
import {
  PaymentConfigResponse,
  CulqiChargeRequest,
  CulqiChargeResponse
} from '../models/billing.model';

declare global {
  interface Window {
    Culqi?: any;
    culqi?: () => void;
  }
}

export interface CulqiCheckoutOptions {
  publicKey: string;
  amountCents: number;
  title?: string;
  description?: string;
  mode?: 'ALL' | 'YAPE';
}

export interface CulqiTokenResult {
  tokenId: string;
  email?: string;
}

@Injectable({
  providedIn: 'root'
})
export class CulqiService {
  private apiUrl = `${environment.apiUrl || '/api'}/v1/pagos`;
  private publicKeySubject = new BehaviorSubject<string | null>(null);
  public publicKey$ = this.publicKeySubject.asObservable();
  private scriptPromise: Promise<void> | null = null;

  constructor(private http: HttpClient, private ngZone: NgZone) {}

  getConfig(): Observable<PaymentConfigResponse> {
    return this.http.get<PaymentConfigResponse>(`${this.apiUrl}/config`).pipe(
      tap((config) => {
        if (config?.culqiPublicKey) {
          this.publicKeySubject.next(config.culqiPublicKey);
        }
      }),
      catchError((error) => {
        console.warn('No se pudo obtener la configuración pública de Culqi:', error);
        return of({ culqiPublicKey: '', culqiCurrency: 'PEN' });
      })
    );
  }

  ensureScriptLoaded(): Promise<void> {
    if (window.Culqi) {
      return Promise.resolve();
    }
    if (this.scriptPromise) {
      return this.scriptPromise;
    }
    this.scriptPromise = new Promise<void>((resolve, reject) => {
      const existing = document.querySelector('script[src*="checkout.culqi.com/js/v4"]') as HTMLScriptElement | null;
      if (existing) {
        if (window.Culqi) {
          resolve();
          return;
        }
        existing.addEventListener('load', () => resolve());
        existing.addEventListener('error', () => reject(new Error('No se pudo cargar Culqi Checkout.')));
        return;
      }
      const script = document.createElement('script');
      script.src = 'https://checkout.culqi.com/js/v4';
      script.async = true;
      script.onload = () => resolve();
      script.onerror = () => reject(new Error('No se pudo cargar Culqi Checkout.'));
      document.head.appendChild(script);
    });
    return this.scriptPromise;
  }

  async openCheckout(
    opts: CulqiCheckoutOptions,
    onToken: (result: CulqiTokenResult) => void,
    onError: (message: string) => void
  ): Promise<void> {
    await this.ensureScriptLoaded();
    if (!window.Culqi) {
      throw new Error('Culqi Checkout no está disponible en este momento.');
    }

    window.Culqi.publicKey = opts.publicKey;
    window.Culqi.settings({
      title: opts.title || 'MediZano Botica',
      currency: 'PEN',
      amount: Math.round(opts.amountCents)
    });
    const isYapeOnly = opts.mode === 'YAPE';
    const paymentMethods = isYapeOnly
      ? {
          yape: true,
          tarjeta: false,
          bancaMovil: false,
          agente: false,
          billetera: false,
          cuotealo: false
        }
      : {
          tarjeta: true,
          yape: true,
          bancaMovil: false,
          agente: false,
          billetera: false,
          cuotealo: false
        };
    window.Culqi.options({
      lang: 'es',
      installments: false,
      paymentMethods,
      paymentMethodsSort: isYapeOnly ? ['yape'] : ['tarjeta', 'yape'],
      style: isYapeOnly
        ? {
            bannerColor: '#742284',
            buttonBackground: '#00d3be',
            menuColor: '#742284',
            linksColor: '#742284',
            buttonText: 'Pagar con Yape',
            buttonTextColor: '#1b0724',
            priceColor: '#742284'
          }
        : {
            bannerColor: '#0f766e',
            buttonBackground: '#763383',
            menuColor: '#0f766e',
            linksColor: '#763383',
            buttonText: 'Pagar ahora',
            buttonTextColor: '#ffffff',
            priceColor: '#0f766e'
          }
    });

    window.culqi = () => {
      this.ngZone.run(() => {
        if (window.Culqi?.token?.id) {
          const tokenId = window.Culqi.token.id;
          const email = window.Culqi.token.email || '';
          try {
            window.Culqi.close();
          } catch {}
          onToken({ tokenId, email });
        } else if (window.Culqi?.error) {
          const err = window.Culqi.error;
          const msg = err.user_message || err.merchant_message || 'No se pudo procesar la tarjeta en Culqi.';
          try {
            window.Culqi.close();
          } catch {}
          onError(msg);
        }
      });
    };

    window.Culqi.open();
  }

  procesarCargo(request: CulqiChargeRequest): Observable<CulqiChargeResponse> {
    return this.http.post<CulqiChargeResponse>(`${this.apiUrl}/culqi/charge`, request);
  }
}
