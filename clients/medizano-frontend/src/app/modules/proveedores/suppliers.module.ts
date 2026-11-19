import { NgModule } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule, ReactiveFormsModule } from '@angular/forms';
import { SuppliersComponent } from './suppliers.component';
import { SuppliersRoutingModule } from './suppliers-routing.module';
import { SvgIconComponent } from '../../core/components/svg-icon/svg-icon.component';

@NgModule({
  declarations: [SuppliersComponent],
  imports: [
    CommonModule,
    FormsModule,
    ReactiveFormsModule,
    SuppliersRoutingModule,
    SvgIconComponent
  ]
})
export class SuppliersModule {}

