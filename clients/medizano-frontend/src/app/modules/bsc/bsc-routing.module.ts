import { NgModule } from '@angular/core';
import { RouterModule, Routes } from '@angular/router';
import { BscComponent } from '../reportes/bsc.component';

const routes: Routes = [{ path: '', component: BscComponent }];

@NgModule({
  imports: [RouterModule.forChild(routes)],
  exports: [RouterModule]
})
export class BscRoutingModule { }
