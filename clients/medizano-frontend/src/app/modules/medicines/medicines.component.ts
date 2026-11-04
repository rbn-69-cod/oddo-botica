import { Component, OnInit, OnDestroy } from '@angular/core';
import { FormBuilder, FormGroup, Validators } from '@angular/forms';
import { InventoryService } from '../../core/services/inventory.service';
import { DialogService } from '../../core/services/dialog.service';
import { Medicine, CreateMedicineRequest, UpdateMedicineRequest } from '../../core/models/medicine.model';
import { Batch, CreateBatchRequest, UpdateBatchRequest } from '../../core/models/batch.model';
import { Subscription, forkJoin, of } from 'rxjs';
import { catchError } from 'rxjs/operators';
import { AuditLogService } from '../../core/services/audit-log.service';

@Component({
  selector: 'app-medicines',
  standalone: false,
  templateUrl: './medicines.component.html',
  styleUrls: ['./medicines.component.scss']
})
export class MedicinesComponent implements OnInit, OnDestroy {
  medicines: Medicine[] = [];
  medicineForm: FormGroup;
  showForm = false;
  isLoading = false;
  editingMedicine: Medicine | null = null;
  isEditMode = false;
  
  // Stock management
  showStockModal = false;
  managingMedicine: Medicine | null = null;
  batches: Batch[] = [];
  stockForm: FormGroup;
  batchForm: FormGroup;
  editingBatch: Batch | null = null;
  isEditingBatch = false;
  originalStockQuantity: number = 0; // Store original stock when opening update modal
  private stockQuantitySubscription?: Subscription;

  constructor(
    private fb: FormBuilder,
    private inventoryService: InventoryService,
    private dialogService: DialogService,
    private auditLogService: AuditLogService
  ) {
    this.medicineForm = this.fb.group({
      name: ['', Validators.required],
      manufacturer: ['', Validators.required],
      category: [''],
      barcode: [''], // GTIN/EAN - identifies product
      hsnCode: ['', Validators.required],
      gstPercentage: [0, [Validators.required, Validators.min(0), Validators.max(100)]],
      prescriptionRequired: [false],
      // Optional: Initial stock and pricing
      initialStock: [null, [Validators.min(0)]],
      purchasePrice: [null, [Validators.min(0)]],
      sellingPrice: [null, [Validators.min(0)]],
      batchNumber: [''],
      expiryDate: ['']
    });

    // Stock management forms
    this.stockForm = this.fb.group({
      quantityAvailable: [0, [Validators.required, Validators.min(0)]],
      purchasePrice: [0, [Validators.required, Validators.min(0)]],
      sellingPrice: [0, [Validators.required, Validators.min(0)]]
    });

    this.batchForm = this.fb.group({
      batchNumber: ['', Validators.required],
      expiryDate: ['', Validators.required],
      purchasePrice: [0, [Validators.required, Validators.min(0)]],
      sellingPrice: [0, [Validators.required, Validators.min(0)]],
      quantityAvailable: [0, [Validators.required, Validators.min(0)]]
    });
  }

  ngOnInit(): void {
    this.loadMedicines();
  }

  get minDate(): string {
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    return tomorrow.toISOString().split('T')[0];
  }

  loadMedicines(): void {
    this.isLoading = true;
    forkJoin({
      medicines: this.inventoryService.getAllMedicines().pipe(
        catchError(err => {
          console.error('Error al cargar catálogo de medicamentos:', err);
          return of([] as Medicine[]);
        })
      ),
      batches: this.inventoryService.getAllBatches().pipe(
        catchError(err => {
          console.error('Error al cargar lotes de inventario:', err);
          return of([] as Batch[]);
        })
      )
    }).subscribe({
      next: ({ medicines, batches }) => {
        const batchList = batches || [];
        this.medicines = (medicines || []).map(med => {
          // Relacionar lotes pertenecientes única y exclusivamente a este medicineId
          const medBatches = batchList.filter(b => Number(b.medicineId) === Number(med.id));
          const stock = medBatches.reduce((sum, b) => sum + (Number(b.quantityAvailable) || 0), 0);

          return {
            ...med,
            totalStock: stock,
            availableStock: stock,
            lowStock: stock > 0 && stock <= (med.lowStockThreshold || 10),
            outOfStock: stock <= 0
          };
        });
        this.isLoading = false;
      },
      error: (error) => {
        console.error('Error general al cargar medicamentos e inventario:', error);
        this.dialogService.error('Error al cargar medicamentos: ' + (error.message || 'error desconocido'));
        this.isLoading = false;
      }
    });
  }

