import { Component, OnInit } from '@angular/core';
import { FormBuilder, FormGroup, Validators } from '@angular/forms';
import { ReportService } from '../../core/services/report.service';
import { BscIndicator, BscPerspective, BscReportResponse } from '../../core/models/bsc.model';
import { DialogService } from '../../core/services/dialog.service';

interface PerspectiveCard { key: BscPerspective; title: string; eyebrow: string; description: string; icon: string; }

@Component({
  selector: 'app-bsc',
  standalone: false,
  templateUrl: './bsc.component.html',
  styleUrls: ['./bsc.component.scss']
})
export class BscComponent implements OnInit {
  form: FormGroup;
  report: BscReportResponse | null = null;
  isLoading = false;
  activePerspective: BscPerspective | 'all' = 'all';
  readonly perspectives: PerspectiveCard[] = [
    { key: 'financial', eyebrow: '01 · Finanzas', title: 'Rentabilidad', description: 'Ventas, margen y devoluciones.', icon: 'billing' },
    { key: 'customer', eyebrow: '02 · Clientes', title: 'Servicio y recompra', description: 'Clientes identificados y recurrencia.', icon: 'user-activity' },
    { key: 'operations', eyebrow: '03 · Operación', title: 'Inventario y compras', description: 'Stock, lotes, FEFO y abastecimiento.', icon: 'inventory' },
    { key: 'control', eyebrow: '04 · Control', title: 'Equipo y trazabilidad', description: 'Operaciones auditadas en el sistema.', icon: 'reports' }
  ];

  constructor(private fb: FormBuilder, private reports: ReportService, private dialogs: DialogService) {
    const now = new Date();
    const firstDay = new Date(now.getFullYear(), now.getMonth(), 1);
    this.form = this.fb.group({ startDate: [this.iso(firstDay), Validators.required], endDate: [this.iso(now), Validators.required] });
  }

  ngOnInit(): void { this.load(); }
  iso(date: Date): string { return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`; }
  setRange(range: 'today' | 'week' | 'month'): void {
    const end = new Date(); const start = new Date(end);
    if (range === 'week') start.setDate(end.getDate() - 6);
    if (range === 'month') start.setDate(1);
    this.form.patchValue({ startDate: this.iso(start), endDate: this.iso(end) }); this.load();
  }
  load(): void {
    if (this.form.invalid || this.isLoading) return;
    const { startDate, endDate } = this.form.value;
    if (startDate > endDate) { this.dialogs.warning('La fecha inicial no puede ser posterior a la fecha final.'); return; }
    this.isLoading = true;
    this.reports.getBscReport(startDate, endDate).subscribe({
      next: report => { this.report = report; this.isLoading = false; },
      error: error => { this.isLoading = false; this.dialogs.error(error?.message || 'No se pudo leer el BSC desde Odoo.'); }
    });
  }
  selectPerspective(key: BscPerspective | 'all'): void { this.activePerspective = key; }
  indicatorsFor(key: BscPerspective): BscIndicator[] { return (this.report?.indicators || []).filter(item => item.perspective === key); }
  get visibleIndicators(): BscIndicator[] { return this.activePerspective === 'all' ? (this.report?.indicators || []) : this.indicatorsFor(this.activePerspective); }
  get globalScore(): string { const score = this.report?.summary.averageAchievement; return score === null || score === undefined ? '—' : `${Math.min(score, 100).toFixed(0)}%`; }
  displayValue(item: BscIndicator): string {
    if (item.actual === null) return 'Sin datos';
    if (item.unit === 'currency') return `S/ ${item.actual.toLocaleString('es-PE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    if (item.unit === 'percent') return `${item.actual.toFixed(1)}%`;
    return item.actual.toLocaleString('es-PE', { maximumFractionDigits: 0 });
  }
  displayTarget(item: BscIndicator): string {
    if (item.unit === 'currency') return `S/ ${item.target.toLocaleString('es-PE', { minimumFractionDigits: 2 })}`;
    if (item.unit === 'percent') return `${item.target.toFixed(0)}%`;
    return item.target.toLocaleString('es-PE');
  }
  statusText(status: string): string { return ({ on_track: 'En meta', warning: 'Atención', critical: 'Crítico', no_data: 'Sin datos' } as Record<string, string>)[status] || status; }
}
