import { NgModule } from '@angular/core';
import { RouterModule, Routes } from '@angular/router';
import { AuthGuard } from './auth/auth.guard';
import { RoleGuard } from './auth/role.guard';
import { UserRole } from './core/models/user.model';

const routes: Routes = [
  {
    path: 'acceso',
    loadChildren: () => import('./auth/auth.module').then(m => m.AuthModule)
  },
  {
    path: 'iniciar-sesion',
    redirectTo: '/acceso/iniciar-sesion',
    pathMatch: 'full'
  },
  {
    path: 'inicio',
    loadChildren: () => import('./modules/dashboard/dashboard.module').then(m => m.DashboardModule),
    canActivate: [AuthGuard]
  },
  {
    path: 'ventas',
    loadChildren: () => import('./modules/billing/billing.module').then(m => m.BillingModule),
    canActivate: [AuthGuard, RoleGuard],
    data: { roles: [UserRole.CASHIER, UserRole.ADMIN] }
  },
  {
    path: 'inventario',
    loadChildren: () => import('./modules/inventory/inventory.module').then(m => m.InventoryModule),
    canActivate: [AuthGuard, RoleGuard],
    data: { roles: [UserRole.STOCK_MONITOR, UserRole.STOCK_KEEPER, UserRole.MANAGER, UserRole.ADMIN] }
  },
  {
    path: 'medicamentos',
    redirectTo: '/inventario',
    pathMatch: 'full'
  },
  {
    path: 'devoluciones',
    loadChildren: () => import('./modules/returns/returns.module').then(m => m.ReturnsModule),
    canActivate: [AuthGuard, RoleGuard],
    data: { roles: [UserRole.CUSTOMER_SUPPORT, UserRole.MANAGER, UserRole.ADMIN] }
  },
  {
    path: 'reportes',
    loadChildren: () => import('./modules/reports/reports.module').then(m => m.ReportsModule),
    canActivate: [AuthGuard, RoleGuard],
    data: { roles: [UserRole.ANALYST, UserRole.MANAGER, UserRole.ADMIN] }
  },
  {
    path: 'proveedores',
    loadChildren: () => import('./modules/suppliers/suppliers.module').then(m => m.SuppliersModule),
    canActivate: [AuthGuard, RoleGuard],
    data: { roles: [UserRole.MANAGER, UserRole.STOCK_MONITOR, UserRole.STOCK_KEEPER, UserRole.ADMIN] }
  },
  {
    path: 'compras',
    loadChildren: () => import('./modules/purchases/purchases.module').then(m => m.PurchasesModule),
    canActivate: [AuthGuard, RoleGuard],
    data: { roles: [UserRole.MANAGER, UserRole.STOCK_MONITOR, UserRole.STOCK_KEEPER, UserRole.ADMIN] }
  },
  {
    path: 'historial-compras',
    loadChildren: () => import('./modules/purchase-history/purchase-history.module').then(m => m.PurchaseHistoryModule),
    canActivate: [AuthGuard, RoleGuard],
    data: { roles: [UserRole.MANAGER, UserRole.ADMIN] }
  },
  {
    path: 'actividad-usuarios',
    loadChildren: () => import('./modules/user-activity/user-activity.module').then(m => m.UserActivityModule),
    canActivate: [AuthGuard, RoleGuard],
    data: { roles: [UserRole.ADMIN] }
  },
  {
    path: 'bsc',
    loadChildren: () => import('./modules/bsc/bsc.module').then(m => m.BscModule),
    canActivate: [AuthGuard, RoleGuard],
    data: { roles: [UserRole.ANALYST, UserRole.MANAGER, UserRole.ADMIN] }
  },
  {
    path: 'historial-accesos',
    loadChildren: () => import('./modules/login-history/login-history.module').then(m => m.LoginHistoryModule),
    canActivate: [AuthGuard, RoleGuard],
    data: { roles: [UserRole.ADMIN] }
  },
  {
    path: 'usuarios',
    loadChildren: () => import('./modules/user-management/user-management.module').then(m => m.UserManagementModule),
    canActivate: [AuthGuard, RoleGuard],
    data: { roles: [UserRole.ADMIN] }
  },
  // Compatibilidad con rutas anteriores en inglés
  { path: 'auth/login', redirectTo: '/acceso/iniciar-sesion', pathMatch: 'full' },
  { path: 'auth/unauthorized', redirectTo: '/acceso/sin-permiso', pathMatch: 'full' },
  { path: 'login', redirectTo: '/acceso/iniciar-sesion', pathMatch: 'full' },
  { path: 'dashboard', redirectTo: '/inicio', pathMatch: 'full' },
  { path: 'billing', redirectTo: '/ventas', pathMatch: 'full' },
  { path: 'inventory', redirectTo: '/inventario', pathMatch: 'full' },
  { path: 'medicines', redirectTo: '/inventario', pathMatch: 'full' },
  { path: 'returns', redirectTo: '/devoluciones', pathMatch: 'full' },
  { path: 'reports', redirectTo: '/reportes', pathMatch: 'full' },
  { path: 'suppliers', redirectTo: '/proveedores', pathMatch: 'full' },
  { path: 'purchases', redirectTo: '/compras', pathMatch: 'full' },
  { path: 'purchases/tracking', redirectTo: '/compras/seguimiento', pathMatch: 'full' },
  { path: 'purchases/scanner', redirectTo: '/compras/escaner', pathMatch: 'full' },
  { path: 'purchase-history', redirectTo: '/historial-compras', pathMatch: 'full' },
  { path: 'user-activity', redirectTo: '/actividad-usuarios', pathMatch: 'full' },
  { path: 'login-history', redirectTo: '/historial-accesos', pathMatch: 'full' },
  { path: 'user-management', redirectTo: '/usuarios', pathMatch: 'full' },
  {
    path: '',
    redirectTo: '/inicio',
    pathMatch: 'full'
  },
  {
    path: '**',
    redirectTo: '/inicio'
  }
];

@NgModule({
  imports: [RouterModule.forRoot(routes, { useHash: true })],
  exports: [RouterModule]
})
export class AppRoutingModule { }
