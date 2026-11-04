import { Component, OnInit } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { FormBuilder, FormGroup, Validators } from '@angular/forms';
import { InventoryService } from '../../core/services/inventory.service';
import { DialogService } from '../../core/services/dialog.service';
import { Batch, UpdateBatchRequest, UpdateStockRequest } from '../../core/models/batch.model';
import { Medicine, CreateMedicineRequest } from '../../core/models/medicine.model';
import { forkJoin, of } from 'rxjs';
import { catchError } from 'rxjs/operators';
import { AuditLogService } from '../../core/services/audit-log.service';

export interface EnrichedBatch extends Batch {
  hasRealBatch?: boolean;
  estado?: string;
  manufacturer?: string;
  category?: string;
  barcode?: string;
  prescriptionRequired?: boolean;
  daysUntilExpiry: number;
  fefoStatus: 'OPTIMO' | 'ALERTA_CANJE' | 'RETIRAR' | 'VENCIDO';
  fefoLabel: string;
  fefoBadgeClass: string;
}

@Component({
  selector: 'app-inventory',
  standalone: false,
  templateUrl: './inventory.component.html',
  styleUrls: ['./inventory.component.scss']
})
export class InventoryComponent implements OnInit {
  batches: EnrichedBatch[] = [];
  allBatches: EnrichedBatch[] = [];
  medicinesMap: Map<number, Medicine> = new Map();
  medicinesList: Medicine[] = [];
  
  isLoading = false;
  searchTerm = '';
  filtroTipo = 'TODOS'; 
  // 'TODOS' | 'DISPONIBLE' | 'BAJO_STOCK' | 'ALERTA_CANJE' | 'RETIRAR' | 'VENCIDO' | 'CON_RECETA' | 'VENTA_LIBRE'

  // Modales
  showStockModal = false;
  showBatchModal = false;
  showAddMedicineModal = false;
  showKardexModal = false;
  kardexList: any[] = [];
  loadingKardex = false;
  editingBatch: Batch | null = null;
  stockForm: FormGroup;
  batchForm: FormGroup;
  newMedicineForm: FormGroup;

  readonly laboratoriosPeruanos: string[] = [
    'Laboratorios Bagó del Perú S.A.',
    'Laboratorios Portugal S.R.L.',
    'Medifarma S.A.',
    'Laboratorios AC Farma S.A.',
    'Genfar Perú S.A.',
    'Roemmers S.A.',
    'Laboratorios Hersil S.A.C.',
    'Laboratorios Lansier S.A.C.',
    'Química Suiza S.A.C.',
    'Laboratorios Terbol Perú'
  ];

  constructor(
    private inventoryService: InventoryService,
    private fb: FormBuilder,
    private dialogService: DialogService,
    private route: ActivatedRoute,
    private auditLogService: AuditLogService
  ) {
    this.stockForm = this.fb.group({
      quantityAvailable: [0, [Validators.required, Validators.min(0)]],
      motivo: ['Ajuste fisico verificado', [Validators.required]]
    });

    this.batchForm = this.fb.group({
      batchNumber: ['', Validators.required],
      expiryDate: ['', Validators.required],
      purchasePrice: [0, [Validators.required, Validators.min(0)]],
      sellingPrice: [0, [Validators.required, Validators.min(0)]],
      quantityAvailable: [0, [Validators.required, Validators.min(0)]],
      motivo: ['Ajuste fisico verificado', [Validators.required]]
    });

    this.newMedicineForm = this.fb.group({
      name: ['', [Validators.required]],
      manufacturer: ['Laboratorios Bagó del Perú S.A.', [Validators.required]],
      category: ['Medicamento General'],
      prescriptionRequired: [false],
      barcode: [''],
      hasInitialStock: [true],
      initialStock: [100, [Validators.min(0)]],
      batchNumber: ['LOT-' + new Date().getFullYear() + '-' + Math.floor(100 + Math.random() * 900)],
      expiryDate: [new Date(Date.now() + 365*24*60*60*1000*2).toISOString().split('T')[0]],
      purchasePrice: [2.50, [Validators.min(0)]],
      sellingPrice: [5.00, [Validators.min(0)]]
    });
  }

