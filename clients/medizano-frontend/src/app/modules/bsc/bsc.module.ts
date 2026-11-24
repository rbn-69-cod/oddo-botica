import { NgModule } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule, ReactiveFormsModule } from '@angular/forms';
import { SvgIconComponent } from '../../core/components/svg-icon/svg-icon.component';
import { BscComponent } from '../reports/bsc.component';
import { BscRoutingModule } from './bsc-routing.module';

@NgModule({
  declarations: [BscComponent],
  imports: [CommonModule, FormsModule, ReactiveFormsModule, SvgIconComponent, BscRoutingModule]
})
export class BscModule { }
