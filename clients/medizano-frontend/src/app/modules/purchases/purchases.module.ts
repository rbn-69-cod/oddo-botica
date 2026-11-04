import { NgModule } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule, ReactiveFormsModule } from '@angular/forms';
import { PurchasesComponent } from './purchases.component';
import { PurchasesRoutingModule } from './purchases-routing.module';
import { SvgIconComponent } from '../../core/components/svg-icon/svg-icon.component';

@NgModule({
  declarations: [PurchasesComponent],
  imports: [
    CommonModule,
    FormsModule,
    ReactiveFormsModule,
    PurchasesRoutingModule,
    SvgIconComponent
  ]
})
export class PurchasesModule {}