  openForm(medicine?: Medicine): void {
    this.showForm = true;
    this.isEditMode = !!medicine;
    this.editingMedicine = medicine || null;
    if (medicine) {
      this.medicineForm.patchValue({
        name: medicine.name,
        manufacturer: medicine.manufacturer,
        category: medicine.category || '',
        barcode: medicine.barcode || '',
        hsnCode: medicine.hsnCode,
        gstPercentage: medicine.gstPercentage,
        prescriptionRequired: medicine.prescriptionRequired
      });
    } else {
      this.medicineForm.reset({
        prescriptionRequired: false,
        gstPercentage: 0
      });
    }
  }

  closeForm(): void {
    this.showForm = false;
    this.medicineForm.reset();
    this.editingMedicine = null;
    this.isEditMode = false;
  }


  onSubmit(): void {
    if (this.medicineForm.invalid) {
      // Mark all fields as touched to show validation errors
      Object.keys(this.medicineForm.controls).forEach(key => {
        this.medicineForm.get(key)?.markAsTouched();
      });
      return;
    }

    this.isLoading = true;
    
    if (this.isEditMode && this.editingMedicine) {
      const formValue = this.medicineForm.value;
      const request: UpdateMedicineRequest = {
        name: formValue.name,
        manufacturer: formValue.manufacturer,
        category: formValue.category || undefined,
        barcode: formValue.barcode || undefined,
        hsnCode: formValue.hsnCode,
        gstPercentage: formValue.gstPercentage,
        prescriptionRequired: formValue.prescriptionRequired
      };
      this.inventoryService.updateMedicine(this.editingMedicine.id, request).subscribe({
        next: () => {
          this.loadMedicines();
          this.closeForm();
          this.isLoading = false;
        },
        error: (error) => {
          this.dialogService.error(error.message || 'Error al actualizar medicamento');
          this.isLoading = false;
        }
      });
    } else {
      const formValue = this.medicineForm.value;
      const request: CreateMedicineRequest = {
        name: formValue.name,
        manufacturer: formValue.manufacturer,
        category: formValue.category || undefined,
        barcode: formValue.barcode || undefined,
        hsnCode: formValue.hsnCode,
        gstPercentage: formValue.gstPercentage,
        prescriptionRequired: formValue.prescriptionRequired,
        // Include stock and pricing if provided
        initialStock: formValue.initialStock && formValue.initialStock > 0 ? formValue.initialStock : undefined,
        purchasePrice: formValue.purchasePrice && formValue.purchasePrice > 0 ? this.roundUpToCashIncrement(formValue.purchasePrice) : undefined,
        sellingPrice: formValue.sellingPrice && formValue.sellingPrice > 0 ? this.roundUpToCashIncrement(formValue.sellingPrice) : undefined,
        batchNumber: formValue.batchNumber && formValue.batchNumber.trim() ? formValue.batchNumber : undefined,
        expiryDate: formValue.expiryDate || undefined
      };
      
      this.inventoryService.createMedicine(request).subscribe({
        next: (createdMed: Medicine) => {
          this.auditLogService.recordActivity({
            action: 'MEDICINE_ADDED', entityType: 'MEDICINE', entityId: String(createdMed.id),
            description: `Medicamento agregado: ${createdMed.name}`
          }).subscribe({ error: () => undefined });
          if (request.initialStock && request.batchNumber && request.expiryDate) {
            this.inventoryService.createBatch({
              medicineId: createdMed.id,
              batchNumber: request.batchNumber,
              expiryDate: request.expiryDate,
              purchasePrice: request.purchasePrice || 0,
              sellingPrice: request.sellingPrice || 0,
              quantityAvailable: request.initialStock
            }).subscribe({
              next: () => {
                this.dialogService.success('Medicamento creado correctamente y lote inicial registrado en inventario.');
                this.loadMedicines();
                this.closeForm();
                this.isLoading = false;
              },
              error: () => {
                this.dialogService.warning('Medicamento creado, pero debe registrar el lote en inventario.');
                this.loadMedicines();
                this.closeForm();
                this.isLoading = false;
              }
            });
          } else {
            this.dialogService.success('Medicamento creado correctamente.');
            this.loadMedicines();
            this.closeForm();
            this.isLoading = false;
          }
        },
        error: (error) => {
          this.dialogService.error(error.message || 'Error al crear medicamento');
          this.isLoading = false;
        }
      });
    }
  }

