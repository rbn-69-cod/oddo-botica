import { Component } from '@angular/core';
import { Router } from '@angular/router';
import { AuthService } from '../auth.service';

@Component({
  selector: 'app-unauthorized',
  standalone: false,
  templateUrl: './unauthorized.component.html',
  styleUrls: ['./unauthorized.component.scss']
})
export class UnauthorizedComponent {
  constructor(
    private router: Router,
    public authService: AuthService
  ) {}

  goHome(): void {
    const user = this.authService.getCurrentUser();
    if (user) {
      // Redirect to user's default page based on role
      const defaultRoute = this.getDefaultRoute(user.role);
      this.router.navigate([defaultRoute]);
    } else {
      this.router.navigate(['/acceso/iniciar-sesion']);
    }
  }

  private getDefaultRoute(role: string): string {
    switch (role) {
      case 'CASHIER':
        return '/ventas';
      case 'STOCK_MONITOR':
        return '/inventario';
      case 'STOCK_KEEPER':
        return '/medicamentos';
      case 'CUSTOMER_SUPPORT':
        return '/devoluciones';
      case 'ANALYST':
      case 'MANAGER':
        return '/reportes';
      case 'ADMIN':
        return '/ventas';
      default:
        return '/ventas';
    }
  }
}
