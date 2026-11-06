import { Injectable } from '@angular/core';
import { BehaviorSubject, Observable, of } from 'rxjs';
import { catchError, map, tap } from 'rxjs/operators';
import { ApiService } from './api.service';
import { LoginRequest, AuthResponse, User, UserRole } from '../models/user.model';

@Injectable({
  providedIn: 'root'
})
export class AuthService {
  private readonly TOKEN_KEY = 'auth_token';
  private readonly USER_KEY = 'user_data';
  private currentUserSubject = new BehaviorSubject<User | null>(this.getStoredUser());
  public currentUser$ = this.currentUserSubject.asObservable();

  constructor(private apiService: ApiService) {}

  login(credentials: LoginRequest): Observable<AuthResponse> {
    return this.apiService.post<AuthResponse>('/auth/login', credentials);
  }

  verifyCode(challengeId: string, code: string): Observable<AuthResponse> {
    return this.apiService.post<AuthResponse>('/auth/verify-code', { challengeId, code })
      .pipe(tap(response => {
          if (!response.token || !response.userId || !response.username || !response.role) {
            throw new Error('La verificación no devolvió una sesión válida.');
          }
          this.setToken(response.token);
          const user: User = {
            id: response.userId,
            username: response.username,
            email: response.email || '',
            fullName: response.fullName || response.username,
            role: response.role as UserRole,
            active: true
          };
          this.setUser(user);
          this.currentUserSubject.next(user);
      }));
  }

  resendCode(challengeId: string): Observable<AuthResponse> {
    return this.apiService.post<AuthResponse>('/auth/resend-code', { challengeId });
  }

  getSsoStatus(): Observable<AuthResponse> {
    return this.apiService.get<AuthResponse>('/auth/sso-status');
  }

  restoreSsoSession(): Observable<boolean> {
    return this.getSsoStatus().pipe(
      map(response => {
        if (!response.authenticated || !response.userId || !response.username || !response.role) {
          this.clearStoredSession();
          this.currentUserSubject.next(null);
          return false;
        }
        const user: User = {
          id: response.userId,
          username: response.username,
          email: response.email || '',
          fullName: response.fullName || response.username,
          role: response.role as UserRole,
          active: true
        };
        this.setToken('odoo-session-mfa');
        this.setUser(user);
        this.currentUserSubject.next(user);
        return true;
      }),
      catchError(() => {
        // Odoo owns the real session.  Never keep a stale frontend session
        // when Odoo has logged out, expired or has not completed MFA.
        this.clearStoredSession();
        this.currentUserSubject.next(null);
        return of(false);
      })
    );
  }

  openOdoo(): void {
    window.location.assign('/sso/odoo');
  }

  logout(): void {
    // Call backend to log logout event
    const user = this.getCurrentUser();
    if (user) {
      this.apiService.post('/auth/logout', {}).subscribe({
        next: () => {},
        error: () => {} // Ignore errors - logout should always succeed
      });
    }
    
    sessionStorage.removeItem(this.TOKEN_KEY);
    sessionStorage.removeItem(this.USER_KEY);
    this.currentUserSubject.next(null);
  }

  getToken(): string | null {
    return sessionStorage.getItem(this.TOKEN_KEY);
  }

  isAuthenticated(): boolean {
    const token = this.getToken();
    const user = this.getCurrentUser();

    if (!token || !user || !this.isStoredSessionValid(token, user)) {
      this.clearStoredSession();
      this.currentUserSubject.next(null);
      return false;
    }

    return true;
  }

  getCurrentUser(): User | null {
    return this.currentUserSubject.value;
  }

  hasRole(role: UserRole): boolean {
    const user = this.getCurrentUser();
    return user?.role === role || user?.role === UserRole.ADMIN;
  }

  hasAnyRole(roles: UserRole[]): boolean {
    const user = this.getCurrentUser();
    if (!user) return false;
    return roles.includes(user.role) || user.role === UserRole.ADMIN;
  }

  private setToken(token: string): void {
    sessionStorage.setItem(this.TOKEN_KEY, token);
  }

  private setUser(user: User): void {
    sessionStorage.setItem(this.USER_KEY, JSON.stringify(user));
  }

  private getStoredUser(): User | null {
    const userData = sessionStorage.getItem(this.USER_KEY);
    const token = this.getToken();

    if (!userData || !token) {
      this.clearStoredSession();
      return null;
    }

    try {
      const user = JSON.parse(userData) as User;
      if (!this.isStoredSessionValid(token, user)) {
        this.clearStoredSession();
        return null;
      }

      return user;
    } catch {
      this.clearStoredSession();
      return null;
    }
  }

  private isStoredSessionValid(token: string, user: User): boolean {
    if (token === 'odoo-session-mfa') {
      return true;
    }
    const payload = this.decodeJwtPayload(token);
    if (!payload) {
      return false;
    }

    const tokenUsername = typeof payload.sub === 'string' ? payload.sub : '';
    const expiresAt = typeof payload.exp === 'number' ? payload.exp * 1000 : 0;

    return tokenUsername === user.username && expiresAt > Date.now();
  }

  private decodeJwtPayload(token: string): any | null {
    try {
      const payload = token.split('.')[1];
      if (!payload) {
        return null;
      }

      const normalizedPayload = payload.replace(/-/g, '+').replace(/_/g, '/');
      const paddedPayload = normalizedPayload.padEnd(
        normalizedPayload.length + ((4 - normalizedPayload.length % 4) % 4),
        '='
      );

      return JSON.parse(atob(paddedPayload));
    } catch {
      return null;
    }
  }

  private clearStoredSession(): void {
    sessionStorage.removeItem(this.TOKEN_KEY);
    sessionStorage.removeItem(this.USER_KEY);
    localStorage.removeItem(this.TOKEN_KEY);
    localStorage.removeItem(this.USER_KEY);
  }
}