  async deleteMedicine(medicine: Medicine): Promise<void> {
    if (!medicine || !medicine.id) return;
    const confirmed = await this.dialogService.confirm(
      '¿Estás seguro de que deseas eliminar el medicamento "' + medicine.name + '"?',
      'Eliminar Medicamento'
    );
    if (!confirmed) return;

    this.isLoading = true;
    this.inventoryService.deleteMedicine(medicine.id).subscribe({
      next: () => {
        this.dialogService.success('Medicamento eliminado correctamente.');
        this.loadMedicines();
        this.isLoading = false;
      },
      error: (error) => {
        this.dialogService.error(error.error?.message || error.message || 'Error al eliminar medicamento');
        this.isLoading = false;
      }
    });
  }

  trackByMedicineId(index: number, medicine: Medicine): any {
    return medicine.id || index;
  }

  // Stock Management Methods
  openStockModal(medicine: Medicine): void {
    this.managingMedicine = medicine;
    this.showStockModal = true;
    this.loadBatches(medicine.id);
    this.editingBatch = null;
    this.isEditingBatch = false;
    this.closeNewBatchModal(); // Ensure new batch modal is closed
  }

  closeStockModal(): void {
    this.showStockModal = false;
    this.managingMedicine = null;
    this.batches = [];
    this.stockForm.reset();
    this.batchForm.reset();
    this.editingBatch = null;
    this.isEditingBatch = false;
  }

  loadBatches(medicineId: number): void {
    this.isLoading = true;
    this.inventoryService.getBatchesByMedicine(medicineId).subscribe({
      next: (batches) => {
        this.batches = batches;
        this.isLoading = false;
      },
      error: (error) => {
        console.error('Error al cargar lotes:', error);
        this.dialogService.error('Error al cargar lotes: ' + (error.message || 'error desconocido'));
        this.isLoading = false;
      }
    });
  }

  openUpdateStockModal(batch: Batch): void {
    this.editingBatch = batch;
    this.isEditingBatch = true;
    this.originalStockQuantity = batch.quantityAvailable; // Store original quantity
    this.stockForm.patchValue({
      quantityAvailable: batch.quantityAvailable,
      purchasePrice: batch.purchasePrice,
      sellingPrice: batch.sellingPrice
    });
  }

  closeUpdateStockModal(): void {
    // Unsubscribe from valueChanges to prevent memory leaks
    if (this.stockQuantitySubscription) {
      this.stockQuantitySubscription.unsubscribe();
      this.stockQuantitySubscription = undefined;
    }
    
    this.editingBatch = null;
    this.isEditingBatch = false;
    this.originalStockQuantity = 0;
    this.stockForm.reset();
  }

  ngOnDestroy(): void {
    if (this.stockQuantitySubscription) {
      this.stockQuantitySubscription.unsubscribe();
    }
  }

