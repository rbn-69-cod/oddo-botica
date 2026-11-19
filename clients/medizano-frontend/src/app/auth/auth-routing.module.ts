import { NgModule } from '@angular/core';
import { RouterModule, Routes } from '@angular/router';
import { LoginComponent } from './login/login.component';
import { UnauthorizedComponent } from './unauthorized/unauthorized.component';

const routes: Routes = [
  {
    path: 'iniciar-sesion',
    component: LoginComponent
  },
  {
    path: 'sin-permiso',
    component: UnauthorizedComponent
  },
  {
    path: 'login',
    redirectTo: 'iniciar-sesion',
    pathMatch: 'full'
  },
  {
    path: 'unauthorized',
    redirectTo: 'sin-permiso',
    pathMatch: 'full'
  }
];

@NgModule({
  imports: [RouterModule.forChild(routes)],
  exports: [RouterModule]
})
export class AuthRoutingModule { }
