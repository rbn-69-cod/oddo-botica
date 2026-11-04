import { Component, OnInit } from '@angular/core';
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
export class LoginComponent implements OnInit {
  loginForm: FormGroup;
  errorMessage = '';
  isLoading = false;
  returnUrl = '';
  showPassword = false;

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
    }
  }

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
      next: () => {
        const user = this.authService.getCurrentUser();
        const defaultRoute = user ? this.getDefaultRouteForRole(user.role) : '/billing';
        const targetRoute = this.returnUrl && this.canAccessRoute(this.returnUrl, user?.role)
          ? this.returnUrl 
          : defaultRoute;
        this.router.navigate([targetRoute]);
      },
      error: (error) => {
        this.errorMessage = error?.name === 'TimeoutError'
          ? 'El servidor tardó demasiado en responder. Comprueba tu conexión e intenta nuevamente.'
          : error.message || 'No se pudo iniciar sesión. Revisa tus credenciales.';
      }
    });
  }

  private getDefaultRoute(): string {
    return '/billing'; // Fallback default
  }

  private getDefaultRouteForRole(role: UserRole | string): string {
    switch (role) {
      case UserRole.CASHIER:
        return '/billing';
      case UserRole.STOCK_MONITOR:
        return '/inventory';
      case UserRole.STOCK_KEEPER:
        return '/medicines';
      case UserRole.CUSTOMER_SUPPORT:
        return '/returns';
      case UserRole.ANALYST:
      case UserRole.MANAGER:
        return '/reports';
      case UserRole.ADMIN:
        return '/billing';
      default:
        return '/billing';
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
