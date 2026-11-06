import { Component, OnDestroy, OnInit } from '@angular/core';
import { FormBuilder, FormGroup, Validators } from '@angular/forms';
import { Router, ActivatedRoute } from '@angular/router';
import { finalize, timeout } from 'rxjs/operators';
import { AuthService } from '../auth.service';
import { UserRole } from '../../core/models/user.model';

@Component({
  selector: 'app-login',
  standalone: false,
  templateUrl: './login.component.html',
  styleUrls: ['./login.component.scss']
})
export class LoginComponent implements OnInit, OnDestroy {
  loginForm: FormGroup;
  errorMessage = '';
  isLoading = false;
  returnUrl = '';
  showPassword = false;
  verificationStep = false;
  challengeId = '';
  maskedEmail = '';
  code = '';
  attemptsRemaining = 3;
  resendsRemaining = 2;
  expiresIn = 300;
  resendIn = 60;
  private autoSubmitPending = false;
  private timer?: ReturnType<typeof setInterval>;

  constructor(
    private fb: FormBuilder,
    private authService: AuthService,
    private router: Router,
    private route: ActivatedRoute
  ) {
    this.loginForm = this.fb.group({
      username: ['', [Validators.required]],
      password: ['', [Validators.required]]
    });
  }

  ngOnInit(): void {
    this.returnUrl = this.route.snapshot.queryParams['returnUrl'] || this.getDefaultRoute();
    
    if (this.authService.isAuthenticated()) {
      const user = this.authService.getCurrentUser();
      const defaultRoute = user ? this.getDefaultRouteForRole(user.role) : '/billing';
      this.router.navigate([this.returnUrl || defaultRoute]);
      return;
    }

    // Covers an already-open login tab after the user authenticates in Odoo.
    this.authService.restoreSsoSession().subscribe(restored => {
      if (restored) this.router.navigate(['/dashboard']);
    });
  }

  ngOnDestroy(): void { this.stopTimer(); }

  onSubmit(): void {
    if (this.loginForm.invalid) {
      return;
    }

    this.isLoading = true;
    this.errorMessage = '';

    this.authService.login(this.loginForm.value).pipe(
      timeout(15000),
      finalize(() => {
        this.isLoading = false;
      })
    ).subscribe({
      next: (response) => {
        if (!response.mfaRequired || !response.challengeId) {
          this.errorMessage = 'No se pudo iniciar la verificación de seguridad.';
          return;
        }
        this.verificationStep = true;
        this.challengeId = response.challengeId;
        this.maskedEmail = response.maskedEmail || '';
        this.attemptsRemaining = response.attemptsRemaining ?? 3;
        this.resendsRemaining = response.resendsRemaining ?? 2;
        this.expiresIn = response.expiresIn ?? 300;
        this.resendIn = response.resendAfter ?? 60;
        this.code = '';
        this.startTimer();
      },
      error: (error) => {
        this.errorMessage = error?.name === 'TimeoutError'
          ? 'El servidor tardó demasiado en responder. Comprueba tu conexión e intenta nuevamente.'
          : error.message || 'No se pudo iniciar sesión. Revisa tus credenciales.';
      }
    });
  }

  verifyCode(): void {
    const normalized = this.code.replace(/\D/g, '').slice(0, 6);
    if (this.isLoading) return;
    if (normalized.length !== 6) {
      this.errorMessage = 'Ingresa los 6 dígitos del código.';
      return;
    }
    this.isLoading = true;
    this.errorMessage = '';
    this.authService.verifyCode(this.challengeId, normalized).pipe(
      timeout(15000), finalize(() => this.isLoading = false)
    ).subscribe({
      next: () => this.completeLogin(),
      error: (error) => {
        this.attemptsRemaining = Math.max(0, this.attemptsRemaining - 1);
        this.code = '';
        this.errorMessage = error.message || 'El código no es correcto.';
        if (!this.attemptsRemaining) this.cancelVerification();
      }
    });
  }