  ngOnInit(): void {
    this.route.queryParams.subscribe(params => {
      if (params['search']) {
        this.searchTerm = params['search'];
      }
      this.refreshAll();
    });
  }

  refreshAll(): void {
    this.isLoading = true;
    forkJoin({
      batches: this.inventoryService.getAllBatches().pipe(catchError(() => of([]))),
      medicines: this.inventoryService.getAllMedicines().pipe(catchError(() => of([])))
    }).subscribe({
      next: (res) => {
        this.medicinesList = res.medicines || [];
        this.medicinesMap.clear();
        this.medicinesList.forEach(m => {
          if (m.id) this.medicinesMap.set(m.id, m);
        });

        // 1. Enriquecer lotes físicos existentes
        const physicalBatches = (res.batches || []).map(b => {
          const enriched = this.enrichBatch(b);
          enriched.hasRealBatch = true;
          return enriched;
        });

        // Mostrar solo lotes fisicos realmente registrados en inventario
        this.allBatches = physicalBatches;
        this.aplicarFiltro();
        this.isLoading = false;
      },
      error: () => {
        this.isLoading = false;
      }
    });
  }

  private enrichBatch(b: Batch): EnrichedBatch {
    // Buscar medicina correspondiente por ID o por coincidencia de nombre
    let med = this.medicinesMap.get(b.medicineId);
    if (!med && b.medicineName) {
      med = this.medicinesList.find(m => 
        m.name && b.medicineName && (
          m.name.toLowerCase().includes(b.medicineName.toLowerCase()) ||
          b.medicineName.toLowerCase().includes(m.name.toLowerCase())
        )
      );
    }

    const expTime = new Date(b.expiryDate).getTime();
    const nowTime = new Date().getTime();
    const diffDays = Math.ceil((expTime - nowTime) / (1000 * 3600 * 24));

    let fefoStatus: 'OPTIMO' | 'ALERTA_CANJE' | 'RETIRAR' | 'VENCIDO' = 'OPTIMO';
    let fefoLabel = 'Vigente (' + diffDays + ' días)';
    let fefoBadgeClass = 'badge-success';

    if (diffDays <= 0 || b.expired) {
      fefoStatus = 'VENCIDO';
      fefoLabel = 'Vencido (' + Math.abs(diffDays) + 'd)';
      fefoBadgeClass = 'badge-danger-glow';
    } else if (diffDays <= 25) {
      fefoStatus = 'RETIRAR';
      fefoLabel = 'Retirar Mostrador (' + diffDays + 'd)';
      fefoBadgeClass = 'badge-warning-dark';
    } else if (diffDays <= 30) {
      fefoStatus = 'ALERTA_CANJE';
      fefoLabel = 'Alerta Canje (' + diffDays + 'd)';
      fefoBadgeClass = 'badge-warning-glow';
    }

    return {
      ...b,
      manufacturer: med?.manufacturer || this.deducirFabricante(b.medicineName),
      category: med?.category || 'Farmacia',
      barcode: med?.barcode || ('775' + String(100000000 + b.medicineId).slice(-9)),
      prescriptionRequired: med ? med.prescriptionRequired : false,
      daysUntilExpiry: diffDays,
      fefoStatus,
      fefoLabel,
      fefoBadgeClass
    };
  }

  private deducirFabricante(nombre?: string): string {
    if (!nombre) return 'Laboratorio Farmacéutico';
    const n = nombre.toLowerCase();
    if (n.includes('bagó') || n.includes('bago')) return 'Laboratorios Bagó';
    if (n.includes('portugal')) return 'Laboratorios Portugal';
    if (n.includes('medifarma')) return 'Medifarma';
    if (n.includes('genfar')) return 'Genfar';
    if (n.includes('ac farma')) return 'Laboratorios AC Farma';
    if (n.includes('roemmers')) return 'Roemmers';
    return 'Laboratorio Farmacéutico';
  }

