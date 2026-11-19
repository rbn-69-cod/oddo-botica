import { NgModule } from '@angular/core';
import { RouterModule, Routes } from '@angular/router';
import { ReportsComponent } from './reports.component';

const routes: Routes = [
  {
    path: 'ventas',
    component: ReportsComponent,
    data: { tab: 'sales' }
  },
  {
    path: 'caja',
    component: ReportsComponent,
    data: { tab: 'cash' }
  },
  { path: '', pathMatch: 'full', redirectTo: 'ventas' }
];

@NgModule({
  imports: [RouterModule.forChild(routes)],
  exports: [RouterModule]
})
export class ReportsRoutingModule { }








