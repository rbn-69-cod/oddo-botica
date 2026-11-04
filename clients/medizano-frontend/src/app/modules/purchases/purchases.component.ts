import { Component, OnInit, OnDestroy, ChangeDetectorRef } from '@angular/core';
import { FormArray, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { Router, NavigationEnd } from '@angular/router';
import { filter } from 'rxjs/operators';
import {
  BrowserMultiFormatReader,
  BarcodeFormat,
  DecodeHintType,
  NotFoundException
} from '@zxing/library';
import { CompraService } from '../../core/services/compra.service';
import { ProveedorService } from '../../core/services/proveedor.service';
import { InventoryService } from '../../core/services/inventory.service';
import { DialogService } from '../../core/services/dialog.service';
import { Compra, EstadoCompra, RecepcionCompraRequest, TipoDocumentoCompra } from '../../core/models/compra.model';
import { Proveedor } from '../../core/models/proveedor.model';
import { AuthService } from '../../core/services/auth.service';
import { AuditLogService } from '../../core/services/audit-log.service';

export interface ScanLogItem {
  barcode: string;
  name: string;
  time: string;
  count: number;
}

@Component({
  selector: 'app-purchases',
  templateUrl: './purchases.component.html',
  styleUrls: ['./purchases.component.scss'],
  standalone: false
})
export class PurchasesComponent implements OnInit, OnDestroy {
  compras: Compra[] = [];
  proveedores: Proveedor[] = [];
  loading = false;
  page = 0;
  size = 20;
  totalPages = 0;
  totalElements = 0;

  activeTab: 'compras' | 'tracking' | 'scanner' = 'compras';

  get isHttp(): boolean {
    return typeof window !== 'undefined' && window.location.protocol === 'http:' && window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
  }

  cambiarAHttps(): void {
    if (typeof window !== 'undefined') {
      window.location.href = 'https://' + window.location.hostname + window.location.pathname + window.location.search;
    }
  }


  filtro = '';
  estadoFiltro = 'TODOS';

  totalComprasRecibidas = 0;
  totalComprasPendientes = 0;
  montoTotalMes = 0;

  // Modals
  showNuevaModal = false;
  showDetalleModal = false;
  showConfirmModal = false;

  // Modal para código de barras nuevo/desconocido
  showAssignBarcodeModal = false;
  scannedUnknownBarcode = '';
  selectedItemIndexToAssign = 0;

  selectedCompra?: Compra | null;
  compraForm!: FormGroup;
  recepcionForm!: FormGroup;

  errorMessage = '';
  successMessage = '';

  codigoBarrasInput = '';
  lastScannedMessage = '';
  lastScannedSuccess = true;
  highlightedRowIndex: number | null = null;

  // Camera Scanner matching Ventas / Billing
  isScanning = false;
  hasCamera = true;
  stream: MediaStream | null = null;
  private codeReader: BrowserMultiFormatReader | null = null;
  private lastScannedBarcode = '';
  private lastScannedAt = 0;
  private stableScanCount = 0;

  soundEnabled = true;
  scanHistory: ScanLogItem[] = [];
  totalScannedSessionCount = 0;

  readonly tiposDocumento: TipoDocumentoCompra[] = ['FACTURA', 'BOLETA', 'GUIA_REMISION', 'ORDEN_COMPRA'];

  constructor(
    private compraService: CompraService,
    private proveedorService: ProveedorService,
    private inventoryService: InventoryService,
    private dialogService: DialogService,
    private fb: FormBuilder,
    public authService: AuthService,
    private router: Router,
    private cdr: ChangeDetectorRef,
    private auditLogService: AuditLogService
  ) {
    this.initForms();
  }

  async ngOnInit(): Promise<void> {
    this.detectTabFromUrl(this.router.url);

    this.router.events
      .pipe(filter(event => event instanceof NavigationEnd))
      .subscribe((event: any) => {
        this.detectTabFromUrl(event.url);
      });

    this.cargarProveedores();
    this.cargarCatalogoMedicamentos();
    this.cargarCompras();
    await this.checkCameraAvailability();
  }

  ngOnDestroy(): void {
    this.stopScanning();
  }

  detectTabFromUrl(url: string): void {
    if (url.includes('/purchases/tracking') || url.includes('tab=tracking')) {
      this.activeTab = 'tracking';
    } else if (url.includes('/purchases/scanner') || url.includes('tab=scanner')) {
      this.activeTab = 'scanner';
      const ordenParaEscanear = this.compras.find(c => c.estado !== 'RECIBIDA' && c.estado !== 'CANCELADA');
      if (ordenParaEscanear) {
        if (!this.selectedCompra || this.selectedCompra.estado === 'RECIBIDA' || this.selectedCompra.estado === 'CANCELADA') {
          this.seleccionarParaVerificar(ordenParaEscanear);
        }
      } else {
        this.selectedCompra = undefined;
        this.itemsRecepcionArray.clear();
      }
    } else {
      this.activeTab = 'compras';
    }
  }

  setTab(tab: 'compras' | 'tracking' | 'scanner'): void {
    this.activeTab = tab;
    if (tab !== 'scanner') {
      this.stopScanning();
    }
    if (tab === 'scanner') {
      const porVerificar = this.compras.find(c => c.estado !== 'RECIBIDA' && c.estado !== 'CANCELADA');
      if (porVerificar) {
        if (!this.selectedCompra || this.selectedCompra.estado === 'RECIBIDA' || this.selectedCompra.estado === 'CANCELADA') {
          this.seleccionarParaVerificar(porVerificar);
        }
      } else {
        this.selectedCompra = undefined;
        this.itemsRecepcionArray.clear();
      }
    }
  }

  async checkCameraAvailability(): Promise<void> {
    try {
      if (navigator.mediaDevices && navigator.mediaDevices.enumerateDevices) {
        const devices = await navigator.mediaDevices.enumerateDevices();
        this.hasCamera = devices.some(device => device.kind === 'videoinput');
      } else {
        this.hasCamera = false;
      }
    } catch {
      this.hasCamera = false;
    }
  }

  initForms(): void {
    this.compraForm = this.fb.group({
      proveedorId: [null, [Validators.required]],
      tipoDocumento: ['FACTURA', [Validators.required]],
      numeroDocumento: ['', [Validators.required]],
      fechaEmision: [new Date().toISOString().split('T')[0], [Validators.required]],
      observaciones: [''],
      detalles: this.fb.array([])
    });

    this.recepcionForm = this.fb.group({
      usuarioRecepcion: [this.authService.getCurrentUser()?.username || 'admin', [Validators.required]],
      observaciones: ['Mercadería verificada con escáner e ingresada a almacén FEFO'],
      items: this.fb.array([])
    });
  }

  get detallesFormArray(): FormArray {
    return this.compraForm.get('detalles') as FormArray;
  }

  get itemsRecepcionArray(): FormArray {
    return this.recepcionForm.get('items') as FormArray;
  }

  asFormGroup(ctrl: any): FormGroup {
    return ctrl as FormGroup;
  }

  agregarDetalle(
    productoId: number = 0,
    nombre: string = '',
    barcode: string = '',
    costo: number = 1.00,
    precioVenta: number = 2.00,
    cantidad: number = 100,
    proveedorId?: number,
    prescriptionRequired: boolean = false
  ): void {
    const baseYear = new Date().getFullYear();
    const currentProv = proveedorId || this.compraForm.get('proveedorId')?.value || (this.proveedores[0]?.id || 1);
    const item = this.fb.group({
      productoId: [productoId || Math.floor(100 + Math.random() * 900)],
      nombreProducto: [nombre, [Validators.required]],
      codigoBarra: [barcode],
      cantidadComprada: [cantidad, [Validators.required, Validators.min(1)]],
      costoUnitario: [costo, [Validators.required, Validators.min(0.01)]],
      precioVenta: [precioVenta, [Validators.required, Validators.min(0.01)]],
      descuento: [0],
      loteSugerido: ['LOT-' + (baseYear + 1) + '-' + Math.floor(100 + Math.random() * 900)],
      fechaVencimiento: [new Date(Date.now() + 365*24*60*60*1000*2).toISOString().split('T')[0]],
      proveedorId: [currentProv, [Validators.required]],
      prescriptionRequired: [prescriptionRequired]
    });
    this.detallesFormArray.push(item);
  }

  toggleRecetaDetalle(index: number): void {
    const ctrl = this.detallesFormArray.at(index);
    if (!ctrl) return;
    const current = !!ctrl.get('prescriptionRequired')?.value;
    ctrl.patchValue({ prescriptionRequired: !current });
  }

  toggleRecetaRecepcion(index: number): void {
    const ctrl = this.itemsRecepcionArray.at(index);
    if (!ctrl) return;
    const current = !!ctrl.get('prescriptionRequired')?.value;
    ctrl.patchValue({ prescriptionRequired: !current });
  }

  eliminarDetalle(index: number): void {
    this.detallesFormArray.removeAt(index);
  }

  calcularSubtotal(): number {
    return this.detallesFormArray.controls.reduce((acc, ctrl) => {
      const cant = ctrl.get('cantidadComprada')?.value || 0;
      const costo = ctrl.get('costoUnitario')?.value || 0;
      const desc = ctrl.get('descuento')?.value || 0;
      return acc + (cant * costo) - desc;
    }, 0);
  }

  cargarProveedores(): void {
    this.proveedorService.listarProveedores({ size: 100 }).subscribe({
      next: (resp) => {
        this.proveedores = resp.content;
        if (this.proveedores.length > 0 && !this.compraForm.get('proveedorId')?.value) {
          this.compraForm.patchValue({ proveedorId: this.proveedores[0].id });
        }
      },
      error: () => {
        this.errorMessage = 'No se pudo conectar con el catálogo de proveedores peruanos.';
      }
    });
  }

  cargarCompras(): void {
    this.loading = true;
    this.errorMessage = '';
    this.compraService.listarCompras(this.page, this.size, this.filtro, this.estadoFiltro).subscribe({
      next: (resp) => {
        this.compras = resp.content;
        this.totalPages = resp.totalPages;
        this.totalElements = resp.totalElements;
        this.loading = false;
        this.calcularKPIs();

        if (this.selectedCompra) {
          const found = this.compras.find(c => c.id === this.selectedCompra?.id);
          if (found && found.estado !== 'RECIBIDA' && found.estado !== 'CANCELADA') {
            this.selectedCompra = found;
          } else {
            const siguientePendiente = this.compras.find(c => c.estado !== 'RECIBIDA' && c.estado !== 'CANCELADA');
            if (siguientePendiente) {
              this.seleccionarParaVerificar(siguientePendiente);
            } else {
              this.selectedCompra = undefined;
              this.itemsRecepcionArray.clear();
            }
          }
        } else if (this.compras.length > 0) {
          const ordenParaEscanear = this.compras.find(c => c.estado !== 'RECIBIDA' && c.estado !== 'CANCELADA');
          if (ordenParaEscanear) {
            this.seleccionarParaVerificar(ordenParaEscanear);
          } else {
            this.selectedCompra = undefined;
            this.itemsRecepcionArray.clear();
          }
        }
      },
      error: (err) => {
        this.errorMessage = err.message || 'Error al listar las órdenes de compra.';
        this.loading = false;
      }
    });
  }

  calcularKPIs(): void {
    this.totalComprasRecibidas = this.compras.filter(c => c.estado === 'RECIBIDA').length;
    this.totalComprasPendientes = this.compras.filter(c => c.estado !== 'RECIBIDA' && c.estado !== 'CANCELADA').length;
    this.montoTotalMes = this.compras
      .filter(c => c.estado !== 'CANCELADA')
      .reduce((sum, c) => sum + (c.total || 0), 0);
  }

  buscar(): void {
    this.page = 0;
    this.cargarCompras();
  }

  limpiar(): void {
    this.filtro = '';
    this.estadoFiltro = 'TODOS';
    this.page = 0;
    this.cargarCompras();
  }

  cargandoBajoStock = false;

  abrirNuevaCompra(): void {
    const defaultProv = this.proveedores.length > 0 ? this.proveedores[0].id : 1;
    this.compraForm.reset({
      proveedorId: defaultProv,
      tipoDocumento: 'FACTURA',
      numeroDocumento: 'F001-' + Math.floor(100000 + Math.random() * 900000),
      fechaEmision: new Date().toISOString().split('T')[0],
      observaciones: 'Reposición programada de medicamentos a laboratorio'
    });
    this.detallesFormArray.clear();
    this.agregarDetalle(1, 'Paracetamol 500mg Tabletas', '', 1.20, 2.50, 100);
    this.agregarDetalle(2, 'Amoxicilina 500mg Cápsulas', '', 2.50, 5.00, 50);
    this.errorMessage = '';
    this.successMessage = '';
    this.showNuevaModal = true;
  }

  cerrarNuevaModal(): void {
    this.showNuevaModal = false;
  }

  abrirNuevaCompraConBajoStock(): void {
    this.abrirNuevaCompra();
    this.cargarMedicamentosBajoStockEnFormulario();
  }

  cargarMedicamentosBajoStockEnFormulario(): void {
    this.cargandoBajoStock = true;
    this.errorMessage = '';
    this.inventoryService.getAllMedicines().subscribe({
      next: (medicines) => {
        this.cargandoBajoStock = false;
        const bajoStock = (medicines || []).filter(m => 
          m.outOfStock || m.lowStock || (m.availableStock !== undefined && m.availableStock <= (m.lowStockThreshold || 10)) || (m.totalStock === 0)
        );

        const itemsACargar = (bajoStock.length > 0) ? bajoStock : (medicines.length > 0 ? medicines : []);

        if (itemsACargar.length > 0) {
          this.detallesFormArray.clear();
          itemsACargar.forEach((med, idx) => {
            const cantSugerida = ((med.lowStockThreshold || 10) * 10) || 100;
            const costo = med.purchasePrice || 2.50;
            const pvp = med.sellingPrice || 5.00;
            this.agregarDetalle(
              med.id || (idx + 1),
              med.name + (med.manufacturer ? ' (' + med.manufacturer + ')' : ''),
              med.barcode || '',
              costo,
              pvp,
              cantSugerida
            );
          });

          if (itemsACargar[0].manufacturer && this.proveedores.length > 0) {
            const mfg = itemsACargar[0].manufacturer.toLowerCase();
            const prov = this.proveedores.find(p => 
              p.razonSocial.toLowerCase().includes(mfg) ||
              (p.nombreComercial && p.nombreComercial.toLowerCase().includes(mfg))
            );
            if (prov) {
              this.compraForm.patchValue({ proveedorId: prov.id });
            }
          }

          this.compraForm.patchValue({
            numeroDocumento: 'F001-RESTOCK-' + Math.floor(1000 + Math.random() * 9000),
            observaciones: 'Reposición urgente por stock crítico / desabastecimiento de medicamentos.'
          });

          this.successMessage = '⚡ Se cargaron automáticamente ' + itemsACargar.length + ' medicamentos en stock bajo para reposición.';
        } else {
          this.cargarFallbackBajoStock();
        }
      },
      error: () => {
        this.cargandoBajoStock = false;
        this.cargarFallbackBajoStock();
      }
    });
  }

  private cargarFallbackBajoStock(): void {
    this.detallesFormArray.clear();
    this.agregarDetalle(1, 'Paracetamol 500 mg (Laboratorio Portugal)', '7751234567890', 2.00, 5.00, 100);
    this.agregarDetalle(2, 'Amoxicilina 500 mg (Laboratorios Bagó)', '7759876543210', 8.00, 15.50, 50);
    this.agregarDetalle(3, 'Ibuprofeno 400 mg (Genfar)', '7755554443332', 3.50, 8.00, 80);
    this.compraForm.patchValue({
      numeroDocumento: 'F001-RESTOCK-' + Math.floor(1000 + Math.random() * 9000),
      observaciones: 'Reposición preventiva de medicamentos bajo stock.'
    });
    this.successMessage = '⚡ Se cargaron 3 medicamentos en estado crítico para reposición de stock.';
  }

  guardarCompra(): void {
    if (this.loading) return;
    if (this.modoCompra === 'MULTI_LABORATORIO') {
      this.guardarComprasMultiples();
      return;
    }

    if (!this.compraForm.get('proveedorId')?.value && this.proveedores.length > 0) {
      this.compraForm.patchValue({ proveedorId: this.proveedores[0].id });
    }

    if (!this.compraForm.get('numeroDocumento')?.value) {
      this.compraForm.patchValue({
        numeroDocumento: 'F001-' + Math.floor(100000 + Math.random() * 900000)
      });
    }

    if (this.detallesFormArray.length === 0) {
      this.errorMessage = 'Debe incluir al menos un medicamento en la orden de compra. Usa "+ Agregar Medicamento" o "⚡ Cargar Productos con Bajo Stock".';
      return;
    }

    for (let i = 0; i < this.detallesFormArray.length; i++) {
      const row = this.detallesFormArray.at(i);
      const nombre = row.get('nombreProducto')?.value;
      const cant = row.get('cantidadComprada')?.value;
      const costo = row.get('costoUnitario')?.value;

      if (!nombre || !nombre.trim()) {
        this.errorMessage = 'Por favor especifica el nombre del medicamento en el ítem #' + (i + 1) + '.';
        return;
      }
      if (!cant || cant <= 0) {
        this.errorMessage = 'La cantidad en el ítem #' + (i + 1) + ' (' + nombre + ') debe ser mayor a 0.';
        return;
      }
      if (costo === null || costo === undefined || costo < 0) {
        this.errorMessage = 'El costo unitario en el ítem #' + (i + 1) + ' (' + nombre + ') no puede ser menor a cero.';
        return;
      }
    }

    const formVal = this.compraForm.value;

    const itemsPayload = (formVal.detalles || []).map((d: any) => ({
      productoId: Number(d.productoId) || Math.floor(100 + Math.random() * 900),
      nombreProducto: (d.nombreProducto || '').trim(),
      cantidad: Number(d.cantidadComprada) || 1,
      cantidadComprada: Number(d.cantidadComprada) || 1,
      costoUnitario: Number(d.costoUnitario) || 1.0,
      precioVenta: Number(d.precioVenta) || 2.0,
      descuento: Number(d.descuento) || 0,
      loteSugerido: d.loteSugerido || ('LOT-' + (new Date().getFullYear() + 1) + '-' + Math.floor(100 + Math.random() * 900)),
      fechaVencimiento: d.fechaVencimiento || new Date(Date.now() + 365*24*60*60*1000*2).toISOString().split('T')[0],
      codigoBarra: (d.codigoBarra || '').trim()
    }));

    const payload = {
      proveedorId: Number(formVal.proveedorId) || (this.proveedores[0]?.id || 1),
      tipoDocumento: formVal.tipoDocumento || 'FACTURA',
      numeroDocumento: (formVal.numeroDocumento || 'F001-' + Date.now()).trim().toUpperCase(),
      fechaEmision: formVal.fechaEmision || new Date().toISOString().split('T')[0],
      observaciones: formVal.observaciones || 'Reposición formal de medicamentos para botica',
      usuarioRegistro: this.authService.getCurrentUser()?.username || 'admin',
      items: itemsPayload,
      detalles: itemsPayload
    };

    this.loading = true;
    this.errorMessage = '';
    this.successMessage = '';

    this.compraService.crearCompra(payload as any).subscribe({
      next: (nueva) => {
        this.auditLogService.recordActivity({
          action: 'PURCHASE_CREATED', entityType: 'PURCHASE', entityId: String(nueva.id),
          description: `Pedido de productos creado: ${nueva.numeroDocumento || nueva.id}`
        }).subscribe({ error: () => undefined });
        this.successMessage = '✅ ¡Orden ' + (nueva.numeroDocumento || payload.numeroDocumento) + ' emitida exitosamente al laboratorio!';
        this.cerrarNuevaModal();
        this.cargarCompras();
        this.loading = false;
      },
      error: (err) => {
        console.error('Error al emitir orden:', err);
        this.errorMessage = err.message || 'Error al emitir orden de compra.';
        this.loading = false;
      }
    });
  }

  avanzarTracking(compra: Compra): void {
    const siguienteEstado: Record<string, string> = {
      'BORRADOR': 'PENDIENTE',
      'PENDIENTE': 'ORDEN_ACEPTADA',
      'ORDEN_ACEPTADA': 'EMPAQUETANDO',
      'EMPAQUETANDO': 'EN_CAMINO',
      'EN_CAMINO': 'EN_ENTREGA',
      'EN_ENTREGA': 'POR_VERIFICAR',
      'POR_VERIFICAR': 'VERIFICANDO'
    };

    const target = siguienteEstado[compra.estado];
    if (!target) return;

    this.compraService.actualizarEstado(compra.id, target).subscribe({
      next: (upd) => {
        compra.estado = upd.estado;
        this.successMessage = 'Estado actualizado a "' + this.getEstadoLabel(upd.estado) + '" para la orden ' + compra.numeroDocumento + '.';
        this.cargarCompras();
        if (target === 'POR_VERIFICAR') {
          this.seleccionarParaVerificar({ ...compra, estado: upd.estado });
          this.router.navigate(['/purchases/scanner'], { queryParams: { compraId: compra.id } });
        }
      },
      error: (err) => {
        this.errorMessage = err.message || 'Error al actualizar el tracking de la orden.';
      }
    });
  }

  irAEscanear(compra: Compra): void {
    this.seleccionarParaVerificar(compra);
    this.activeTab = 'scanner';
  }

  seleccionarParaVerificar(compra: Compra): void {
    this.selectedCompra = compra;
    this.itemsRecepcionArray.clear();
    this.scanHistory = [];
    this.totalScannedSessionCount = 0;

    const baseYear = new Date().getFullYear();

    (compra.detalles || []).forEach((det, idx) => {
      const suggestedBarcode = det.codigoBarra || '';
      const suggestedLot = det.loteSugerido || ('LOTE-' + (baseYear + 1) + '-X' + (idx + 1));
      const suggestedExpiry = det.fechaVencimiento || (baseYear + 2 + '-12-31');
      const costoUnitario = det.costoUnitario || 1.00;
      const precioVenta = det.precioVenta || Number((costoUnitario * 2.0).toFixed(2));

      // Determinar si requiere receta médica (del catálogo existente si ya hay, o por nombre)
      let isRx = false;
      const existing = (this.medicamentosCatalogo || []).find(m =>
        (det.productoId && m.id === det.productoId) ||
        (det.codigoBarra && m.barcode === det.codigoBarra) ||
        (det.nombreProducto && m.name && m.name.toLowerCase().trim() === det.nombreProducto.toLowerCase().trim())
      );
      if (existing && existing.prescriptionRequired !== undefined) {
        isRx = !!existing.prescriptionRequired;
      }

      const itemGroup = this.fb.group({
        detalleId: [det.id || (idx + 1), Validators.required],
        productoId: [det.productoId],
        nombreProducto: [det.nombreProducto],
        codigoBarra: [suggestedBarcode],
        cantidadComprada: [det.cantidadComprada],
        cantidadRecibida: [det.cantidadRecibida || 0, [Validators.required, Validators.min(0)]],
        costoUnitario: [costoUnitario, [Validators.required, Validators.min(0.01)]],
        precioVenta: [precioVenta, [Validators.required, Validators.min(0.01)]],
        batchNumber: [suggestedLot, Validators.required],
        expiryDate: [suggestedExpiry, Validators.required],
        prescriptionRequired: [isRx]
      });

      this.itemsRecepcionArray.push(itemGroup);
    });

    if (compra.estado === 'POR_VERIFICAR') {
      this.compraService.actualizarEstado(compra.id, 'VERIFICANDO').subscribe({
        next: (upd) => { compra.estado = upd.estado; }
      });
    }
  }

  onCompraSelectChange(id: any): void {
    const numId = Number(id);
    const found = this.compras.find(c => c.id === numId);
    if (found) {
      this.seleccionarParaVerificar(found);
    }
  }

  // ==========================================
  // ESCÁNER DE CÁMARA (IDÉNTICO A VENTAS / POS)
  // ==========================================

  async startScanning(): Promise<void> {
    if (this.isHttp) {
      const msg = 'Para que el navegador permita activar la camara, se requiere conexion segura HTTPS. Deseas cambiar a HTTPS ahora?';
      if (confirm(msg)) {
        this.cambiarAHttps();
        return;
      }
    }

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      this.dialogService.error('Tu navegador bloquea la camara sobre HTTP. Por favor abre el sistema con HTTPS: https://' + window.location.hostname + '/');
      return;
    }

    try {
      this.isScanning = true;
      this.cdr.detectChanges();

      let videoElement: HTMLVideoElement | null = null;
      let retries = 0;
      const maxRetries = 50;

      while (!videoElement && retries < maxRetries) {
        await new Promise(resolve => setTimeout(resolve, 100));
        videoElement = document.getElementById('video-scanner') as HTMLVideoElement;
        if (!videoElement) {
          this.cdr.detectChanges();
        }
        retries++;
      }

      if (!videoElement) {
        this.dialogService.error('No se pudo abrir el visor de camara. Actualiza la pagina e intenta otra vez.');
        this.isScanning = false;
        return;
      }

      const hints = new Map();
      const formats = [
        BarcodeFormat.CODE_128,
        BarcodeFormat.CODE_39,
        BarcodeFormat.CODE_93,
        BarcodeFormat.ITF,
        BarcodeFormat.CODABAR,
        BarcodeFormat.EAN_13,
        BarcodeFormat.EAN_8,
        BarcodeFormat.UPC_A,
        BarcodeFormat.UPC_E,
        BarcodeFormat.DATA_MATRIX,
        BarcodeFormat.QR_CODE,
        BarcodeFormat.PDF_417,
        BarcodeFormat.AZTEC
      ].filter(f => f !== undefined);

      hints.set(DecodeHintType.POSSIBLE_FORMATS, formats);
      hints.set(DecodeHintType.TRY_HARDER, true);

      this.codeReader = new BrowserMultiFormatReader(hints);
      let selectedDeviceId: string | null = null;
      try {
        const videoInputDevices = await this.codeReader.listVideoInputDevices();
        if (videoInputDevices && videoInputDevices.length > 0) {
          const backCam = videoInputDevices.find(d => /back|rear|environment|trasera|posterior/i.test(d.label));
          const chosen = backCam || videoInputDevices[videoInputDevices.length - 1];
          if (chosen && chosen.deviceId) {
            selectedDeviceId = chosen.deviceId;
          }
        }
      } catch (err) {
        console.warn('No se pudieron listar camaras:', err);
      }

      const video = videoElement;
      video.setAttribute('playsinline', 'true');
      video.setAttribute('autoplay', 'true');
      video.setAttribute('muted', 'true');

      await this.codeReader.decodeFromVideoDevice(
        selectedDeviceId,
        video,
        (result, error) => {
          if (result) {
            const barcode = result.getText();
            if (this.isStableScan(barcode)) {
              this.handleScannedBarcode(barcode);
            }
          }
          if (error && !(error instanceof NotFoundException)) {
            console.error('Error de escaneo:', error);
          }
        }
      );
      this.stream = video.srcObject as MediaStream | null;
    } catch (error: any) {
      console.error('Error al iniciar cámara:', error);
      if (error.name === 'NotAllowedError' || error.name === 'PermissionDeniedError') {
        this.dialogService.error('Permiso de cámara denegado. Habilita el acceso a la cámara.');
      } else {
        this.dialogService.error('No se pudo iniciar la cámara: ' + (error.message || 'error desconocido'));
      }
      this.isScanning = false;
      this.stopScanning();
    }
  }

  stopScanning(): void {
    const videoElement = document.getElementById('video-scanner') as HTMLVideoElement;
    if (videoElement) {
      videoElement.srcObject = null;
      videoElement.pause();
    }

    if (this.codeReader) {
      this.codeReader.reset();
      this.codeReader = null;
    }

    if (this.stream) {
      this.stream.getTracks().forEach(track => track.stop());
      this.stream = null;
    }

    this.isScanning = false;
    this.lastScannedBarcode = '';
    this.lastScannedAt = 0;
    this.stableScanCount = 0;
  }

  private isStableScan(value: string): boolean {
    const now = Date.now();
    if (!value) return false;

    if (value === this.lastScannedBarcode && now - this.lastScannedAt < 1200) {
      return false; // Evitar disparos duplicados inmediatos
    }

    this.lastScannedBarcode = value;
    this.lastScannedAt = now;
    return true;
  }

  handleScannedBarcode(barcode: string): void {
    this.escanearCodigo(barcode);
  }

  // ==========================================
  // LÓGICA DE DETECCIÓN Y ASIGNACIÓN DE CÓDIGOS
  // ==========================================

  escanearCodigo(codeOverride?: string): void {
    const code = (codeOverride || this.codigoBarrasInput || '').trim();
    if (!code) return;

    let matchedIndex = -1;
    for (let i = 0; i < this.itemsRecepcionArray.length; i++) {
      const itemCtrl = this.itemsRecepcionArray.at(i);
      const barcode = (itemCtrl.get('codigoBarra')?.value || '').trim();

      if (barcode && barcode === code) {
        matchedIndex = i;
        break;
      }
    }

    if (matchedIndex !== -1) {
      // CÓDIGO CONOCIDO -> Directo suma +1
      const targetCtrl = this.itemsRecepcionArray.at(matchedIndex);
      const actual = targetCtrl.get('cantidadRecibida')?.value || 0;
      const comprada = targetCtrl.get('cantidadComprada')?.value || 0;
      const nombre = targetCtrl.get('nombreProducto')?.value || 'Medicamento';

      const nuevaCantidad = actual + 1;
      targetCtrl.patchValue({ cantidadRecibida: nuevaCantidad });

      this.playBeepSound();
      this.triggerFlashEffect(matchedIndex);

      this.totalScannedSessionCount++;
      this.scanHistory.unshift({
        barcode: code,
        name: nombre,
        time: new Date().toLocaleTimeString(),
        count: nuevaCantidad
      });
      if (this.scanHistory.length > 8) this.scanHistory.pop();

      this.lastScannedSuccess = true;
      this.lastScannedMessage = '✅ Reconocido: ' + nombre + ' (+1 ud) · Total: ' + nuevaCantidad + '/' + comprada + ' uds';
      this.codigoBarrasInput = '';
    } else {
      // CÓDIGO NUEVO / NO ASIGNADO
      this.scannedUnknownBarcode = code;
      this.selectedItemIndexToAssign = 0;
      this.showAssignBarcodeModal = true;
      this.codigoBarrasInput = '';
    }
  }

  asignarCodigoNuevo(): void {
    if (this.selectedItemIndexToAssign < 0 || this.selectedItemIndexToAssign >= this.itemsRecepcionArray.length) {
      return;
    }

    const targetCtrl = this.itemsRecepcionArray.at(this.selectedItemIndexToAssign);
    targetCtrl.patchValue({ codigoBarra: this.scannedUnknownBarcode });

    const actual = targetCtrl.get('cantidadRecibida')?.value || 0;
    const comprada = targetCtrl.get('cantidadComprada')?.value || 0;
    const nombre = targetCtrl.get('nombreProducto')?.value || 'Medicamento';

    const nuevaCantidad = actual + 1;
    targetCtrl.patchValue({ cantidadRecibida: nuevaCantidad });

    this.playBeepSound();
    this.triggerFlashEffect(this.selectedItemIndexToAssign);

    this.totalScannedSessionCount++;
    this.scanHistory.unshift({
      barcode: this.scannedUnknownBarcode,
      name: nombre,
      time: new Date().toLocaleTimeString(),
      count: nuevaCantidad
    });

    this.lastScannedSuccess = true;
    this.lastScannedMessage = '✅ Código ' + this.scannedUnknownBarcode + ' asignado a "' + nombre + '". Contabilizado: ' + nuevaCantidad + '/' + comprada + ' uds';
    this.showAssignBarcodeModal = false;
    this.scannedUnknownBarcode = '';
  }

  cerrarAssignModal(): void {
    this.showAssignBarcodeModal = false;
    this.scannedUnknownBarcode = '';
  }

  simularEscaneo(barcode: string): void {
    this.escanearCodigo(barcode);
  }

  private triggerFlashEffect(index: number): void {
    this.highlightedRowIndex = index;
    setTimeout(() => {
      this.highlightedRowIndex = null;
    }, 600);
  }

  sumarUno(index: number): void {
    this.sumarCantidad(index, 1);
  }

  sumarCantidad(index: number, delta: number): void {
    const ctrl = this.itemsRecepcionArray.at(index);
    const actual = ctrl.get('cantidadRecibida')?.value || 0;
    const max = ctrl.get('cantidadComprada')?.value || 9999;
    const nuevo = Math.min(actual + delta, max);
    ctrl.patchValue({ cantidadRecibida: nuevo });
    this.playBeepSound();
    this.triggerFlashEffect(index);
  }

  restarUno(index: number): void {
    const ctrl = this.itemsRecepcionArray.at(index);
    const actual = ctrl.get('cantidadRecibida')?.value || 0;
    if (actual > 0) {
      ctrl.patchValue({ cantidadRecibida: actual - 1 });
    }
  }

  completarItem(index: number): void {
    const ctrl = this.itemsRecepcionArray.at(index);
    const comprada = ctrl.get('cantidadComprada')?.value || 0;
    ctrl.patchValue({ cantidadRecibida: comprada });
    this.playBeepSound();
    this.triggerFlashEffect(index);
  }

  completarTodos(): void {
    for (let i = 0; i < this.itemsRecepcionArray.length; i++) {
      this.completarItem(i);
    }
    this.successMessage = '⚡ Todas las cantidades fueron completadas según la orden de compra (Modo Caja Máster).';
  }

  getItemProgressPercent(index: number): number {
    const ctrl = this.itemsRecepcionArray.at(index);
    if (!ctrl) return 0;
    const recibida = ctrl.get('cantidadRecibida')?.value || 0;
    const comprada = ctrl.get('cantidadComprada')?.value || 1;
    return Math.min(Math.round((recibida / comprada) * 100), 100);
  }

  isItemComplete(index: number): boolean {
    const ctrl = this.itemsRecepcionArray.at(index);
    if (!ctrl) return false;
    const recibida = ctrl.get('cantidadRecibida')?.value || 0;
    const comprada = ctrl.get('cantidadComprada')?.value || 1;
    return recibida >= comprada && comprada > 0;
  }

  getTotalProgreso(): number {
    if (this.itemsRecepcionArray.length === 0) return 0;
    let totalPedida = 0;
    let totalRecibida = 0;
    for (let i = 0; i < this.itemsRecepcionArray.length; i++) {
      const ctrl = this.itemsRecepcionArray.at(i);
      totalPedida += ctrl.get('cantidadComprada')?.value || 0;
      totalRecibida += ctrl.get('cantidadRecibida')?.value || 0;
    }
    if (totalPedida === 0) return 0;
    return Math.min(Math.round((totalRecibida / totalPedida) * 100), 100);
  }

  isTodoVerificado(): boolean {
    if (this.itemsRecepcionArray.length === 0) return false;
    return this.itemsRecepcionArray.controls.every(ctrl => {
      const rec = ctrl.get('cantidadRecibida')?.value || 0;
      return rec > 0;
    });
  }

  // Margen de ganancia
  calcularMargenPorcentaje(costo: number, pvp: number): number {
    if (!costo || costo <= 0) return 0;
    return Math.round(((pvp - costo) / costo) * 100);
  }

  calcularGananciaUnitaria(costo: number, pvp: number): number {
    return Number(Math.max(pvp - costo, 0).toFixed(2));
  }

  toggleSound(): void {
    this.soundEnabled = !this.soundEnabled;
  }

  playBeepSound(): void {
    if (!this.soundEnabled) return;
    try {
      const audioCtx = new (window.AudioContext || (window as any).webkitAudioContext)();
      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();
      osc.connect(gain);
      gain.connect(audioCtx.destination);
      osc.type = 'sine';
      osc.frequency.setValueAtTime(880, audioCtx.currentTime);
      gain.gain.setValueAtTime(0.2, audioCtx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.12);
      osc.start();
      osc.stop(audioCtx.currentTime + 0.12);
    } catch {}
  }

  abrirConfirmarModal(): void {
    if (!this.selectedCompra || this.recepcionForm.invalid) return;
    this.showConfirmModal = true;
  }

  cerrarConfirmarModal(): void {
    this.showConfirmModal = false;
  }

  confirmarRecepcionFinal(): void {
    if (!this.selectedCompra) {
      this.errorMessage = 'No hay ninguna orden de compra seleccionada.';
      return;
    }
    if (this.recepcionForm.invalid) {
      const invalidItems: string[] = [];
      this.itemsRecepcionArray.controls.forEach((c, idx) => {
        if (c.invalid) {
          const nom = c.get('nombreProducto')?.value || ('Ítem #' + (idx + 1));
          invalidItems.push(nom);
        }
      });
      this.errorMessage = 'Verifica que la cantidad recibida sea mayor a 0 y los datos sean válidos en: ' +
        (invalidItems.length > 0 ? invalidItems.join(', ') : 'la recepción.');
      return;
    }

    const payload: RecepcionCompraRequest = {
      usuarioRecepcion: this.recepcionForm.value.usuarioRecepcion,
      observaciones: this.recepcionForm.value.observaciones,
      items: this.itemsRecepcionArray.value.map((i: any) => ({
        detalleId: i.detalleId,
        cantidadRecibida: i.cantidadRecibida,
        batchNumber: i.batchNumber,
        expiryDate: i.expiryDate,
        purchasePrice: i.costoUnitario,
        sellingPrice: i.precioVenta,
        codigoBarra: i.codigoBarra
      }))
    };

    this.loading = true;
    this.compraService.confirmarRecepcion(this.selectedCompra.id, payload).subscribe({
      next: () => {
        // Actualizar precios globales en el catálogo farmacéutico
        this.actualizarPreciosGlobalesCatalogo();

        const numDoc = this.selectedCompra?.numeroDocumento || '';
        this.successMessage = '✅ ¡Orden ' + numDoc + ' recepcionada exitosamente! Las existencias ingresaron al almacén FEFO y la orden se archivó en el Historial de Compras.';
        this.loading = false;
        this.cerrarConfirmarModal();
        this.selectedCompra = undefined;
        this.itemsRecepcionArray.clear();
        this.cargarCompras();
        this.setTab('compras');
      },
      error: (err) => {
        this.errorMessage = err.message || 'Error al confirmar la recepción en inventario';
        this.loading = false;
      }
    });
  }

  private actualizarPreciosGlobalesCatalogo(): void {
    this.itemsRecepcionArray.value.forEach((item: any) => {
      const barcode = item.codigoBarra;
      const costo = item.costoUnitario;
      const pvp = item.precioVenta;
      const nombre = item.nombreProducto;
      const prescription = item.prescriptionRequired === true;

      const syncOrCrear = () => {
        this.inventoryService.searchMedicines(nombre).subscribe({
          next: (meds) => {
            if (meds && meds.length > 0) {
              const m = meds[0];
              this.inventoryService.updateMedicine(m.id, {
                name: m.name,
                manufacturer: m.manufacturer,
                category: m.category,
                barcode: barcode || m.barcode,
                hsnCode: m.hsnCode,
                gstPercentage: m.gstPercentage,
                prescriptionRequired: prescription,
                purchasePrice: costo,
                sellingPrice: pvp
              }).subscribe({
                next: () => console.log('Actualizado catálogo por nombre:', nombre, 'Receta:', prescription)
              });
            } else {
              this.crearNuevoMedicamentoEnCatalogo(nombre, barcode, costo, pvp, prescription);
            }
          },
          error: () => {
            this.crearNuevoMedicamentoEnCatalogo(nombre, barcode, costo, pvp, prescription);
          }
        });
      };

      if (barcode) {
        this.inventoryService.findMedicineByBarcode(barcode).subscribe({
          next: (med) => {
            if (med && med.id) {
              this.inventoryService.updateMedicine(med.id, {
                name: med.name,
                manufacturer: med.manufacturer,
                category: med.category,
                barcode: med.barcode,
                hsnCode: med.hsnCode,
                gstPercentage: med.gstPercentage,
                prescriptionRequired: prescription,
                purchasePrice: costo,
                sellingPrice: pvp
              }).subscribe({
                next: () => console.log('Actualizado catálogo por código:', nombre, 'Receta:', prescription)
              });
            } else {
              syncOrCrear();
            }
          },
          error: () => {
            syncOrCrear();
          }
        });
      } else {
        syncOrCrear();
      }
    });
  }

  private crearNuevoMedicamentoEnCatalogo(nombre: string, barcode: string | undefined, costo: number, pvp: number, prescription: boolean): void {
    const labName = this.selectedCompra?.proveedorRazonSocial || 'Laboratorio Fabricante';
    const slug = (nombre || 'MED').substring(0, 3).toUpperCase().replace(/[^A-Z]/g, 'X');
    const hsnCode = 'MED-' + slug + '-' + Math.floor(1000 + Math.random() * 9000);
    this.inventoryService.createMedicine({
      name: nombre,
      manufacturer: labName,
      category: 'Farmacéutico',
      barcode: barcode || undefined,
      hsnCode: hsnCode,
      gstPercentage: 18.00,
      prescriptionRequired: prescription,
      purchasePrice: costo,
      sellingPrice: pvp
    }).subscribe({
      next: (created) => {
        console.log('Nuevo medicamento registrado en catálogo:', created.name, 'Con receta:', created.prescriptionRequired);
        this.cargarCatalogoMedicamentos();
      },
      error: (err) => console.warn('Error al registrar nuevo medicamento en catálogo:', err)
    });
  }

  verDetalles(c: Compra): void {
    this.selectedCompra = c;
    this.showDetalleModal = true;
  }

  cerrarDetalleModal(): void {
    this.showDetalleModal = false;
  }

  cancelar(c: Compra): void {
    if (!confirm('¿Está seguro de cancelar la compra ' + c.numeroDocumento + '?')) {
      return;
    }
    this.loading = true;
    this.compraService.cancelarCompra(c.id, 'Cancelado por usuario').subscribe({
      next: () => {
        this.successMessage = 'Compra cancelada correctamente.';
        this.cargarCompras();
      },
      error: (err) => {
        this.errorMessage = err.message || 'Error al cancelar compra';
        this.loading = false;
      }
    });
  }

  cambiarPagina(delta: number): void {
    const nueva = this.page + delta;
    if (nueva >= 0 && nueva < this.totalPages) {
      this.page = nueva;
      this.cargarCompras();
    }
  }

  getEstadoLabel(estado: string): string {
    switch (estado) {
      case 'BORRADOR': return 'Borrador';
      case 'PENDIENTE': return '1. Enviada a Proveedor';
      case 'ORDEN_ACEPTADA': return '2. Orden Aceptada';
      case 'EMPAQUETANDO': return '3. Empaquetando en Almacén';
      case 'EN_CAMINO': return '4. En Camino (Courier - 2 días)';
      case 'EN_ENTREGA': return '5. Courier en Destino';
      case 'POR_VERIFICAR': return '6. Bultos Entregados (Por Verificar)';
      case 'VERIFICANDO': return '7. Escaneando Productos';
      case 'RECIBIDA': return '8. Ingresada a Stock FEFO';
      case 'CANCELADA': return 'Cancelada';
      default: return estado;
    }
  }

  getEstadoBadgeClass(estado: string): string {
    switch (estado) {
      case 'RECIBIDA': return 'badge-success';
      case 'PENDIENTE': return 'badge-warning';
      case 'ORDEN_ACEPTADA': return 'badge-info';
      case 'EMPAQUETANDO': return 'badge-purple';
      case 'EN_CAMINO': return 'badge-primary';
      case 'EN_ENTREGA': return 'badge-orange';
      case 'POR_VERIFICAR': return 'badge-teal';
      case 'VERIFICANDO': return 'badge-cyan';
      case 'CANCELADA': return 'badge-danger';
      default: return 'badge-secondary';
    }
  }

  getStepProgress(estado: string): number {
    switch (estado) {
      case 'PENDIENTE': return 15;
      case 'ORDEN_ACEPTADA': return 30;
      case 'EMPAQUETANDO': return 45;
      case 'EN_CAMINO': return 65;
      case 'EN_ENTREGA': return 80;
      case 'POR_VERIFICAR': return 90;
      case 'VERIFICANDO': return 95;
      case 'RECIBIDA': return 100;
      default: return 5;
    }
  }


  trackingFiltro: 'TODOS' | 'EN_TRANSITO' | 'POR_VERIFICAR' | 'RECIBIDA' = 'TODOS';
  trackingSearch: string = '';

  getComprasTracking(): Compra[] {
    let list = this.compras;
    if (this.trackingFiltro === 'EN_TRANSITO') {
      list = list.filter(c => ['PENDIENTE', 'ORDEN_ACEPTADA', 'EMPAQUETANDO', 'EN_CAMINO'].includes(c.estado));
    } else if (this.trackingFiltro === 'POR_VERIFICAR') {
      list = list.filter(c => ['EN_ENTREGA', 'POR_VERIFICAR', 'VERIFICANDO'].includes(c.estado));
    } else if (this.trackingFiltro === 'RECIBIDA') {
      list = list.filter(c => c.estado === 'RECIBIDA');
    }

    if (this.trackingSearch && this.trackingSearch.trim()) {
      const q = this.trackingSearch.toLowerCase().trim();
      list = list.filter(c => 
        (c.numeroDocumento && c.numeroDocumento.toLowerCase().includes(q)) ||
        (c.proveedorRazonSocial && c.proveedorRazonSocial.toLowerCase().includes(q)) ||
        (c.proveedorRuc && c.proveedorRuc.includes(q)) ||
        (c.detalles && c.detalles.some(d => d.nombreProducto && d.nombreProducto.toLowerCase().includes(q)))
      );
    }
    return list;
  }

  getConteoEnTransito(): number {
    return this.compras.filter(c => ['PENDIENTE', 'ORDEN_ACEPTADA', 'EMPAQUETANDO', 'EN_CAMINO'].includes(c.estado)).length;
  }

  getConteoPorVerificar(): number {
    return this.compras.filter(c => ['EN_ENTREGA', 'POR_VERIFICAR', 'VERIFICANDO'].includes(c.estado)).length;
  }

  getConteoRecibidas(): number {
    return this.compras.filter(c => c.estado === 'RECIBIDA').length;
  }

  getGuiaRemisionMock(c: Compra): string {
    const num = (c.id * 18742) % 900000 + 100000;
    return 'GR-OLVA-' + num;
  }

  getSiguienteEstadoNombre(estado: string): string {
    switch (estado) {
      case 'PENDIENTE': return '2. Aceptar Orden en Laboratorio';
      case 'ORDEN_ACEPTADA': return '3. Iniciar Empaque';
      case 'EMPAQUETANDO': return '4. Despachar con Olva Courier';
      case 'EN_CAMINO': return '5. Courier en Destino (Botica)';
      case 'EN_ENTREGA': return '6. Entregar Bultos para Escaneo';
      default: return 'Avanzar Etapa';
    }
  }

  setTrackingFiltro(filtro: 'TODOS' | 'EN_TRANSITO' | 'POR_VERIFICAR' | 'RECIBIDA'): void {
    this.trackingFiltro = filtro;
  }


  medicamentosCatalogo: any[] = [];

  
  // ==============================================================================
  // GESTIÓN MULTI-LABORATORIO Y CONTROL INTELIGENTE DE CAMBIO DE PROVEEDOR
  // ==============================================================================
  modoCompra: 'INDIVIDUAL' | 'MULTI_LABORATORIO' = 'INDIVIDUAL';
  mostrarAlertaCambioLab: boolean = false;
  laboratorioAnteriorId: number | null = null;
  laboratorioNuevoPendienteId: number | null = null;
  resumenMultiEmision: any[] | null = null;

  setModoCompra(modo: 'INDIVIDUAL' | 'MULTI_LABORATORIO'): void {
    this.modoCompra = modo;
  }

  getProveedorNombre(id: number | null): string {
    if (!id) return 'Laboratorio';
    const prov = this.proveedores.find(p => p.id === id);
    return prov ? (prov.nombreComercial || prov.razonSocial) : ('Laboratorio #' + id);
  }

  onProveedorSelectChange(event: any): void {
    const nuevoId = Number(event.target.value);
    const actualId = this.laboratorioAnteriorId || this.compraForm.get('proveedorId')?.value;

    if (this.modoCompra === 'INDIVIDUAL' && this.detallesFormArray.length > 0 && actualId && actualId !== nuevoId) {
      // Interceptar cambio para no perder/mezclar productos de otro laboratorio
      this.laboratorioAnteriorId = actualId;
      this.laboratorioNuevoPendienteId = nuevoId;
      // Revertir temporalmente en el form hasta que el usuario decida en el modal
      this.compraForm.patchValue({ proveedorId: actualId }, { emitEvent: false });
      this.mostrarAlertaCambioLab = true;
    } else {
      this.compraForm.patchValue({ proveedorId: nuevoId });
      this.laboratorioAnteriorId = nuevoId;
    }
  }

  confirmarCambioLabDividir(): void {
    // Guarda la orden actual para el laboratorio anterior y abre una nueva limpia para el nuevo laboratorio
    this.mostrarAlertaCambioLab = false;
    const labPrevId = this.laboratorioAnteriorId;
    const labNuevoId = this.laboratorioNuevoPendienteId;

    this.compraForm.patchValue({ proveedorId: labPrevId });
    this.guardarCompra();

    // Inicia nueva orden con el nuevo laboratorio
    setTimeout(() => {
      this.abrirNuevaCompra();
      if (labNuevoId) {
        this.compraForm.patchValue({ proveedorId: labNuevoId });
        this.laboratorioAnteriorId = labNuevoId;
        this.recomendarProductosLaboratorio();
      }
      this.successMessage = '✅ Orden anterior enviada al laboratorio. Ahora configurando nueva orden para ' + this.getProveedorNombre(labNuevoId) + '.';
    }, 600);
  }

  confirmarCambioLabLimpiar(): void {
    this.mostrarAlertaCambioLab = false;
    if (this.laboratorioNuevoPendienteId) {
      this.compraForm.patchValue({ proveedorId: this.laboratorioNuevoPendienteId });
      this.laboratorioAnteriorId = this.laboratorioNuevoPendienteId;
      this.detallesFormArray.clear();
      this.recomendarProductosLaboratorio();
    }
  }

  cancelarCambioLab(): void {
    this.mostrarAlertaCambioLab = false;
    if (this.laboratorioAnteriorId) {
      this.compraForm.patchValue({ proveedorId: this.laboratorioAnteriorId });
    }
  }

  getGruposPorLaboratorio(): any[] {
    const gruposMap = new Map<number, any>();
    const detalles = this.detallesFormArray.value || [];

    detalles.forEach((d: any, idx: number) => {
      const pId = Number(d.proveedorId) || Number(this.compraForm.get('proveedorId')?.value) || (this.proveedores[0]?.id || 1);
      if (!gruposMap.has(pId)) {
        const prov = this.proveedores.find(p => p.id === pId);
        gruposMap.set(pId, {
          proveedorId: pId,
          proveedorNombre: prov ? (prov.nombreComercial || prov.razonSocial) : ('Laboratorio #' + pId),
          proveedorRuc: prov?.ruc || '20100000000',
          docSuffix: String(100000 + pId * 1111).slice(0, 6),
          items: [],
          subtotal: 0
        });
      }
      const g = gruposMap.get(pId);
      g.items.push(d);
      g.subtotal += ((Number(d.cantidadComprada) || 1) * (Number(d.costoUnitario) || 0));
    });

    const list = Array.from(gruposMap.values());
    list.forEach(g => {
      g.nombresResumen = g.items.map((it: any) => it.nombreProducto || 'Medicamento').slice(0, 3).join(', ') + (g.items.length > 3 ? '...' : '');
    });
    return list;
  }

  getTotalGeneral(): number {
    const detalles = this.detallesFormArray.value || [];
    return detalles.reduce((acc: number, d: any) => acc + ((Number(d.cantidadComprada) || 1) * (Number(d.costoUnitario) || 0)), 0);
  }

  guardarComprasMultiples(): void {
    const grupos = this.getGruposPorLaboratorio();
    if (grupos.length === 0) {
      this.errorMessage = 'Debe incluir al menos un producto para emitir las órdenes.';
      return;
    }

    this.loading = true;
    this.errorMessage = '';
    this.resumenMultiEmision = [];

    const baseDocNum = Math.floor(100000 + Math.random() * 800000);
    const formVal = this.compraForm.value;
    let completados = 0;
    const totalGrupos = grupos.length;

    grupos.forEach((grupo, idx) => {
      const numDoc = 'F001-' + (baseDocNum + idx);
      const itemsPayload = grupo.items.map((d: any) => ({
        productoId: Number(d.productoId) || Math.floor(100 + Math.random() * 900),
        nombreProducto: (d.nombreProducto || '').trim(),
        cantidad: Number(d.cantidadComprada) || 1,
        cantidadComprada: Number(d.cantidadComprada) || 1,
        costoUnitario: Number(d.costoUnitario) || 1.0,
        precioVenta: Number(d.precioVenta) || 2.0,
        descuento: Number(d.descuento) || 0,
        loteSugerido: d.loteSugerido || ('LOT-' + (new Date().getFullYear() + 1) + '-' + Math.floor(100 + Math.random() * 900)),
        fechaVencimiento: d.fechaVencimiento || new Date(Date.now() + 365*24*60*60*1000*2).toISOString().split('T')[0],
        codigoBarra: (d.codigoBarra || '').trim()
      }));

      const payload = {
        proveedorId: grupo.proveedorId,
        tipoDocumento: 'FACTURA',
        numeroDocumento: numDoc,
        fechaEmision: formVal.fechaEmision || new Date().toISOString().split('T')[0],
        observaciones: 'Orden consolidada multi-laboratorio para ' + grupo.proveedorNombre,
        usuarioRegistro: this.authService.getCurrentUser()?.username || 'admin',
        items: itemsPayload,
        detalles: itemsPayload
      };

      this.compraService.crearCompra(payload as any).subscribe({
        next: (nueva) => {
          completados++;
          this.resumenMultiEmision?.push({
            numeroDocumento: nueva.numeroDocumento || numDoc,
            proveedorRazonSocial: grupo.proveedorNombre,
            total: grupo.subtotal,
            totalItems: grupo.items.length,
            guiaRemision: 'GR-001-' + Math.floor(100000 + Math.random() * 900000)
          });

          if (completados === totalGrupos) {
            this.loading = false;
            this.cerrarNuevaModal();
            this.cargarCompras();
          }
        },
        error: (err) => {
          completados++;
          console.error('Error al emitir orden consolidada:', err);
          this.errorMessage = 'Error al emitir orden para ' + grupo.proveedorNombre + ': ' + (err.error?.message || err.message || 'Error del servidor');
          if (completados === totalGrupos) {
            this.loading = false;
            this.cargarCompras();
          }
        }
      });
    });
  }

  cerrarResumenMulti(): void {
    this.resumenMultiEmision = null;
  }

  irATrackingDesdeMulti(): void {
    this.resumenMultiEmision = null;
    this.activeTab = 'tracking';
    this.router.navigate(['/purchases/tracking']);
  }

  cargarCatalogoMedicamentos(): void {
    this.inventoryService.getAllMedicines().subscribe({
      next: (meds) => {
        this.medicamentosCatalogo = meds || [];
        this.sincronizarRecetaConCatalogo();
      },
      error: () => {
        this.medicamentosCatalogo = [
          { id: 1, name: 'Paracetamol 500 mg', manufacturer: 'Portugal', purchasePrice: 2.00, sellingPrice: 5.00, prescriptionRequired: false },
          { id: 2, name: 'Amoxicilina 500 mg', manufacturer: 'Laboratorios Bagó', purchasePrice: 8.00, sellingPrice: 15.50, prescriptionRequired: true },
          { id: 3, name: 'Ibuprofeno 400 mg', manufacturer: 'Genfar', purchasePrice: 3.50, sellingPrice: 8.00, prescriptionRequired: false }
        ];
        this.sincronizarRecetaConCatalogo();
      }
    });
  }

  private sincronizarRecetaConCatalogo(): void {
    if (!this.itemsRecepcionArray || this.itemsRecepcionArray.length === 0) return;
    this.itemsRecepcionArray.controls.forEach(ctrl => {
      const prodId = ctrl.get('productoId')?.value;
      const barcode = ctrl.get('codigoBarra')?.value;
      const nombre = ctrl.get('nombreProducto')?.value;
      const match = (this.medicamentosCatalogo || []).find(m =>
        (prodId && m.id === prodId) ||
        (barcode && m.barcode === barcode) ||
        (nombre && m.name && m.name.toLowerCase().trim() === nombre.toLowerCase().trim())
      );
      if (match && match.prescriptionRequired !== undefined) {
        ctrl.patchValue({ prescriptionRequired: !!match.prescriptionRequired });
      }
    });
  }

  onSeleccionarMedicamentoCatalogo(index: number, event: any): void {
    const medId = Number(event.target.value);
    if (!medId) return;
    const med = this.medicamentosCatalogo.find(m => m.id === medId);
    if (med) {
      const row = this.detallesFormArray.at(index);
      let provId = this.compraForm.get('proveedorId')?.value;
      if (med.manufacturer && this.proveedores.length > 0) {
        const mfg = med.manufacturer.toLowerCase();
        const prov = this.proveedores.find(p => 
          p.razonSocial.toLowerCase().includes(mfg) ||
          (p.nombreComercial && p.nombreComercial.toLowerCase().includes(mfg)) ||
          (mfg.includes('bagó') && p.razonSocial.toLowerCase().includes('bago')) ||
          (mfg.includes('portugal') && p.razonSocial.toLowerCase().includes('portugal')) ||
          (mfg.includes('genfar') && p.razonSocial.toLowerCase().includes('genfar')) ||
          (mfg.includes('medifarma') && p.razonSocial.toLowerCase().includes('medifarma')) ||
          (mfg.includes('ac farma') && p.razonSocial.toLowerCase().includes('ac farma')) ||
          (mfg.includes('roemmers') && p.razonSocial.toLowerCase().includes('roemmers'))
        );
        if (prov) {
          provId = prov.id;
          if (this.modoCompra === 'INDIVIDUAL' && this.detallesFormArray.length === 1) {
            this.compraForm.patchValue({ proveedorId: prov.id });
            this.laboratorioAnteriorId = prov.id;
          }
        }
      }

      row.patchValue({
        productoId: med.id,
        nombreProducto: med.name,
        codigoBarra: med.barcode || '',
        costoUnitario: med.purchasePrice || 2.50,
        precioVenta: med.sellingPrice || 5.00,
        proveedorId: provId,
        prescriptionRequired: !!med.prescriptionRequired
      });
    }
  }

  recomendarProductosLaboratorio(): void {
    const provId = this.compraForm.get('proveedorId')?.value;
    const prov = this.proveedores.find(p => p.id === provId);
    const labName = prov ? (prov.nombreComercial || prov.razonSocial).toLowerCase() : '';

    const productosLab = this.medicamentosCatalogo.filter(m => 
      m.manufacturer && labName && (
        m.manufacturer.toLowerCase().includes(labName) ||
        labName.includes(m.manufacturer.toLowerCase()) ||
        (m.manufacturer.toLowerCase().includes('bagó') && labName.includes('bago')) ||
        (m.manufacturer.toLowerCase().includes('portugal') && labName.includes('portugal')) ||
        (m.manufacturer.toLowerCase().includes('genfar') && labName.includes('genfar'))
      )
    );

    const items = productosLab.length > 0 ? productosLab : this.medicamentosCatalogo;

    if (items.length > 0) {
      this.detallesFormArray.clear();
      items.forEach((med, idx) => {
        this.agregarDetalle(
          med.id || (idx + 1),
          med.name,
          med.barcode || '',
          med.purchasePrice || 2.50,
          med.sellingPrice || 5.00,
          100
        );
      });
      this.successMessage = '💡 Se cargaron ' + items.length + ' medicamentos sugeridos para ' + (prov ? prov.razonSocial : 'este laboratorio') + '.';
    } else {
      this.successMessage = 'No se encontraron medicamentos específicos registrados para este laboratorio. Puedes escribir libremente los productos a solicitar.';
    }
  }

  cambiarLaboratorioParaNuevaOrden(): void {
    const provActual = this.compraForm.get('proveedorId')?.value;
    const otrosProveedores = this.proveedores.filter(p => p.id !== provActual);
    if (otrosProveedores.length > 0) {
      const siguiente = otrosProveedores[0];
      this.abrirNuevaCompra();
      this.compraForm.patchValue({ proveedorId: siguiente.id });
      this.recomendarProductosLaboratorio();
    } else {
      this.abrirNuevaCompra();
    }
  }

  getComprasActivas(): Compra[] {
    return this.compras.filter(c => c.estado !== 'RECIBIDA' && c.estado !== 'CANCELADA');
  }
}