  updateStock(): void {
    if (this.stockForm.invalid || !this.editingBatch) {
      return;
    }

    const formValue = this.stockForm.value;
    const request: UpdateBatchRequest = {
      batchNumber: this.editingBatch.batchNumber,
      expiryDate: this.editingBatch.expiryDate,
      quantityAvailable: formValue.quantityAvailable,
      purchasePrice: this.roundUpToCashIncrement(formValue.purchasePrice),
      sellingPrice: this.roundUpToCashIncrement(formValue.sellingPrice)
    };

    this.isLoading = true;
    this.inventoryService.updateBatch(this.editingBatch.id, request).subscribe({
      next: () => {
        if (this.managingMedicine) {
          this.loadBatches(this.managingMedicine.id);
          this.loadMedicines(); // Refresh medicines to update stock display
        }
        this.closeUpdateStockModal();
        this.isLoading = false;
      },
      error: (error) => {
        this.dialogService.error(error.message || 'Error al actualizar lote');
        this.isLoading = false;
      }
    });
  }

  openNewBatchModal(): void {
    this.editingBatch = { id: 0 } as Batch; // Set a dummy value to show modal
    this.isEditingBatch = false;
    this.batchForm.reset({
      purchasePrice: 0,
      sellingPrice: 0,
      quantityAvailable: 0
    });
  }

  closeNewBatchModal(): void {
    this.editingBatch = null;
    this.isEditingBatch = false;
    this.batchForm.reset();
  }

  saveBatch(): void {
    if (this.batchForm.invalid || !this.managingMedicine) {
      Object.keys(this.batchForm.controls).forEach(key => {
        this.batchForm.get(key)?.markAsTouched();
      });
      return;
    }

    this.isLoading = true;
    const formValue = this.batchForm.value;

    const request: CreateBatchRequest = {
      medicineId: this.managingMedicine.id,
      batchNumber: formValue.batchNumber,
      expiryDate: formValue.expiryDate,
      purchasePrice: this.roundUpToCashIncrement(formValue.purchasePrice),
      sellingPrice: this.roundUpToCashIncrement(formValue.sellingPrice),
      quantityAvailable: formValue.quantityAvailable
    };

    this.inventoryService.createBatch(request).subscribe({
      next: () => {
        if (this.managingMedicine) {
          this.loadBatches(this.managingMedicine.id);
          this.loadMedicines(); // Refresh medicines to update stock display
        }
        this.closeNewBatchModal();
        this.isLoading = false;
      },
      error: (error) => {
        this.dialogService.error(error.message || 'Error al crear lote');
        this.isLoading = false;
      }
    });
  }

  deleteBatch(batch: Batch): void {
    // Delete confirmation will be handled in async function

    this.isLoading = true;
    this.inventoryService.deleteBatch(batch.id).subscribe({
      next: () => {
        if (this.managingMedicine) {
          this.loadBatches(this.managingMedicine.id);
          this.loadMedicines(); // Refresh medicines to update stock display
        }
        this.isLoading = false;
      },
      error: (error) => {
        this.dialogService.error(error.message || 'Error al eliminar lote');
        this.isLoading = false;
      }
    });
  }

  isExpired(expiryDate: string): boolean {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const expiry = new Date(expiryDate);
    expiry.setHours(0, 0, 0, 0);
    return expiry.getTime() < today.getTime();
  }

  isExpiringSoon(expiryDate: string): boolean {
    const today = new Date();
    const expiry = new Date(expiryDate);
    const diffTime = Math.abs(expiry.getTime() - today.getTime());
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
    return diffDays <= 30 && !this.isExpired(expiryDate);
  }

  private roundUpToCashIncrement(value: number): number {
    const amount = Number(value || 0);
    if (amount <= 0) {
      return 0;
    }

    return Math.round((Math.ceil((amount - Number.EPSILON) * 10) / 10) * 10) / 10;
  }

  isLowStock(quantity: number): boolean {
    return quantity > 0 && quantity <= 10;
  }

}
