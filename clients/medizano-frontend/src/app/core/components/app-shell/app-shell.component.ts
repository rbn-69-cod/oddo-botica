import { Component, OnInit } from '@angular/core';
import { Router, NavigationEnd } from '@angular/router';
import { AuthService } from '../../services/auth.service';
import { UserRole } from '../../models/user.model';
import { filter } from 'rxjs/operators';

export interface SubNavItem {
  label: string;
  route: string;
  icon?: string;
  roles: UserRole[];
}

export interface NavItem {
  label: string;
  route: string;
  icon: string;
  roles: UserRole[];
  subItems?: SubNavItem[];
}

@Component({
  selector: 'app-shell',
  standalone: false,
  templateUrl: './app-shell.component.html',
  styleUrls: ['./app-shell.component.scss']
})
export class AppShellComponent implements OnInit {
  readonly UserRole = UserRole;
  
  currentRoute = '';
  sidebarExpanded = false;
  openMenus: { [route: string]: boolean } = {
    '/purchases': true
  };

  navItems: NavItem[] = [
    {
      label: 'Dashboard',
      route: '/dashboard',
      icon: 'reports',
      roles: [UserRole.CASHIER, UserRole.STOCK_MONITOR, UserRole.STOCK_KEEPER, UserRole.CUSTOMER_SUPPORT, UserRole.ANALYST, UserRole.MANAGER, UserRole.ADMIN]
    },
    {
      label: 'Ventas / POS',
      route: '/billing',
      icon: 'billing',
      roles: [UserRole.CASHIER, UserRole.ADMIN]
    },
    {
      label: 'Inventario',
      route: '/inventory',
      icon: 'inventory',
      roles: [UserRole.STOCK_MONITOR, UserRole.STOCK_KEEPER, UserRole.MANAGER, UserRole.ADMIN]
    },
    {
      label: 'Devoluciones',
      route: '/returns',
      icon: 'returns',
      roles: [UserRole.CUSTOMER_SUPPORT, UserRole.MANAGER, UserRole.ADMIN]
    },
    {
      label: 'Proveedores',
      route: '/suppliers',
      icon: 'suppliers',
      roles: [UserRole.MANAGER, UserRole.STOCK_MONITOR, UserRole.STOCK_KEEPER, UserRole.ADMIN]
    },
    {
      label: 'Compras',
      route: '/purchases',
      icon: 'purchases',
      roles: [UserRole.MANAGER, UserRole.STOCK_MONITOR, UserRole.STOCK_KEEPER, UserRole.ADMIN],
      subItems: [
        {
          label: 'Órdenes de Compra',
          route: '/purchases',
          roles: [UserRole.MANAGER, UserRole.STOCK_MONITOR, UserRole.STOCK_KEEPER, UserRole.ADMIN]
        },
        {
          label: 'Estado de Pedidos',
          route: '/purchases/tracking',
          roles: [UserRole.MANAGER, UserRole.STOCK_MONITOR, UserRole.STOCK_KEEPER, UserRole.ADMIN]
        },
        {
          label: 'Escanear Productos',
          route: '/purchases/scanner',
          roles: [UserRole.STOCK_KEEPER, UserRole.STOCK_MONITOR, UserRole.ADMIN]
        }
      ]
    },
    {
      label: 'Facturación',
      route: '/purchase-history',
      icon: 'purchase-history',
      roles: [UserRole.MANAGER, UserRole.ADMIN]
    },
    {
      label: 'Reportes',
      route: '/reports',
      icon: 'reports',
      roles: [UserRole.ANALYST, UserRole.MANAGER, UserRole.ADMIN]
    },
    {
      label: 'Actividad de usuarios',
      route: '/user-activity',
      icon: 'user-activity',
      roles: [UserRole.ADMIN]
    },
    {
      label: 'Historial de accesos',
      route: '/login-history',
      icon: 'login-history',
      roles: [UserRole.ADMIN]
    },
    {
      label: 'Usuarios',
      route: '/user-management',
      icon: 'user-management',
      roles: [UserRole.ADMIN]
    }
  ];

  constructor(
    public authService: AuthService,
    private router: Router
  ) {}

  ngOnInit(): void {
    this.router.events
      .pipe(filter(event => event instanceof NavigationEnd))
      .subscribe((event: any) => {
        this.currentRoute = event.url;
        this.autoOpenParentMenu();
      });
    
    this.currentRoute = this.router.url;
    this.autoOpenParentMenu();
  }

  autoOpenParentMenu(): void {
    if (this.currentRoute.startsWith('/purchases')) {
      this.openMenus['/purchases'] = true;
    }
    
  }

  toggleMenu(route: string): void {
    this.openMenus[route] = !this.openMenus[route];
  }

  isMenuOpen(route: string): boolean {
    return !!this.openMenus[route];
  }

  get visibleNavItems(): NavItem[] {
    return this.navItems.filter(item => 
      this.authService.hasAnyRole(item.roles)
    );
  }

  isActive(route: string): boolean {
    if (route === '/purchases') {
      return this.currentRoute === '/purchases' || this.currentRoute === '/purchases/';
    }
    return this.currentRoute === route || this.currentRoute.startsWith(route + '?');
  }

  isSubItemActive(subRoute: string): boolean {
    if (subRoute === '/purchases') {
      return this.currentRoute === '/purchases' || this.currentRoute === '/purchases/';
    }
    if (subRoute === '/inventory') {
      return this.currentRoute === '/inventory' || this.currentRoute.startsWith('/inventory?');
    }
    if (subRoute === '/medicines') {
      return this.currentRoute.startsWith('/medicines');
    }
    return this.currentRoute.startsWith(subRoute);
  }

  isParentActive(item: NavItem): boolean {
    if (item.subItems) {
      return item.subItems.some(sub => this.isSubItemActive(sub.route));
    }
    return this.isActive(item.route);
  }

  getRoleLabel(role: UserRole | string): string {
    const labels: Record<string, string> = {
      ADMIN: 'Administrador',
      CASHIER: 'Cajero',
      STOCK_MONITOR: 'Supervisor de inventario',
      STOCK_KEEPER: 'Encargado de almacén',
      CUSTOMER_SUPPORT: 'Atención al cliente',
      ANALYST: 'Analista',
      MANAGER: 'Gerente'
    };
    return labels[role] || role;
  }

  logout(): void {
    this.authService.logout();
    this.router.navigate(['/auth/login']);
  }
}