  setFiltro(tipo: string): void {
    this.filtroTipo = tipo;
    this.aplicarFiltro();
  }

  aplicarFiltro(): void {
    const term = (this.searchTerm || '').trim().toLowerCase();
    this.batches = this.allBatches.filter(b => {
      const matchText = !term || 
        (b.medicineName && b.medicineName.toLowerCase().includes(term)) ||
        (b.batchNumber && b.batchNumber.toLowerCase().includes(term)) ||
        (b.manufacturer && b.manufacturer.toLowerCase().includes(term)) ||
        (b.barcode && b.barcode.toLowerCase().includes(term));

      if (!matchText) return false;

      switch (this.filtroTipo) {
        case 'DISPONIBLE':
        case 'CON_STOCK':
          return b.hasRealBatch !== false && b.quantityAvailable > 0 && b.fefoStatus !== 'VENCIDO' && b.fefoStatus !== 'RETIRAR';
        case 'POR_ABASTECER':
        case 'SIN_STOCK':
          return b.hasRealBatch === false || b.quantityAvailable === 0;
        case 'BAJO_STOCK':
          return b.hasRealBatch !== false && b.quantityAvailable <= 10 && b.quantityAvailable > 0 && b.fefoStatus !== 'VENCIDO';
        case 'ALERTA_CANJE':
          return b.hasRealBatch !== false && b.fefoStatus === 'ALERTA_CANJE';
        case 'RETIRAR':
          return b.hasRealBatch !== false && (b.fefoStatus === 'RETIRAR' || b.fefoStatus === 'VENCIDO');
        case 'VENCIDO':
          return b.hasRealBatch !== false && b.fefoStatus === 'VENCIDO';
        case 'CON_RECETA':
          return b.prescriptionRequired === true;
        case 'VENTA_LIBRE':
          return b.prescriptionRequired === false;
        default:
          return true;
      }
    });
  }

  limpiarFiltro(): void {
    this.searchTerm = '';
    this.filtroTipo = 'TODOS';
    this.aplicarFiltro();
  }

  // Contadores y Métricas Unificadas (100% coherentes con Dashboard)
  getMedicamentosTotalCount(): number {
    return this.medicinesList.length;
  }

  getMedicamentosConStockCount(): number {
    return this.medicinesList.filter(m => {
      return this.getStockForMedicine(m) > 0;
    }).length;
  }

  getMedicamentosSinStockCount(): number {
    return Math.max(0, this.getMedicamentosTotalCount() - this.getMedicamentosConStockCount());
  }

  getPhysicalBatchesCount(): number {
    return this.allBatches.filter(b => b.hasRealBatch !== false).length;
  }

  getTotalUnidadesAlmacen(): number {
    return this.allBatches
      .filter(b => b.hasRealBatch !== false)
      .reduce((acc, b) => acc + (Number(b.quantityAvailable) || 0), 0);
  }

  getKpiBajoStock(): number {
    return this.allBatches.filter(b => b.hasRealBatch !== false && b.quantityAvailable <= 10 && b.quantityAvailable > 0 && b.fefoStatus !== 'VENCIDO').length;
  }

  getCanjeCount(): number {
    return this.allBatches.filter(b => b.hasRealBatch !== false && b.fefoStatus === 'ALERTA_CANJE').length;
  }

  getRetirarCount(): number {
    return this.allBatches.filter(b => b.hasRealBatch !== false && (b.fefoStatus === 'RETIRAR' || b.fefoStatus === 'VENCIDO')).length;
  }

  getKpiVencidos(): number {
    return this.allBatches.filter(b => b.hasRealBatch !== false && b.fefoStatus === 'VENCIDO').length;
  }