  resendCode(): void {
    if (this.resendIn > 0 || this.resendsRemaining <= 0 || this.isLoading) return;
    this.isLoading = true;
    this.errorMessage = '';
    this.authService.resendCode(this.challengeId).pipe(
      timeout(15000), finalize(() => this.isLoading = false)
    ).subscribe({
      next: (response) => {
        this.resendsRemaining = response.resendsRemaining ?? Math.max(0, this.resendsRemaining - 1);
        this.attemptsRemaining = response.attemptsRemaining ?? 3;
        this.expiresIn = response.expiresIn ?? 300;
        this.resendIn = response.resendAfter ?? 60;
        this.code = '';
      },
      error: (error) => this.errorMessage = error.message || 'No se pudo reenviar el código.'
    });
  }

  cancelVerification(): void {
    this.stopTimer();
    this.verificationStep = false;
    this.challengeId = '';
    this.code = '';
    this.loginForm.get('password')?.reset('');
  }

  onCodeInput(value: string): void {
    this.code = value.replace(/\D/g, '').slice(0, 6);
    this.errorMessage = '';
    if (this.code.length === 6 && !this.isLoading && !this.autoSubmitPending) {
      this.autoSubmitPending = true;
      setTimeout(() => {
        this.autoSubmitPending = false;
        if (this.code.length === 6 && !this.isLoading) this.verifyCode();
      }, 220);
    }
  }

  digitAt(index: number): string { return this.code[index] || ''; }

  get expiryLabel(): string {
    const minutes = Math.floor(this.expiresIn / 60).toString().padStart(2, '0');
    const seconds = (this.expiresIn % 60).toString().padStart(2, '0');
    return `${minutes}:${seconds}`;
  }

  private startTimer(): void {
    this.stopTimer();
    this.timer = setInterval(() => {
      if (this.expiresIn > 0) this.expiresIn--;
      if (this.resendIn > 0) this.resendIn--;
      if (this.expiresIn === 0) {
        this.errorMessage = 'El código venció. Vuelve a iniciar sesión.';
        this.stopTimer();
      }
    }, 1000);
  }

  private stopTimer(): void {
    if (this.timer) clearInterval(this.timer);
    this.timer = undefined;
  }

  private completeLogin(): void {
    this.stopTimer();
    const user = this.authService.getCurrentUser();
    const defaultRoute = user ? this.getDefaultRouteForRole(user.role) : '/billing';
    const targetRoute = this.returnUrl && this.canAccessRoute(this.returnUrl, user?.role)
      ? this.returnUrl : defaultRoute;
    this.router.navigate([targetRoute]);
  }

  private getDefaultRoute(): string {
    return '/dashboard';
  }

  private getDefaultRouteForRole(role: UserRole | string): string {
    switch (role) {
      case UserRole.CASHIER:
        return '/billing';
      case UserRole.STOCK_MONITOR:
        return '/inventory';
      case UserRole.STOCK_KEEPER:
        return '/medicines';
      case UserRole.WAREHOUSE:
        return '/purchases';
      case UserRole.CUSTOMER_SUPPORT:
        return '/returns';
      case UserRole.ANALYST:
      case UserRole.MANAGER:
        return '/reports';
      case UserRole.ADMIN:
        return '/dashboard';
      default:
        return '/dashboard';
    }
  }

  private canAccessRoute(route: string, role?: UserRole | string): boolean {
    if (!role || !route || route.startsWith('/auth')) {
      return false;
    }

    if (role === UserRole.ADMIN) {
      return true;
    }

    const cleanRoute = route.split('?')[0].split('#')[0];
    const roleRoutes: Record<string, string[]> = {
      [UserRole.CASHIER]: ['/billing'],
      [UserRole.STOCK_MONITOR]: ['/inventory'],
      [UserRole.STOCK_KEEPER]: ['/medicines'],
      [UserRole.WAREHOUSE]: ['/purchases', '/suppliers'],
      [UserRole.CUSTOMER_SUPPORT]: ['/returns'],
      [UserRole.ANALYST]: ['/reports'],
      [UserRole.MANAGER]: ['/reports', '/purchase-history']
    };

    return (roleRoutes[role] || []).some(allowedRoute => cleanRoute.startsWith(allowedRoute));
  }

  get username() {
    return this.loginForm.get('username');
  }

  get password() {
    return this.loginForm.get('password');
  }

  togglePasswordVisibility(): void {
    this.showPassword = !this.showPassword;
  }
}
