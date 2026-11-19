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
    '/compras': true,
    '/reportes': true
  };

  navItems: NavItem[] = [
    {
      label: 'Dashboard',
      route: '/inicio',
      icon: 'reports',
      roles: [UserRole.CASHIER, UserRole.STOCK_MONITOR, UserRole.STOCK_KEEPER, UserRole.WAREHOUSE, UserRole.CUSTOMER_SUPPORT, UserRole.ANALYST, UserRole.MANAGER, UserRole.ADMIN]
    },
    {
      label: 'BSC estratégico',
      route: '/bsc',
      icon: 'reports',
      roles: [UserRole.ANALYST, UserRole.MANAGER, UserRole.ADMIN]
    },
    {
      label: 'Ventas / POS',
      route: '/ventas',
      icon: 'billing',
      roles: [UserRole.CASHIER, UserRole.ADMIN]
    },
    {
      label: 'Medicamentos e Inventario',
      route: '/inventario',
      icon: 'inventory',
      roles: [UserRole.STOCK_MONITOR, UserRole.STOCK_KEEPER, UserRole.WAREHOUSE, UserRole.MANAGER, UserRole.ADMIN]
    },
    {
      label: 'Devoluciones',
      route: '/devoluciones',
      icon: 'returns',
      roles: [UserRole.CUSTOMER_SUPPORT, UserRole.MANAGER, UserRole.ADMIN]
    },
    {
      label: 'Proveedores',
      route: '/proveedores',
      icon: 'suppliers',
      roles: [UserRole.MANAGER, UserRole.STOCK_MONITOR, UserRole.STOCK_KEEPER, UserRole.WAREHOUSE, UserRole.ADMIN]
    },
    {
      label: 'Compras',
      route: '/compras',
      icon: 'purchases',
      roles: [UserRole.MANAGER, UserRole.STOCK_MONITOR, UserRole.STOCK_KEEPER, UserRole.ADMIN],
      subItems: [
        {
          label: 'Órdenes de Compra',
          route: '/compras',
          roles: [UserRole.MANAGER, UserRole.STOCK_MONITOR, UserRole.STOCK_KEEPER, UserRole.WAREHOUSE, UserRole.ADMIN]
        },
        {
          label: 'Estado de Pedidos',
          route: '/compras/seguimiento',
          roles: [UserRole.MANAGER, UserRole.STOCK_MONITOR, UserRole.STOCK_KEEPER, UserRole.WAREHOUSE, UserRole.ADMIN]
        },
        {
          label: 'Recepciones completadas',
          route: '/purchases/history',
          roles: [UserRole.MANAGER, UserRole.STOCK_MONITOR, UserRole.STOCK_KEEPER, UserRole.WAREHOUSE, UserRole.ADMIN]
        },
        {
          label: 'Escanear Productos',
          route: '/compras/escaner',
          roles: [UserRole.STOCK_KEEPER, UserRole.STOCK_MONITOR, UserRole.WAREHOUSE, UserRole.ADMIN]
        }
      ]
    },
    {
      label: 'Facturación',
      route: '/historial-compras',
      icon: 'purchase-history',
      roles: [UserRole.MANAGER, UserRole.ADMIN]
    },
    {
      label: 'Reportes',
      route: '/reportes',
      icon: 'reports',
      roles: [UserRole.ANALYST, UserRole.MANAGER, UserRole.ADMIN],
      subItems: [
        {
          label: 'Ventas',
          route: '/reports/ventas',
          roles: [UserRole.ANALYST, UserRole.MANAGER, UserRole.ADMIN]
        },
        {
          label: 'Caja diaria',
          route: '/reports/caja',
          roles: [UserRole.ANALYST, UserRole.MANAGER, UserRole.ADMIN]
        }
      ]
    },
    {
      label: 'Actividad de usuarios',
      route: '/actividad-usuarios',
      icon: 'user-activity',
      roles: [UserRole.ADMIN]
    },
    {
      label: 'Historial de accesos',
      route: '/historial-accesos',
      icon: 'login-history',
      roles: [UserRole.ADMIN]
    },
    {
      label: 'Usuarios',
      route: '/usuarios',
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
    if (this.currentRoute.startsWith('/compras')) {
      this.openMenus['/compras'] = true;
    }
    if (this.currentRoute.startsWith('/reportes')) {
      this.openMenus['/reportes'] = true;
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
    if (route === '/compras') {
      return this.currentRoute === '/compras' || this.currentRoute === '/compras/';
    }
    return this.currentRoute === route || this.currentRoute.startsWith(route + '?');
  }

  isSubItemActive(subRoute: string): boolean {
    if (subRoute === '/compras') {
      return this.currentRoute === '/compras' || this.currentRoute === '/compras/';
    }
    if (subRoute === '/inventario') {
      return this.currentRoute === '/inventario' || this.currentRoute.startsWith('/inventario?');
    }
    if (subRoute === '/medicamentos') {
      return this.currentRoute.startsWith('/medicamentos');
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
    this.router.navigate(['/acceso/iniciar-sesion']);
  }
}