  getKpiConReceta(): number {
    return this.medicinesList.filter(m => m.prescriptionRequired).length;
  }

  getKpiVentaLibre(): number {
    return this.medicinesList.filter(m => !m.prescriptionRequired).length;
  }

  private getStockForMedicine(medicine: Medicine): number {
    return this.allBatches
      .filter(b => b.hasRealBatch !== false && (
        Number(b.medicineId) === Number(medicine.id) ||
        this.normalizeMedicineName(b.medicineName) === this.normalizeMedicineName(medicine.name)
      ))
      .reduce((acc, b) => acc + (Number(b.quantityAvailable) || 0), 0);
  }

  private normalizeMedicineName(name?: string): string {
    return (name || '')
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .trim()
      .toLowerCase()
      .replace(/\s+/g, ' ');
  }

  // MODAL: Agregar Medicamento
  openAddMedicineModal(): void {
    const baseYear = new Date().getFullYear();
    this.newMedicineForm.reset({
      name: '',
      manufacturer: 'Laboratorios Bagó del Perú S.A.',
      category: 'Medicamento General',
      prescriptionRequired: false,
      barcode: '',
      hasInitialStock: true,
      initialStock: 100,
      batchNumber: 'LOT-' + baseYear + '-' + Math.floor(100 + Math.random() * 900),
      expiryDate: new Date(Date.now() + 365*24*60*60*1000*2).toISOString().split('T')[0],
      purchasePrice: 2.50,
      sellingPrice: 5.00
    });
    this.showAddMedicineModal = true;
  }

  closeAddMedicineModal(): void {
    this.showAddMedicineModal = false;
  }

  setPrescriptionRequired(value: boolean): void {
    this.newMedicineForm.patchValue({ prescriptionRequired: value });
  }

  saveNewMedicine(): void {
    if (this.newMedicineForm.invalid) {
      this.dialogService.error('Por favor completa el nombre del medicamento y el laboratorio.');
      return;
    }

    this.isLoading = true;
    const form = this.newMedicineForm.value;
    const autoHsn = 'MED-' + Math.floor(100000 + Math.random() * 900000);
    const autoBarcode = form.barcode?.trim() || ('775' + Math.floor(100000000 + Math.random() * 900000000));

    const payload: CreateMedicineRequest = {
      name: form.name.trim(),
      manufacturer: form.manufacturer.trim(),
      category: form.category?.trim() || 'General',
      barcode: autoBarcode,
      hsnCode: autoHsn,
      gstPercentage: 18.00,
      prescriptionRequired: form.prescriptionRequired === true,
      ...(form.hasInitialStock ? {
        initialStock: Number(form.initialStock) || 0,
        batchNumber: form.batchNumber?.trim() || ('LOT-' + Date.now().toString().slice(-6)),
        expiryDate: form.expiryDate || new Date(Date.now() + 365*24*60*60*1000*2).toISOString().split('T')[0],
        purchasePrice: Number(form.purchasePrice) || 1.0,
        sellingPrice: Number(form.sellingPrice) || 2.0
      } : {})
    };

    this.inventoryService.createMedicine(payload).subscribe({
      next: (med) => {
        this.auditLogService.recordActivity({
          action: 'MEDICINE_ADDED', entityType: 'MEDICINE', entityId: String(med.id),
          description: `Medicamento agregado: ${med.name}`
        }).subscribe({ error: () => undefined });
        this.dialogService.success('¡Medicamento "' + med.name + '" registrado exitosamente en inventario!');
        this.closeAddMedicineModal();
        this.refreshAll();
      },
      error: (err) => {
        this.dialogService.error('Error al registrar medicamento: ' + (err.message || 'Verifica los datos'));
        this.isLoading = false;
      }
    });
  }

  // MODALES DE STOCK Y EDICIÓN DE LOTE
  openStockModal(batch: Batch): void {
    this.editingBatch = batch;
    this.stockForm.patchValue({ quantityAvailable: batch.quantityAvailable });
    this.showStockModal = true;
  }

