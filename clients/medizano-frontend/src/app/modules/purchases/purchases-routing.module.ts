import { NgModule } from '@angular/core';
import { RouterModule, Routes } from '@angular/router';
import { PurchasesComponent } from './purchases.component';

const routes: Routes = [
  { path: '', component: PurchasesComponent },
  { path: 'seguimiento', component: PurchasesComponent },
  { path: 'escaner', component: PurchasesComponent },
  { path: 'tracking', redirectTo: 'seguimiento', pathMatch: 'full' },
  { path: 'scanner', redirectTo: 'escaner', pathMatch: 'full' }
];

@NgModule({
  imports: [RouterModule.forChild(routes)],
  exports: [RouterModule]
})
export class PurchasesRoutingModule { }