  closeStockModal(): void {
    this.showStockModal = false;
    this.editingBatch = null;
    this.stockForm.reset();
  }

  updateStock(): void {
    if (this.stockForm.invalid || !this.editingBatch) return;
    this.isLoading = true;
    const request: UpdateStockRequest = {
      quantityAvailable: this.stockForm.value.quantityAvailable,
      motivo: this.stockForm.value.motivo
    } as any;

    this.inventoryService.updateStock(this.editingBatch.id, request).subscribe({
      next: () => {
        this.dialogService.success('Stock actualizado exitosamente');
        this.refreshAll();
        this.closeStockModal();
      },
      error: (error) => {
        this.dialogService.error(error.message || 'Error al actualizar stock');
        this.isLoading = false;
      }
    });
  }

  openBatchModal(batch: Batch): void {
    this.editingBatch = batch;
    const expiryDate = new Date(batch.expiryDate).toISOString().split('T')[0];
    this.batchForm.patchValue({
      batchNumber: batch.batchNumber,
      expiryDate: expiryDate,
      purchasePrice: batch.purchasePrice,
      sellingPrice: batch.sellingPrice,
      quantityAvailable: batch.quantityAvailable
    });
    this.batchForm.get('quantityAvailable')?.disable();
    this.showBatchModal = true;
  }

  closeBatchModal(): void {
    this.showBatchModal = false;
    this.editingBatch = null;
    this.batchForm.reset();
  }

  updateBatch(): void {
    if (this.batchForm.invalid || !this.editingBatch) return;
    this.isLoading = true;
    const formValue = this.batchForm.value;
    const request: UpdateBatchRequest = {
      batchNumber: formValue.batchNumber,
      expiryDate: formValue.expiryDate,
      purchasePrice: formValue.purchasePrice,
      sellingPrice: formValue.sellingPrice,
      quantityAvailable: formValue.quantityAvailable
    };

    this.inventoryService.updateBatch(this.editingBatch.id, request).subscribe({
      next: () => {
        this.dialogService.success('Lote actualizado exitosamente');
        this.refreshAll();
        this.closeBatchModal();
      },
      error: (error) => {
        this.dialogService.error(error.message || 'Error al actualizar lote');
        this.isLoading = false;
      }
    });
  }

  async deleteBatch(batch: any): Promise<void> {
    if (!batch || !batch.id) {
      this.dialogService.warning('Este medicamento no cuenta con un lote físico registrado para retirar.');
      return;
    }
    const confirmed = await this.dialogService.confirm(
      '¿Estás seguro de que deseas retirar el lote "' + (batch.batchNumber || 'sin número') + '"?',
      'Retirar Lote'
    );
    if (!confirmed) return;

    this.isLoading = true;
    this.inventoryService.deleteBatch(batch.id).subscribe({
      next: () => {
        this.dialogService.success('Lote retirado correctamente');
        this.refreshAll();
      },
      error: (error) => {
        this.dialogService.error(error.error?.message || error.message || 'Error al retirar lote');
        this.isLoading = false;
      }
    });
  }

  // ==========================================
  // KARDEX / AUDITORÍA DE MOVIMIENTOS
  // ==========================================
  openKardexModal(productoId?: number): void {
    this.loadingKardex = true;
    this.showKardexModal = true;
    this.inventoryService.getMovimientos(productoId).subscribe({
      next: (movs) => {
        this.kardexList = movs || [];
        this.loadingKardex = false;
      },
      error: () => {
        this.kardexList = [];
        this.loadingKardex = false;
      }
    });
  }

  closeKardexModal(): void {
    this.showKardexModal = false;
    this.kardexList = [];
  }

  getMedicineNameById(prodId: number): string {
    const med = this.medicinesMap.get(prodId);
    return med ? med.name : ('Medicamento #' + prodId);
  }

  trackByBatchId(index: number, batch: Batch): any {
    return batch.id || index;
  }
}
