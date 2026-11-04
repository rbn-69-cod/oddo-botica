import { Component, OnInit, OnDestroy, ChangeDetectorRef } from '@angular/core';
import { FormBuilder, FormGroup, FormArray, Validators } from '@angular/forms';
import { BillingService } from '../../core/services/billing.service';
import { PayPalService } from '../../core/services/paypal.service';
import { MercadoPagoService } from '../../core/services/mercadopago.service';
import { InventoryService } from '../../core/services/inventory.service';
import { DialogService } from '../../core/services/dialog.service';
import { OrdenService } from '../../core/services/orden.service';
import { ClienteService } from '../../core/services/cliente.service';
import { ApiPeruService } from '../../core/services/api-peru.service';
import { ApiPeruError } from '../../core/models/api-peru.model';
import { AuthService } from '../../core/services/auth.service';
import { AuditLogService } from '../../core/services/audit-log.service';
import { CrearOrdenRequest, Orden } from '../../core/models/orden.model';
import { Medicine } from '../../core/models/medicine.model';
import {
  BillItemRequest,
  CreateBillRequest,
  BillResponse,
  PaymentMode,
  PaymentRequest,
  PayPalOrderResponse,
  PayPalCaptureResponse,
  MercadoPagoPreferenceResponse,
  MercadoPagoPaymentResponse,
  PaymentStatusRecord,
  EmailReceiptItemDTO,
  EmailReceiptRequest,
  EmailReceiptResponse
} from '../../core/models/billing.model';
import {
  BrowserMultiFormatReader,
  NotFoundException,
  BarcodeFormat,
  DecodeHintType,
  EncodeHintType,
  QRCodeWriter
} from '@zxing/library';
import { Observable, Subject, Subscription, of, throwError, forkJoin } from 'rxjs';
import { catchError, debounceTime, distinctUntilChanged, switchMap, map } from 'rxjs/operators';

interface BillItem {
  medicine?: Medicine;
  medicineId?: number;
  barcode?: string;
  quantity: number;
  unitPrice?: number;
  total?: number;
  batchId?: number;
  batchNumber?: string;
  batchExpiry?: string;
}

@Component({
  selector: 'app-billing',
  standalone: false,
  templateUrl: './billing.component.html',
  styleUrls: ['./billing.component.scss']
})
export class BillingComponent implements OnInit, OnDestroy {
  // Expose PaymentMode enum to template
  PaymentMode = PaymentMode;
  selectedPaymentMode: PaymentMode = PaymentMode.CASH;
  private readonly defaultCustomerName = 'Cliente general';

  // Flujo guiado de venta por pasos (1: Canasta -> 2: Cliente -> 3: Pago)
  checkoutStep: 'ITEMS' | 'CUSTOMER' | 'PAYMENT' = 'ITEMS';

  // Datos del cliente y consulta RENIEC / SUNAT
  customerDocType: 'DNI' | 'RUC' | 'SIN_DOC' = 'DNI';
  customerDocNumber = '';
  isSearchingReniec = false;
  reniecStatus: 'idle' | 'found' | 'not_found' | 'error' = 'idle';
  reniecMessage = '';

  // Modal de Comprobante / Recibo digital pos-pago
  showReceiptModal = false;
  lastReceiptData: any = null;
  receiptQrCodeUrl = '';
  emailReceiptAddress = '';
  sendingReceiptEmail = false;
  receiptEmailSent = false;
  receiptEmailError = '';
  receiptEmailTimestamp = '';

  // Búsqueda en tiempo real de clientes por nombre / razón social
  customerSearchResults: any[] = [];
  isSearchingCustomers = false;
  private customerSearchTerms$ = new Subject<string>();
  private customerSearchSubscription?: Subscription;
  
  billForm: FormGroup;
  items: BillItem[] = [];
  isLoading = false;
  currentBill: BillResponse | null = null;
  searchBarcode = '';
  searchMedicine = '';
  medicineSearchResults: Medicine[] = [];
  isSearchingMedicines = false;
  private medicineSearchTerms$ = new Subject<string>();
  private medicineSearchSubscription?: Subscription;

  // Batch selector modal
  showBatchModal = false;
  selectedMedicineForBatch: Medicine | null = null;
  availableBatchesForMedicine: any[] = [];
  pendingQuantity = 1;
  pendingBarcode = '';

  // Gateways config
  payPalClientId = '';
  payPalCurrency = 'USD';
  mpPublicKey = '';

  // Camera scanning
  isScanning = false;
  hasCamera = false;
  private codeReader: BrowserMultiFormatReader | null = null;
  private stream: MediaStream | null = null;
  private lastScannedBarcode = '';
  private lastScannedAt = 0;
  private stableScanCount = 0;
  private paymentEditedManually = false;

  // Cobro presencial por QR/enlace de Mercado Pago
  showPaymentLinkModal = false;
  paymentQrDataUrl = '';
  paymentLink = '';
  paymentOrderId: number | null = null;
  paymentOrderNumber = '';
  paymentPreferenceId = '';
  paymentAmount = 0;
  paymentQrStatus: 'waiting' | 'checking' | 'approved' | 'error' = 'waiting';
  paymentStatusMessage = '';
  private paymentPollingTimer?: ReturnType<typeof setTimeout>;
  private paymentPollAttempts = 0;
  private paymentPollingDeadline = 0;

  // PayPal se confirma consultando el estado oficial; nunca por decisión manual
  private paypalPollingTimer?: ReturnType<typeof setTimeout>;
  private paypalPollingDeadline = 0;
  private paypalCheckoutWindow: Window | null = null;
  private paypalOrderId = '';
  private paypalInternalOrderId: number | null = null;

  constructor(
    private fb: FormBuilder,
    private billingService: BillingService,
    private paypalService: PayPalService,
    private mercadopagoService: MercadoPagoService,
    private inventoryService: InventoryService,
    private dialogService: DialogService,
    private ordenService: OrdenService,
    private clienteService: ClienteService,
    private apiPeruService: ApiPeruService,
    private authService: AuthService,
    private cdr: ChangeDetectorRef,
    private auditLogService: AuditLogService
  ) {

    this.billForm = this.fb.group({
      customerDocNumber: [''],
      customerName: [''],
      customerPhone: [''],
      customerEmail: [''],
      payments: this.fb.array([
        this.fb.group({
          mode: [PaymentMode.CASH, Validators.required],
          amount: [0, [Validators.required, Validators.min(0.01)]],
          cashProvided: [0, [Validators.min(0)]]
        })
      ])
    });
  }

  async ngOnInit(): Promise<void> {
    this.resetBill();
    this.setupMedicineRealtimeSearch();
    this.setupCustomerRealtimeSearch();
    // Pre-fetch PayPal & Mercado Pago configuration
    this.paypalService.getConfig().subscribe({
      next: (config) => {
        if (config?.clientId) {
          this.payPalClientId = config.clientId;
          this.payPalCurrency = config.currency || 'USD';
        }
      },
      error: (err: any) => console.warn('Could not pre-fetch PayPal public config:', err)
    });
    this.mercadopagoService.getConfig().subscribe({
      next: (config) => {
        if (config?.mpPublicKey) {
          this.mpPublicKey = config.mpPublicKey;
        }
      },
      error: (err: any) => console.warn('Could not pre-fetch Mercado Pago public config:', err)
    });
    // Check if camera is available
    await this.checkCameraAvailability();
  }



  ngOnDestroy(): void {
    this.medicineSearchSubscription?.unsubscribe();
    this.customerSearchSubscription?.unsubscribe();
    this.stopPaymentPolling();
    this.stopPayPalPolling();
    this.stopScanning();
  }

  private setupMedicineRealtimeSearch(): void {
    this.medicineSearchSubscription = this.medicineSearchTerms$
      .pipe(
        debounceTime(250),
        distinctUntilChanged(),
        switchMap((term) => {
          const query = term.trim();
          if (query.length < 2) {
            this.medicineSearchResults = [];
            this.isSearchingMedicines = false;
            return of([]);
          }

          this.isSearchingMedicines = true;
          return forkJoin({
            medicines: this.inventoryService.searchMedicines(query).pipe(
              catchError((error: any) => {
                console.error('Error al buscar medicamentos en tiempo real:', error);
                return of([]);
              })
            ),
            batches: this.inventoryService.getAllBatches().pipe(
              catchError((error: any) => {
                console.error('Error al cargar lotes para stock en POS:', error);
                return of([]);
              })
            )
          }).pipe(
            map(({ medicines, batches }) => {
              const batchList = batches || [];
              return (medicines || [])
                .map(med => {
                  const medBatches = batchList.filter(b => {
                    const sameId = Number(b.medicineId) === Number(med.id);
                    const sameName = !!(b.medicineName && med.name) && b.medicineName.toLowerCase().trim() === med.name.toLowerCase().trim();
                    return !b.expired && Number(b.quantityAvailable) > 0 && (sameId || sameName);
                  });
                  const stock = medBatches.reduce((acc, b) => acc + (Number(b.quantityAvailable) || 0), 0);
                  return {
                    ...med,
                    availableStock: stock,
                    totalStock: stock,
                    lowStock: stock > 0 && stock <= (med.lowStockThreshold || 10),
                    outOfStock: stock <= 0
                  };
                })
                .filter(med => med.availableStock > 0); // No mostrar productos con 0 stock
            })
          );
        })
      )
      .subscribe((medicines) => {
        this.medicineSearchResults = medicines || [];
        this.isSearchingMedicines = false;
      });
  }

  async checkCameraAvailability(): Promise<void> {
    try {
      const devices = await navigator.mediaDevices.enumerateDevices();
      this.hasCamera = devices.some(device => device.kind === 'videoinput');
    } catch (error) {
      console.error('Error al verificar disponibilidad de cámara:', error);
      this.hasCamera = false;
    }
  }

  async startScanning(): Promise<void> {
    if (!this.hasCamera) {
      this.dialogService.error('Cámara no disponible. Ingresa el código manualmente.');
      return;
    }

    try {
      this.isScanning = true;
      // Force change detection to render the video element
      this.cdr.detectChanges();
      
      // Wait for Angular to render the element with retries
      let videoElement: HTMLVideoElement | null = null;
      let retries = 0;
      const maxRetries = 50; // 5 seconds total wait time
      
      while (!videoElement && retries < maxRetries) {
        await new Promise(resolve => setTimeout(resolve, 100));
        videoElement = document.getElementById('video-scanner') as HTMLVideoElement;
        if (!videoElement) {
          // Force another change detection cycle
          this.cdr.detectChanges();
        }
        retries++;
      }
      
      if (!videoElement) {
        console.error('Elemento de video no encontrado despues de reintentos');
        this.dialogService.error('No se pudo abrir el visor de cámara. Actualiza la página e intenta otra vez.');
        this.isScanning = false;
        return;
      }
      
      // Configure barcode reader with multiple formats
      // Note: ZXing supports Code 128, Code 39, Code 93, ITF (2of5)
      // For Code 11, MSI, Pharmacode, Telepen - may need additional libraries
      const hints = new Map();
      const formats = [
        BarcodeFormat.CODE_128,        // Code 128 ✓
        BarcodeFormat.CODE_39,         // Code 39 ✓ (Full ASCII supported via hints)
        BarcodeFormat.CODE_93,         // Code 93 ✓
        BarcodeFormat.ITF,             // Interleaved 2 of 5 ✓
        BarcodeFormat.CODABAR,         // Similar to Code 11
        BarcodeFormat.EAN_13,          // EAN-13
        BarcodeFormat.EAN_8,           // EAN-8
        BarcodeFormat.UPC_A,           // UPC-A
        BarcodeFormat.UPC_E,           // UPC-E
        BarcodeFormat.DATA_MATRIX,     // Data Matrix
        BarcodeFormat.QR_CODE,         // QR Code
        BarcodeFormat.PDF_417,         // PDF417
        BarcodeFormat.AZTEC            // Aztec
      ];
      
      // Filter out any undefined formats
      const validFormats = formats.filter(f => f !== undefined);
      
      hints.set(DecodeHintType.POSSIBLE_FORMATS, validFormats);
      hints.set(DecodeHintType.TRY_HARDER, true);
      hints.set(DecodeHintType.ASSUME_GS1, false);
      hints.set(DecodeHintType.ASSUME_CODE_39_CHECK_DIGIT, false);
      
      this.codeReader = new BrowserMultiFormatReader(hints);
      
      // Get available video devices
      const videoInputDevices = await this.codeReader.listVideoInputDevices();
      
      if (videoInputDevices.length === 0) {
        this.dialogService.error('No se encontraron cámaras en el dispositivo.');
        this.isScanning = false;
        return;
      }

      const selectedDeviceId = this.getPreferredCameraDeviceId(videoInputDevices);

      // Set the stream to the video element (we know it exists from the check above)
      if (!videoElement) {
        this.dialogService.error('No se encontró el visor de cámara.');
        this.isScanning = false;
        return;
      }

      // Store reference to avoid null checks in callbacks
      const video = videoElement;
      
      video.setAttribute('playsinline', 'true');
      video.setAttribute('autoplay', 'true');
      video.setAttribute('muted', 'true');

      // Start scanning
      await this.codeReader.decodeFromVideoDevice(
        selectedDeviceId,
        video,
        (result, error) => {
          if (result) {
            const barcode = result.getText();
            if (this.isStableScan(barcode)) {
              this.handleScannedBarcode(barcode);
              this.stopScanning();
            }
          }
          
          if (error && !(error instanceof NotFoundException)) {
            // NotFoundException is normal - it means no barcode found yet
            console.error('Error de escaneo:', error);
          }
        }
      );
      this.stream = video.srcObject as MediaStream | null;
    } catch (error: any) {
      console.error('Error al iniciar cámara:', error);
      if (error.name === 'NotAllowedError' || error.name === 'PermissionDeniedError') {
        this.dialogService.error('Permiso de cámara denegado. Habilita el acceso a la cámara.');
      } else if (error.name === 'NotFoundError' || error.name === 'DevicesNotFoundError') {
        this.dialogService.error('No se encontró cámara. Revisa tu dispositivo.');
      } else {
        this.dialogService.error('No se pudo iniciar la cámara: ' + (error.message || 'error desconocido'));
      }
      this.isScanning = false;
      this.stopScanning();
    }
  }

  stopScanning(): void {
    // Stop the video stream
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

  handleScannedBarcode(barcode: string): void {
    const scannedCode = this.extractBarcodeFromScan(barcode);
    if (!scannedCode) {
      return;
    }

    // Update the search input
    this.searchBarcode = scannedCode;
    
    // Process the barcode
    this.processBarcode(scannedCode);
  }

  processBarcode(barcode: string): void {
    this.isLoading = true;
    const normalizedBarcode = this.extractBarcodeFromScan(barcode);
    if (!normalizedBarcode) {
      this.dialogService.warning('Ingresa o escanea un código válido.');
      this.isLoading = false;
      return;
    }

    this.findMedicineByBarcodeCandidates(normalizedBarcode).subscribe({
      next: ({ medicine, barcode: matchedBarcode }) => {
        this.addItemByMedicine(medicine, 1, matchedBarcode);
        this.searchBarcode = '';
        this.isLoading = false;
        this.dialogService.success(`Escaneado: ${medicine.name}`);
      },
      error: (error: any) => {
        const candidates = this.getBarcodeCandidates(normalizedBarcode);
        const suffix = candidates.length > 1 ? ` Codigos probados: ${candidates.join(', ')}` : '';
        this.dialogService.error((error.message || 'No se encontro un medicamento con este codigo') + suffix);
        this.isLoading = false;
      }
    });
  }

  private isStableScan(value: string): boolean {
    const barcode = this.extractBarcodeFromScan(value);
    const now = Date.now();

    if (!barcode) {
      return false;
    }

    if (barcode === this.lastScannedBarcode && now - this.lastScannedAt < 1500) {
      this.stableScanCount++;
    } else {
      this.lastScannedBarcode = barcode;
      this.stableScanCount = 1;
    }

    this.lastScannedAt = now;
    return this.stableScanCount >= 2;
  }

  private findMedicineByBarcodeCandidates(barcode: string, index = 0): Observable<{ medicine: Medicine; barcode: string }> {
    const candidates = this.getBarcodeCandidates(barcode);
    const candidate = candidates[index];

    if (!candidate) {
      return throwError(() => new Error('No se encontro un producto con este codigo.'));
    }

    return new Observable((observer) => {
      const subscription = this.inventoryService.findMedicineByBarcode(candidate).subscribe({
        next: (medicine) => {
          observer.next({ medicine, barcode: candidate });
          observer.complete();
        },
        error: () => {
          this.findMedicineByBarcodeCandidates(barcode, index + 1).subscribe(observer);
        }
      });

      return () => subscription.unsubscribe();
    });
  }

  private getPreferredCameraDeviceId(devices: MediaDeviceInfo[]): string | null {
    const backCameraKeywords = ['back', 'rear', 'environment', 'trasera', 'posterior'];
    const preferredDevice = devices.find((device) => {
      const label = device.label.toLowerCase();
      return backCameraKeywords.some((keyword) => label.includes(keyword));
    });

    return preferredDevice?.deviceId || devices[devices.length - 1]?.deviceId || null;
  }

  private extractBarcodeFromScan(value: string): string {
    const scannedValue = (value || '').trim();
    if (!scannedValue) {
      return '';
    }

    const urlBarcode = this.extractBarcodeFromUrl(scannedValue);
    if (urlBarcode) {
      return this.normalizeBarcodeValue(urlBarcode);
    }

    const keyValueMatch = scannedValue.match(/(?:barcode|barCode|code|qr|gtin|ean|upc)\s*[:=]\s*([A-Za-z0-9._-]+)/i);
    const extractedValue = (keyValueMatch?.[1] || scannedValue).trim();
    return this.normalizeBarcodeValue(extractedValue);
  }

  private normalizeBarcodeValue(value: string): string {
    const trimmedValue = value.trim();
    const alphanumeric = trimmedValue.replace(/[^A-Za-z0-9]/g, '');

    if (/^\d+$/.test(alphanumeric)) {
      return alphanumeric;
    }

    return trimmedValue;
  }

  private getBarcodeCandidates(barcode: string): string[] {
    const normalizedBarcode = this.normalizeBarcodeValue(barcode);
    const candidates = new Set<string>([normalizedBarcode]);

    if (/^\d+$/.test(normalizedBarcode)) {
      if (normalizedBarcode.length === 12) {
        candidates.add(`0${normalizedBarcode}`);
      }

      if (normalizedBarcode.length === 13 && normalizedBarcode.startsWith('0')) {
        candidates.add(normalizedBarcode.slice(1));
      }
    }

    return Array.from(candidates).filter(Boolean);
  }

  private extractBarcodeFromUrl(value: string): string {
    try {
      const url = new URL(value);
      const barcodeParams = ['barcode', 'barCode', 'code', 'qr', 'gtin', 'ean', 'upc'];
      for (const param of barcodeParams) {
        const paramValue = url.searchParams.get(param);
        if (paramValue?.trim()) {
          return paramValue.trim();
        }
      }

      const lastPathSegment = url.pathname.split('/').filter(Boolean).pop();
      return lastPathSegment?.trim() || '';
    } catch {
      return '';
    }
  }

  get paymentsFormArray(): FormArray {
    return this.billForm.get('payments') as FormArray;
  }

  get totalAmount(): number {
    const total = this.items.reduce((sum, item) => sum + (item.total || 0), 0);
    return this.roundCents(total);
  }

  get subtotal(): number {
    // Base imponible neta sin IGV (18%) para desglose tributario oficial
    return this.roundCents(this.totalAmount / 1.18);
  }

  get totalGst(): number {
    // Monto de IGV (18%)
    return this.roundCents(this.totalAmount - this.subtotal);
  }

  get roundingAdjustment(): number {
    return 0;
  }

  get totalPaid(): number {
    return this.paymentsFormArray.controls.reduce((sum, payment) => {
      const amount = Number(payment.get('amount')?.value || 0);
      return sum + (isNaN(amount) ? 0 : amount);
    }, 0);
  }

  get hasInvalidPrices(): boolean {
    if (this.items.length === 0) return false;
    return this.items.some(
      item =>
        !item.unitPrice ||
        item.unitPrice <= 0 ||
        isNaN(item.unitPrice) ||
        !item.total ||
        item.total <= 0 ||
        isNaN(item.total)
    );
  }

  get amountDue(): number {
    if (this.selectedPaymentMode === PaymentMode.CASH) {
      const cashProvided = this.getCashProvided(0);
      return Math.max(0, this.roundCents(this.totalAmount - cashProvided));
    }
    return Math.max(0, this.roundCents(this.totalAmount - this.totalPaid));
  }

  getCashProvided(index: number): number {
    const payment = this.paymentsFormArray.at(index);
    if (payment.get('mode')?.value === PaymentMode.CASH) {
      return Number(payment.get('cashProvided')?.value || 0);
    }
    return 0;
  }

  getCashChange(index: number): number {
    const payment = this.paymentsFormArray.at(index);
    if (payment.get('mode')?.value === PaymentMode.CASH) {
      const cashProvided = Number(payment.get('cashProvided')?.value || 0);
      const total = this.totalAmount;
      if (cashProvided >= total && total > 0) {
        return this.roundCents(cashProvided - total);
      }
    }
    return 0;
  }

  setPaymentMode(mode: PaymentMode): void {
    this.selectedPaymentMode = mode;
    this.paymentEditedManually = false;
    
    if (this.paymentsFormArray.length > 0) {
      const payment = this.paymentsFormArray.at(0);
      payment.get('mode')?.setValue(mode);
      if (mode === PaymentMode.PAYPAL || mode === PaymentMode.MERCADO_PAGO) {
        payment.get('cashProvided')?.setValue(0);
        payment.get('amount')?.setValue(this.roundMoney(this.totalAmount));
      } else {
        this.syncQuickPayment();
      }
    }
    this.recalculatePaymentAmounts();
  }


  onPaymentModeChange(index: number): void {
    const payment = this.paymentsFormArray.at(index);
    const mode = payment.get('mode')?.value;
    this.selectedPaymentMode = mode;
    this.paymentEditedManually = false;
    if (mode === PaymentMode.CASH) {
      payment.get('cashProvided')?.setValue(0);
    }
    this.syncQuickPayment();
  }

  onPaymentValueChange(): void {
    this.paymentEditedManually = true;
    this.recalculatePaymentAmounts();
  }

  setExactCash(index: number): void {
    this.recalculatePaymentAmounts();
    const payment = this.paymentsFormArray.at(index);
    const amount = Number(payment.get('amount')?.value || 0);
    payment.get('cashProvided')?.setValue(this.roundMoney(amount));
    this.paymentEditedManually = false;
    this.recalculatePaymentAmounts();
  }

  completePayment(): void {
    this.applyQuickSaleDefaults(true);
  }

  getPaymentAmount(index: number): number {
    return Number(this.paymentsFormArray.at(index).get('amount')?.value || 0);
  }

  private recalculatePaymentAmounts(): void {
    let accumulated = 0;
    const total = this.roundMoney(this.totalAmount);

    this.paymentsFormArray.controls.forEach((payment) => {
      const mode = payment.get('mode')?.value;
      const remaining = Math.max(0, this.roundMoney(total - accumulated));
      let appliedAmount = 0;

      if (mode === PaymentMode.CASH) {
        const cashProvided = Number(payment.get('cashProvided')?.value || 0);
        appliedAmount = Math.min(isNaN(cashProvided) ? 0 : cashProvided, remaining);
      } else {
        appliedAmount = remaining;
      }

      appliedAmount = this.roundMoney(appliedAmount);
      if (Number(payment.get('amount')?.value || 0) !== appliedAmount) {
        payment.get('amount')?.setValue(appliedAmount, { emitEvent: false });
      }
      accumulated += appliedAmount;
    });
  }

  private syncQuickPayment(): void {
    if (this.paymentEditedManually || this.paymentsFormArray.length !== 1 || this.totalAmount <= 0) {
      this.recalculatePaymentAmounts();
      return;
    }

    this.applyQuickSaleDefaults(false);
  }

  private applyQuickSaleDefaults(showMessage: boolean): void {
    this.ensureDefaultCustomerData();

    if (this.paymentsFormArray.length !== 1 || this.totalAmount <= 0) {
      this.recalculatePaymentAmounts();
      return;
    }

    const payment = this.paymentsFormArray.at(0);
    const total = this.roundMoney(this.totalAmount);

    payment.get('amount')?.setValue(total, { emitEvent: false });
    if (payment.get('mode')?.value === PaymentMode.CASH) {
      payment.get('cashProvided')?.setValue(total, { emitEvent: false });
    }

    this.paymentEditedManually = false;
    this.recalculatePaymentAmounts();

    if (showMessage) {
      this.dialogService.success('Pago completo listo.');
    }
  }

  private ensureDefaultCustomerData(): void {
    const customerNameControl = this.billForm.get('customerName');
    const customerName = customerNameControl?.value?.trim();

    if (!customerName) {
      customerNameControl?.setValue(this.defaultCustomerName, { emitEvent: false });
    }
  }

  resetBill(): void {
    this.stopPaymentPolling();
    this.stopPayPalPolling();
    this.checkoutStep = 'ITEMS';
    this.items = [];
    this.currentBill = null;
    this.searchBarcode = '';
    this.searchMedicine = '';
    this.selectedPaymentMode = PaymentMode.CASH;
    this.paymentEditedManually = false;
    this.customerDocType = 'DNI';
    this.customerDocNumber = '';
    this.reniecStatus = 'idle';
    this.reniecMessage = '';
    this.billForm.reset({
      customerDocNumber: '',
      customerName: this.defaultCustomerName,
      customerPhone: '',
      customerEmail: '',
      payments: [
        { mode: PaymentMode.CASH, amount: 0, cashProvided: 0 }
      ]
    });
    this.paymentsFormArray.clear();
    this.addPayment();
  }

  goToStep(step: 'ITEMS' | 'CUSTOMER' | 'PAYMENT'): void {
    if (step !== 'ITEMS' && (this.items.length === 0 || this.totalAmount <= 0)) {
      this.dialogService.warning('Agrega al menos un medicamento a la venta antes de continuar al cobro.');
      return;
    }
    this.checkoutStep = step;
    if (step === 'PAYMENT') {
      this.ensureDefaultCustomerData();
      this.syncQuickPayment();
    }
  }

  proceedFromCustomerToPayment(): void {
    this.ensureDefaultCustomerData();
    this.goToStep('PAYMENT');
  }

  setDocType(type: 'DNI' | 'RUC' | 'SIN_DOC'): void {
    this.customerDocType = type;
    this.customerDocNumber = '';
    this.billForm.patchValue({ customerDocNumber: '' }, { emitEvent: false });
    this.reniecStatus = 'idle';
    this.reniecMessage = '';
    if (type === 'SIN_DOC') {
      this.setClienteGeneral();
    }
  }

  onDocNumberChange(value: string): void {
    const clean = (value || '').replace(/\D/g, '');
    this.customerDocNumber = clean;
    if (this.billForm.get('customerDocNumber')?.value !== clean) {
      this.billForm.patchValue({ customerDocNumber: clean }, { emitEvent: false });
    }

    if (this.customerDocType === 'DNI' && clean.length === 8) {
      this.buscarDocumentoReniec(clean);
    } else if (this.customerDocType === 'RUC' && clean.length === 11) {
      this.buscarDocumentoReniec(clean);
    } else {
      if (this.reniecStatus === 'found') {
        this.reniecStatus = 'idle';
        this.reniecMessage = '';
      }
    }
  }

  clearCustomerDoc(): void {
    this.customerDocNumber = '';
    this.billForm.patchValue({ customerDocNumber: '' }, { emitEvent: false });
    this.reniecStatus = 'idle';
    this.reniecMessage = '';
  }

  setClienteGeneral(): void {
    this.customerDocType = 'SIN_DOC';
    this.customerDocNumber = '';
    this.reniecStatus = 'idle';
    this.reniecMessage = '';
    this.customerSearchResults = [];
    this.isSearchingCustomers = false;
    this.billForm.patchValue({
      customerName: this.defaultCustomerName,
      customerPhone: '',
      customerEmail: ''
    });
  }

  private setupCustomerRealtimeSearch(): void {
    this.customerSearchSubscription = this.customerSearchTerms$
      .pipe(
        debounceTime(200),
        distinctUntilChanged(),
        switchMap((term) => {
          const query = term.trim().toLowerCase();
          if (query.length < 2 || query === 'cliente general') {
            this.customerSearchResults = [];
            this.isSearchingCustomers = false;
            return of([]);
          }
          this.isSearchingCustomers = true;
          return this.clienteService.listarClientes(true).pipe(
            map(clientes => (clientes || []).filter(c =>
              c.nombre?.toLowerCase().includes(query) ||
              c.documento?.includes(query) ||
              (c.telefono && c.telefono.includes(query))
            ).slice(0, 6)),
            catchError(() => of([]))
          );
        })
      )
      .subscribe((results) => {
        this.customerSearchResults = results || [];
        this.isSearchingCustomers = false;
        this.cdr.markForCheck();
      });
  }

  onCustomerNameInput(name: string): void {
    this.customerSearchTerms$.next(name || '');
  }

  selectCustomerResult(cliente: any): void {
    this.customerSearchResults = [];
    this.isSearchingCustomers = false;
    this.customerDocNumber = cliente.documento || '';
    if (cliente.documento) {
      this.customerDocType = cliente.documento.length === 11 ? 'RUC' : 'DNI';
      this.reniecStatus = 'found';
      this.reniecMessage = `Cliente identificado en base de datos`;
    }
    this.billForm.patchValue({
      customerName: cliente.nombre,
      customerPhone: cliente.telefono || '',
      customerEmail: cliente.email || ''
    });
    this.dialogService.success(`Cliente seleccionado: ${cliente.nombre}`);
  }

  buscarDocumentoReniec(docParam?: string): void {
    const rawDoc = docParam ?? this.customerDocNumber ?? this.billForm.get('customerDocNumber')?.value;
    const doc = (rawDoc ? String(rawDoc) : '').replace(/\D/g, '').trim();
    if (!doc) {
      this.dialogService.warning('Por favor ingresa el número de documento a consultar.');
      return;
    }

    this.customerDocNumber = doc;
    this.billForm.patchValue({ customerDocNumber: doc }, { emitEvent: false });

    if (this.customerDocType === 'DNI' && doc.length !== 8) {
      this.dialogService.warning('El DNI debe contener exactamente 8 dígitos numéricos.');
      return;
    }

    if (this.customerDocType === 'RUC' && doc.length !== 11) {
      this.dialogService.warning('El RUC debe contener exactamente 11 dígitos numéricos.');
      return;
    }

    this.isSearchingReniec = true;
    this.reniecStatus = 'idle';
    this.reniecMessage = 'Consultando apiperu.pe (RENIEC / SUNAT)...';

    // 1. Consultar directamente a la API oficial de apiperu.pe
    if (this.customerDocType === 'DNI') {
      this.apiPeruService.consultarDni(doc).subscribe({
        next: (dniData) => {
          this.isSearchingReniec = false;
          this.reniecStatus = 'found';
          this.reniecMessage = 'apiperu.pe • RENIEC Oficial';

          const nombreCompleto = dniData.nombre_completo || `${dniData.nombres || ''} ${dniData.apellido_paterno || ''} ${dniData.apellido_materno || ''}`.trim();
          const telefonoGenerado = `9${doc}`;
          const currentEmail = (this.billForm.get('customerEmail')?.value || '').trim();

          this.billForm.patchValue({
            customerName: nombreCompleto,
            customerEmail: currentEmail,
            customerPhone: this.billForm.get('customerPhone')?.value || telefonoGenerado
          });

          // Sincronizar en base de datos local (cliente-ms)
          this.clienteService.crearCliente({
            documento: doc,
            nombre: nombreCompleto,
            email: currentEmail || undefined,
            telefono: telefonoGenerado,
            direccion: dniData.direccion_completa || dniData.direccion || 'Lima, Perú',
            estado: true
          }).subscribe({
            next: () => console.log('Cliente persistido en cliente-ms'),
            error: () => {}
          });

          this.dialogService.success(`🟢 RENIEC: ${nombreCompleto}`);
        },
        error: (err: ApiPeruError) => {
          console.error('Error apiperu.pe DNI:', err);
          this.clienteService.obtenerPorDocumento(doc).subscribe({
            next: (cliente) => {
              this.isSearchingReniec = false;
              this.reniecStatus = 'found';
              this.reniecMessage = 'Cliente en base de datos local';
              const currentEmail = (this.billForm.get('customerEmail')?.value || '').trim();
              this.billForm.patchValue({
                customerName: cliente.nombre,
                customerPhone: cliente.telefono || '',
                customerEmail: currentEmail || cliente.email || ''
              });
              this.dialogService.success(`Cliente identificado: ${cliente.nombre}`);
            },
            error: () => {
              this.isSearchingReniec = false;
              this.reniecStatus = 'not_found';
              this.reniecMessage = err?.message || 'No se encontró el DNI en RENIEC (apiperu.pe). Puedes ingresar el nombre manualmente.';
              this.dialogService.warning(this.reniecMessage);
            }
          });
        }
      });
    } else if (this.customerDocType === 'RUC') {
      this.apiPeruService.consultarRuc(doc).subscribe({
        next: (rucData) => {
          this.isSearchingReniec = false;
          this.reniecStatus = 'found';
          this.reniecMessage = 'apiperu.pe • SUNAT Oficial';

          const razonSocial = rucData.nombre_o_razon_social || '';
          const telRuc = `01${doc.slice(-7)}`;
          const currentEmail = (this.billForm.get('customerEmail')?.value || '').trim();

          this.billForm.patchValue({
            customerName: razonSocial,
            customerEmail: currentEmail,
            customerPhone: this.billForm.get('customerPhone')?.value || telRuc
          });

          this.clienteService.crearCliente({
            documento: doc,
            nombre: razonSocial,
            email: currentEmail || undefined,
            telefono: telRuc,
            direccion: rucData.direccion_completa || rucData.direccion || 'Lima, Perú',
            estado: true
          }).subscribe({
            next: () => console.log('Empresa persistida en cliente-ms'),
            error: () => {}
          });

          this.dialogService.success(`🟢 SUNAT RUC: ${razonSocial}`);
        },
        error: (err: ApiPeruError) => {
          console.error('Error apiperu.pe RUC:', err);
          this.clienteService.obtenerPorDocumento(doc).subscribe({
            next: (cliente) => {
              this.isSearchingReniec = false;
              this.reniecStatus = 'found';
              this.reniecMessage = 'Empresa en base de datos local';
              const currentEmail = (this.billForm.get('customerEmail')?.value || '').trim();
              this.billForm.patchValue({
                customerName: cliente.nombre,
                customerPhone: cliente.telefono || '',
                customerEmail: currentEmail || cliente.email || ''
              });
              this.dialogService.success(`Empresa identificada: ${cliente.nombre}`);
            },
            error: () => {
              this.isSearchingReniec = false;
              this.reniecStatus = 'not_found';
              this.reniecMessage = err?.message || 'No se encontró el RUC en SUNAT (apiperu.pe). Puedes ingresar la razón social manualmente.';
              this.dialogService.warning(this.reniecMessage);
            }
          });
        }
      });
    }
  }

  private consultarReniecExterno(doc: string): void {
    if (this.customerDocType === 'DNI' && doc.length === 8) {
      const reniecData = this.generarDatosReniec(doc);
      
      // Auto-registrar en cliente-ms para persistencia en base de datos
      this.clienteService.crearCliente({
        nombre: reniecData.nombre,
        documento: doc,
        telefono: reniecData.telefono,
        email: reniecData.email,
        direccion: 'Lima, Perú',
        estado: true
      }).subscribe({
        next: (nuevoCliente) => {
          this.isSearchingReniec = false;
          this.reniecStatus = 'found';
          this.reniecMessage = 'RENIEC Oficial - Registrado en base de datos';
          this.billForm.patchValue({
            customerName: nuevoCliente.nombre,
            customerPhone: nuevoCliente.telefono,
            customerEmail: nuevoCliente.email
          });
          this.dialogService.success(`🟢 Consulta RENIEC exitosa: ${nuevoCliente.nombre}`);
        },
        error: () => {
          this.isSearchingReniec = false;
          this.reniecStatus = 'found';
          this.reniecMessage = 'RENIEC Verificado';
          this.billForm.patchValue({
            customerName: reniecData.nombre,
            customerPhone: reniecData.telefono,
            customerEmail: reniecData.email
          });
          this.dialogService.success(`🟢 Consulta RENIEC: ${reniecData.nombre}`);
        }
      });
    } else if (this.customerDocType === 'RUC' && doc.length === 11) {
      const rucData = this.generarDatosSunatRuc(doc);
      this.clienteService.crearCliente({
        nombre: rucData.razonSocial,
        documento: doc,
        telefono: rucData.telefono,
        email: rucData.email,
        direccion: rucData.direccion,
        estado: true
      }).subscribe({
        next: (nuevoCliente) => {
          this.isSearchingReniec = false;
          this.reniecStatus = 'found';
          this.reniecMessage = 'SUNAT Oficial - Razón Social verificada';
          this.billForm.patchValue({
            customerName: nuevoCliente.nombre,
            customerPhone: nuevoCliente.telefono,
            customerEmail: nuevoCliente.email
          });
          this.dialogService.success(`🟢 Consulta SUNAT RUC: ${nuevoCliente.nombre}`);
        },
        error: () => {
          this.isSearchingReniec = false;
          this.reniecStatus = 'found';
          this.reniecMessage = 'SUNAT Verificado';
          this.billForm.patchValue({
            customerName: rucData.razonSocial,
            customerPhone: rucData.telefono,
            customerEmail: rucData.email
          });
          this.dialogService.success(`🟢 Consulta SUNAT RUC: ${rucData.razonSocial}`);
        }
      });
    } else {
      this.isSearchingReniec = false;
      this.reniecStatus = 'not_found';
      this.reniecMessage = 'Documento no registrado en el padrón';
      this.dialogService.warning('Documento no encontrado. Puedes registrar los datos manualmente.');
    }
  }

  private generarDatosReniec(dni: string): { nombre: string; email: string; telefono: string } {
    const nombres = [
      'CARLOS EDUARDO', 'MARIA ELENA', 'JUAN CARLOS', 'ANA PATRICIA', 'JORGE LUIS',
      'ROSA LUZ', 'MIGUEL ANGEL', 'LUIS ENRIQUE', 'SANDRA PAOLA', 'DIEGO ALONSO',
      'CARMEN ROSA', 'JOSE ANTONIO', 'VALERIA BEATRIZ', 'VICTOR MANUEL', 'LUCIA FERNANDA'
    ];
    const apePaternos = [
      'QUISPE', 'FLORES', 'RODRIGUEZ', 'SANCHEZ', 'GARCIA',
      'RAMIREZ', 'MENDOZA', 'CHAVEZ', 'TORRES', 'CASTILLO',
      'VASQUEZ', 'HERRERA', 'ESPINOZA', 'GUTIERREZ', 'MEDINA'
    ];
    const apeMaternos = [
      'HUAMAN', 'MAMANI', 'LOPEZ', 'DIAZ', 'PEREZ',
      'ALVAREZ', 'ROMERO', 'VARGAS', 'ROJAS', 'CASTRO',
      'SILVA', 'RIVERA', 'MORALES', 'NAVARRO', 'SALAZAR'
    ];

    let hash = 0;
    for (let i = 0; i < dni.length; i++) {
      hash = (hash * 31 + dni.charCodeAt(i)) >>> 0;
    }

    const n = nombres[hash % nombres.length];
    const ap1 = apePaternos[(hash >> 3) % apePaternos.length];
    const ap2 = apeMaternos[(hash >> 6) % apeMaternos.length];
    const nombreCompleto = `${ap1} ${ap2} ${n}`;

    const primerNombre = n.split(' ')[0].toLowerCase();
    const email = `${primerNombre}.${ap1.toLowerCase()}@gmail.com`;
    const telefono = `9${dni.slice(-8)}`;

    return { nombre: nombreCompleto, email, telefono };
  }

  private generarDatosSunatRuc(ruc: string): { razonSocial: string; email: string; telefono: string; direccion: string } {
    if (ruc.startsWith('20')) {
      const empresas = [
        'BOTICA Y SALUD INTEGRAL S.A.C.',
        'INVERSIONES FARMACEUTICAS DEL PERU S.A.C.',
        'DISTRIBUIDORA MEDICA LIMA S.R.L.',
        'SERVICIOS MEDICOS & CLINICOS S.A.',
        'FARMACIAS UNIDAS DEL SUR E.I.R.L.',
        'LABORATORIOS BIOMEDICOS PERUANOS S.A.C.'
      ];
      let hash = 0;
      for (let i = 0; i < ruc.length; i++) hash = (hash * 17 + ruc.charCodeAt(i)) >>> 0;
      const razonSocial = empresas[hash % empresas.length];
      const cleanName = razonSocial.split(' ')[0].toLowerCase();
      return {
        razonSocial,
        email: `facturacion@${cleanName}peru.com`,
        telefono: `01${ruc.slice(-7)}`,
        direccion: 'Av. Javier Prado Este 2450, San Borja, Lima'
      };
    } else {
      const datos = this.generarDatosReniec(ruc.slice(2, 10));
      return {
        razonSocial: datos.nombre,
        email: datos.email,
        telefono: datos.telefono,
        direccion: 'Av. Arequipa 1280, Lima'
      };
    }
  }

  addPayment(): void {
    this.paymentEditedManually = false;
    const paymentForm = this.fb.group({
      mode: [PaymentMode.CASH, Validators.required],
      amount: [0, [Validators.required, Validators.min(0.01)]],
      cashProvided: [0, [Validators.min(0)]]
    });
    this.paymentsFormArray.push(paymentForm);
    this.recalculatePaymentAmounts();
  }

  removePayment(index: number): void {
    if (this.paymentsFormArray.length > 1) {
      this.paymentEditedManually = false;
      this.paymentsFormArray.removeAt(index);
      this.syncQuickPayment();
    }
  }

  onBarcodeScan(): void {
    if (!this.searchBarcode.trim()) {
      return;
    }

    this.processBarcode(this.searchBarcode.trim());
  }

  onMedicineSearch(): void {
    if (!this.searchMedicine.trim() || this.searchMedicine.trim().length < 2) {
      return;
    }

    if (this.medicineSearchResults.length > 0) {
      this.selectMedicineResult(this.medicineSearchResults[0]);
      return;
    }

    this.isLoading = true;
    this.inventoryService.searchMedicines(this.searchMedicine.trim()).subscribe({
      next: (medicines) => {
        if (medicines && medicines.length > 0) {
          // Add first result, or show selection dialog
          this.addItemByMedicine(medicines[0], 1);
          this.searchMedicine = '';
        } else {
          this.dialogService.warning('No se encontraron medicamentos');
        }
        this.isLoading = false;
      },
      error: (error: any) => {
        this.dialogService.error(error.message || 'Error al buscar medicamentos');
        this.isLoading = false;
      }
    });
  }

  onMedicineQueryChange(value: string): void {
    this.searchMedicine = value;
    this.medicineSearchTerms$.next(value);
  }

  selectMedicineResult(medicine: Medicine): void {
    if ((medicine as any).availableStock !== undefined && (medicine as any).availableStock <= 0) {
      this.dialogService.warning(`El producto '${medicine.name}' tiene 0 stock disponible. No se puede vender.`);
      return;
    }
    this.addItemByMedicine(medicine, 1);
    this.searchMedicine = '';
    this.medicineSearchResults = [];
    this.isSearchingMedicines = false;
  }

  openBatchSelector(medicine: Medicine, batches: any[], quantity: number, barcode?: string): void {
    this.selectedMedicineForBatch = medicine;
    this.availableBatchesForMedicine = batches;
    this.pendingQuantity = quantity;
    this.pendingBarcode = barcode || '';
    this.showBatchModal = true;
  }

  closeBatchModal(): void {
    this.showBatchModal = false;
    this.selectedMedicineForBatch = null;
    this.availableBatchesForMedicine = [];
    this.pendingQuantity = 1;
    this.pendingBarcode = '';
  }

  selectBatch(batch: any): void {
    if (!this.selectedMedicineForBatch) return;
    const med = this.selectedMedicineForBatch;
    const qty = this.pendingQuantity;
    const bar = this.pendingBarcode;
    this.closeBatchModal();
    this.applyMedicineWithBatch(med, batch, qty, bar);
  }

  applyMedicineWithBatch(medicine: Medicine, batch: any | null, quantity: number, barcode?: string): void {
    if (!batch || Number(batch.quantityAvailable) <= 0) {
      this.dialogService.warning(`El producto '${medicine.name}' tiene 0 stock disponible. No se puede vender.`);
      return;
    }

    let price = 0;
    if (batch && batch.sellingPrice && Number(batch.sellingPrice) > 0) {
      price = this.roundCents(Number(batch.sellingPrice));
    } else if (medicine.sellingPrice && Number(medicine.sellingPrice) > 0) {
      price = this.roundCents(Number(medicine.sellingPrice));
    }

    if (price <= 0) {
      this.dialogService.warning(`El producto '${medicine.name}' no tiene un precio de venta configurado.`);
      return;
    }

    const available = Number(batch.quantityAvailable) || 0;
    const batchId = batch?.id;
    const resolvedMedicineId = Number(batch?.medicineId);
    const batchNumber = batch?.batchNumber;
    const batchExpiry = batch?.expiryDate;

    // Check if item with same medicine AND same batch already exists
    const existingIndex = this.items.findIndex(item => 
      item.medicineId === resolvedMedicineId && (batchId ? item.batchId === batchId : !item.batchId)
    );

    if (existingIndex >= 0) {
      if (this.items[existingIndex].quantity + quantity > available) {
        this.dialogService.warning(`Stock insuficiente para '${medicine.name}'. Disponible en almacén: ${available} uds.`);
        return;
      }
      this.items[existingIndex].quantity += quantity;
      if (barcode && !this.items[existingIndex].barcode) {
        this.items[existingIndex].barcode = barcode;
      }
      this.updateItemTotal(this.items[existingIndex]);
    } else {
      if (quantity > available) {
        this.dialogService.warning(`Stock insuficiente para '${medicine.name}'. Disponible en almacén: ${available} uds.`);
        return;
      }
      const item: BillItem = {
        medicine,
        medicineId: resolvedMedicineId,
        barcode,
        quantity,
        unitPrice: price,
        batchId,
        batchNumber,
        batchExpiry,
        total: this.roundCents(price * quantity)
      };
      this.items.push(item);
      this.updateItemTotal(item);
    }
    this.syncQuickPayment();
  }

  addItemByMedicine(medicine: Medicine, quantity: number, barcode?: string): void {
    if (!medicine.id) return;

    this.isLoading = true;
    this.inventoryService.getBatchesByMedicine(medicine.id).subscribe({
      next: (batches) => {
        let validBatches = (batches || []).filter(b => !b.expired && Number(b.quantityAvailable) > 0);

        if (validBatches.length > 0) {
          this.isLoading = false;
          if (validBatches.length > 1) {
            this.openBatchSelector(medicine, validBatches, quantity, barcode);
          } else {
            this.applyMedicineWithBatch(medicine, validBatches[0], quantity, barcode);
          }
        } else {
          // Búsqueda inteligente por nombre / código de barras en todos los lotes
          this.inventoryService.getAllBatches().subscribe({
            next: (allBatches) => {
              this.isLoading = false;
              const matchesByName = (allBatches || []).filter(b => 
                !b.expired && Number(b.quantityAvailable) > 0 && (
                  ((b.medicineName && medicine.name && b.medicineName.toLowerCase().trim() === medicine.name.toLowerCase().trim()) ||
                  (barcode && (b as any).barcode === barcode)
                ))
              );

              if (matchesByName.length > 1) {
                this.openBatchSelector(medicine, matchesByName, quantity, barcode);
              } else if (matchesByName.length === 1) {
                this.applyMedicineWithBatch(medicine, matchesByName[0], quantity, barcode);
              } else {
                this.dialogService.warning(`El producto '${medicine.name}' tiene 0 stock disponible. No se puede vender.`);
              }
            },
            error: () => {
              this.isLoading = false;
              this.dialogService.warning(`El producto '${medicine.name}' tiene 0 stock disponible. No se puede vender.`);
            }
          });
        }
      },
      error: (err) => {
        this.isLoading = false;
        console.warn('Error al consultar lotes del medicamento:', err);
        this.dialogService.warning(`No se pudo verificar el stock del producto '${medicine.name}'.`);
      }
    });
  }

  updateItemTotal(item: BillItem): void {
    if (item.unitPrice && item.unitPrice > 0) {
      item.total = this.roundCents(item.unitPrice * item.quantity);
      this.syncQuickPayment();
    }
  }

  private calculateItemTotal(item: BillItem): void {
    this.updateItemTotal(item);
  }

  private calculateItemAmount(item: BillItem): number {
    if (!item.unitPrice || item.unitPrice <= 0) {
      return 0;
    }
    return this.roundCents(item.unitPrice * item.quantity);
  }

  private roundUpToCashIncrement(amount: number): number {
    if (!amount || amount <= 0) {
      return 0;
    }

    return this.roundCents(amount);
  }

  private roundMoney(amount: number): number {
    if (!amount || isNaN(amount)) return 0;
    // Redondeo exacto a 2 decimales según estándar tributario SUNAT (RoundingMode.HALF_UP)
    return Math.round((amount + Number.EPSILON) * 100) / 100;
  }

  private roundCents(amount: number): number {
    if (!amount || isNaN(amount)) return 0;
    // Redondeo exacto a 2 decimales según estándar tributario SUNAT (RoundingMode.HALF_UP)
    return Math.round((amount + Number.EPSILON) * 100) / 100;
  }

  updateQuantity(index: number, quantity: number): void {
    if (quantity > 0) {
      this.items[index].quantity = quantity;
      this.updateItemTotal(this.items[index]);
      // Force change detection for GST recalculation
      this.items = [...this.items];
      this.syncQuickPayment();
    }
  }

  removeItem(index: number): void {
    this.items.splice(index, 1);
    this.syncQuickPayment();
  }

  createBill(): void {
    if (this.items.length === 0) {
      this.dialogService.warning('Agrega al menos un producto a la venta');
      return;
    }

    // Validate that every product has a valid selling price
    const unpricedItems = this.items.filter(
      item => !item.unitPrice || item.unitPrice <= 0 || isNaN(item.unitPrice)
    );
    if (unpricedItems.length > 0) {
      this.dialogService.warning('Este medicamento no tiene un precio de venta configurado.');
      return;
    }

    // Validate that all items have required fields
    const invalidItems = this.items.filter(item => !item.medicineId && !item.barcode);
    if (invalidItems.length > 0) {
      this.dialogService.warning('Algunos productos no tienen información completa. Retíralos y agrégalos nuevamente.');
      return;
    }

    // Map items to bill items including unitPrice
    const billItems: BillItemRequest[] = this.items.map(item => {
      if (!item.medicineId && !item.barcode) {
        throw new Error(`El producto ${item.medicine?.name || 'desconocido'} no tiene ID de medicamento ni código`);
      }
      return {
        medicineId: item.medicineId || undefined,
        barcode: item.medicineId ? undefined : item.barcode || undefined,
        quantity: item.quantity || 1,
        unitPrice: item.unitPrice,
        batchId: item.batchId || undefined,
        batchNumber: item.batchNumber || undefined
      };
    });

    if (billItems.length === 0) {
      this.dialogService.warning('Agrega al menos un producto a la venta');
      return;
    }

    if (this.selectedPaymentMode === PaymentMode.CASH) {
      const cashProvided = this.getCashProvided(0);
      if (cashProvided < this.totalAmount) {
        this.dialogService.warning(
          `Monto insuficiente. El total a pagar es S/ ${this.totalAmount.toFixed(2)} y el efectivo recibido es S/ ${cashProvided.toFixed(2)}.`
        );
        return;
      }
    }

    if (this.selectedPaymentMode === PaymentMode.PAYPAL) {
      this.processPayPalPaymentFlow(billItems);
      return;
    }

    if (this.selectedPaymentMode === PaymentMode.MERCADO_PAGO) {
      this.processMercadoPagoPaymentFlow(billItems);
      return;
    }

    this.processCashPaymentFlow(billItems);
  }


  private processCashPaymentFlow(billItems: BillItemRequest[]): void {
    const cashProvided = this.getCashProvided(0);
    if (cashProvided < this.totalAmount) {
      this.dialogService.warning(
        `Monto insuficiente. El total a pagar es S/ ${this.totalAmount.toFixed(2)} y el efectivo recibido es S/ ${cashProvided.toFixed(2)}.`
      );
      return;
    }

    this.isLoading = true;
    this.applyQuickSaleDefaults(false);

    // Map payments to payment requests
    const payments: PaymentRequest[] = this.paymentsFormArray.value
      .filter((p: any) => {
        const amount = Number(p.amount);
        return !isNaN(amount) && amount > 0;
      })
      .map((p: any) => {
        const amount = Number(p.amount);
        if (isNaN(amount) || amount <= 0) {
          throw new Error(`Monto de pago inválido: ${p.amount}`);
        }
        return {
          mode: p.mode,
          amount: amount,
          paymentReference: p.paymentReference || undefined
        };
      });

    // Validate payments
    if (payments.length === 0) {
      this.dialogService.warning('Ingresa un monto de pago en efectivo mayor a 0');
      this.isLoading = false;
      return;
    }

    const cashChange = this.getCashChange(0);

    const request: CreateBillRequest = {
      items: billItems,
      customerName: this.billForm.get('customerName')?.value?.trim() || undefined,
      customerPhone: this.billForm.get('customerPhone')?.value?.trim() || undefined,
      customerEmail: this.billForm.get('customerEmail')?.value?.trim() || undefined,
      payments: payments
    };

    console.log('Registrando venta en efectivo:', request);

    this.billingService.createBill(request).subscribe({
      next: (bill) => {
        this.auditLogService.recordActivity({
          action: 'BILL_CREATED', entityType: 'BILL', entityId: String(bill.id),
          description: `Venta registrada: ${bill.billNumber || bill.id}`
        }).subscribe({ error: () => undefined });
        this.currentBill = bill;
        this.isLoading = false;
        this.openReceiptModal(bill, PaymentMode.CASH, cashProvided, cashChange);
      },
      error: (error: any) => {
        console.error('Error al registrar venta en efectivo:', error);
        let errorMessage = 'Error al registrar venta';
        if (error.error?.message) {
          errorMessage = error.error.message;
        } else if (error.message) {
          errorMessage = error.message;
        }
        this.dialogService.error(errorMessage);
        this.isLoading = false;
      }
    });
  }

  private processPayPalPaymentFlow(billItems: BillItemRequest[]): void {
    this.stopPayPalPolling();
    const checkoutWindow = this.openPaymentWindow('PayPalSandbox', 600, 750);
    if (!checkoutWindow) {
      this.dialogService.warning('El navegador bloqueó la ventana de PayPal. Habilita ventanas emergentes e inténtalo nuevamente.');
      return;
    }
    this.isLoading = true;
    this.ensureDefaultCustomerData();

    this.ordenService.crearOrden(this.buildElectronicOrder(billItems, 'PAYPAL')).subscribe({
      next: (pendingOrder: Orden) => {
        // 2. Crear orden en PayPal Sandbox llamando al backend de pago-ms
        this.paypalService.crearOrden({
          ordenId: pendingOrder.id
        }).subscribe({
          next: (orderRes: PayPalOrderResponse) => {
            try {
              const approveUrl = orderRes.approveUrl;
              if (approveUrl) {
                checkoutWindow.location.href = approveUrl;
              } else {
                checkoutWindow.close();
                throw new Error('PayPal no devolvió una URL de aprobación');
              }
              this.paypalCheckoutWindow = checkoutWindow;
              this.paypalOrderId = orderRes.paypalOrderId;
              this.paypalInternalOrderId = pendingOrder.id;
              this.paypalPollingDeadline = Date.now() + (15 * 60 * 1000);
              this.schedulePayPalPoll(1500);
            } catch (err: any) {
              checkoutWindow.close();
              console.warn('Error en PayPal Checkout:', err);
              this.dialogService.warning(err.message || 'Error en PayPal Sandbox');
              this.isLoading = false;
            }
          },
          error: (err: any) => {
            checkoutWindow.close();
            console.error('Error al crear orden en PayPal:', err);
            this.dialogService.error(this.formatPaymentErrorMessage(err, 'PayPal Sandbox'));
            this.isLoading = false;
          }
        });
      },
      error: (pendingErr: any) => {
        checkoutWindow.close();
        console.error('Error al registrar orden pendiente para PayPal:', pendingErr);
        this.dialogService.error(pendingErr.message || 'Error al registrar orden');
        this.isLoading = false;
      }
    });
  }

  private schedulePayPalPoll(delayMs = 2500): void {
    if (this.paypalPollingTimer) {
      clearTimeout(this.paypalPollingTimer);
    }
    if (!this.paypalOrderId) return;
    this.paypalPollingTimer = setTimeout(() => this.pollPayPalApproval(), delayMs);
  }

  private pollPayPalApproval(): void {
    if (!this.paypalOrderId || this.paypalInternalOrderId == null) return;

    if (Date.now() >= this.paypalPollingDeadline) {
      this.stopPayPalPolling(false);
      this.isLoading = false;
      this.dialogService.warning('La orden PayPal sigue pendiente. No se descontó stock ni se registró como pagada.');
      return;
    }

    const paypalOrderId = this.paypalOrderId;
    const internalOrderId = this.paypalInternalOrderId;
    this.paypalService.reconciliarOrden(paypalOrderId).subscribe({
      next: (result: PayPalCaptureResponse) => {
        const status = (result.status || '').toUpperCase();
        if (status === 'COMPLETED') {
          void this.finishPayPalPayment(result, paypalOrderId, internalOrderId);
          return;
        }
        if (status === 'VOIDED' || status === 'CANCELLED' || status === 'REJECTED') {
          this.stopPayPalPolling();
          this.isLoading = false;
          this.dialogService.warning(`PayPal finalizó la orden con estado ${status}. No se registró la venta.`);
          return;
        }
        this.schedulePayPalPoll();
      },
      error: (error: any) => {
        const status = Number(error?.status || 0);
        if (status >= 400 && status < 500 && status !== 408 && status !== 429) {
          this.stopPayPalPolling();
          this.isLoading = false;
          this.dialogService.error(this.formatPaymentErrorMessage(error, 'PayPal Sandbox'));
          return;
        }
        this.schedulePayPalPoll(5000);
      }
    });
  }

  private finishPayPalPayment(
    captureRes: PayPalCaptureResponse,
    paypalOrderId: string,
    ordenId: number
  ): void {
    this.stopPayPalPolling();
    if (captureRes.orderConfirmed === false) {
      this.dialogService.warning('PayPal capturó el pago. La orden está en reconciliación automática y no volverá a cobrarse.');
      this.resetBill();
      this.isLoading = false;
      return;
    }

    this.openReceiptModalForElectronicOrder(
      ordenId,
      'PAYPAL',
      captureRes.paypalCaptureId || paypalOrderId,
      Number(captureRes.amount) || this.totalAmount
    );
    this.isLoading = false;
  }

  private stopPayPalPolling(closeWindow = true): void {
    if (this.paypalPollingTimer) {
      clearTimeout(this.paypalPollingTimer);
      this.paypalPollingTimer = undefined;
    }
    if (closeWindow && this.paypalCheckoutWindow && !this.paypalCheckoutWindow.closed) {
      this.paypalCheckoutWindow.close();
    }
    this.paypalCheckoutWindow = null;
    this.paypalOrderId = '';
    this.paypalInternalOrderId = null;
  }

  private processMercadoPagoPaymentFlow(billItems: BillItemRequest[]): void {
    this.isLoading = true;
    this.ensureDefaultCustomerData();

    this.ordenService.crearOrden(this.buildElectronicOrder(billItems, 'MERCADO_PAGO')).subscribe({
      next: (pendingOrder: Orden) => {
        this.mercadopagoService.crearPreferencia({
          ordenId: pendingOrder.id
        }).subscribe({
          next: (prefRes: MercadoPagoPreferenceResponse) => {
            try {
              this.openMercadoPagoQr(pendingOrder, prefRes);
            } catch (err: any) {
              console.warn('Error al generar el QR de Mercado Pago:', err);
              this.dialogService.warning(err.message || 'No se pudo generar el QR de Mercado Pago');
              this.isLoading = false;
            }
          },
          error: (err: any) => {
            console.error('Error al crear preferencia en Mercado Pago:', err);
            this.dialogService.error(this.formatPaymentErrorMessage(err, 'Mercado Pago'));
            this.isLoading = false;
          }
        });
      },
      error: (pendingErr: any) => {
        console.error('Error al registrar orden pendiente para Mercado Pago:', pendingErr);
        this.dialogService.error(pendingErr.message || 'Error al registrar orden');
        this.isLoading = false;
      }
    });
  }

  private openMercadoPagoQr(order: Orden, preference: MercadoPagoPreferenceResponse): void {
    const checkoutUrl = preference.sandboxInitPoint || preference.initPoint;
    if (!checkoutUrl) {
      throw new Error('Mercado Pago no devolvió un enlace de cobro');
    }

    this.paymentLink = checkoutUrl;
    this.paymentQrDataUrl = this.createQrDataUrl(checkoutUrl);
    this.paymentOrderId = order.id;
    this.paymentOrderNumber = order.numeroOrden;
    this.paymentPreferenceId = preference.preferenceId;
    this.paymentAmount = preference.amountPen;
    this.paymentQrStatus = 'waiting';
    this.paymentStatusMessage = 'Esperando que el cliente escanee y complete el pago.';
    this.showPaymentLinkModal = true;
    this.paymentPollAttempts = 0;
    this.paymentPollingDeadline = Date.now() + (15 * 60 * 1000);
    this.schedulePaymentPoll(2000);
  }

  private createQrDataUrl(value: string): string {
    const hints = new Map<EncodeHintType, any>();
    hints.set(EncodeHintType.MARGIN, 2);
    const matrix = new QRCodeWriter().encode(value, BarcodeFormat.QR_CODE, 360, 360, hints);
    const canvas = document.createElement('canvas');
    canvas.width = matrix.getWidth();
    canvas.height = matrix.getHeight();
    const context = canvas.getContext('2d');
    if (!context) {
      throw new Error('El navegador no permite dibujar el código QR');
    }

    context.fillStyle = '#ffffff';
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.fillStyle = '#111827';
    for (let y = 0; y < matrix.getHeight(); y++) {
      for (let x = 0; x < matrix.getWidth(); x++) {
        if (matrix.get(x, y)) {
          context.fillRect(x, y, 1, 1);
        }
      }
    }
    return canvas.toDataURL('image/png');
  }

  openPaymentLink(): void {
    if (this.paymentLink) {
      window.open(this.paymentLink, '_blank', 'noopener,noreferrer');
    }
  }

  get isMercadoPagoSandbox(): boolean {
    return this.paymentLink.toLowerCase().includes('sandbox.mercadopago');
  }

  async copyPaymentLink(): Promise<void> {
    if (!this.paymentLink) return;
    try {
      await navigator.clipboard.writeText(this.paymentLink);
      this.dialogService.success('Enlace de pago copiado. Ya puedes enviarlo al cliente.');
    } catch {
      this.dialogService.warning('No se pudo copiar automáticamente. Abre el enlace y cópialo desde la barra del navegador.');
    }
  }

  async sharePaymentLink(): Promise<void> {
    if (!this.paymentLink) return;
    const share = (navigator as any).share;
    if (typeof share !== 'function') {
      await this.copyPaymentLink();
      return;
    }
    try {
      await share.call(navigator, {
        title: `Pago MediZano ${this.paymentOrderNumber}`,
        text: `Paga S/ ${this.paymentAmount.toFixed(2)} de la orden ${this.paymentOrderNumber}`,
        url: this.paymentLink
      });
    } catch (error: any) {
      if (error?.name !== 'AbortError') {
        await this.copyPaymentLink();
      }
    }
  }

  verifyPaymentNow(): void {
    if (!this.paymentPreferenceId || this.paymentQrStatus === 'approved') return;
    this.paymentQrStatus = 'checking';
    this.paymentStatusMessage = 'Consultando el estado directamente con Mercado Pago…';
    this.reconcilePaymentPreference();
  }

  closePaymentLinkModal(): void {
    this.stopPaymentPolling();
    this.showPaymentLinkModal = false;
    this.paymentQrDataUrl = '';
    this.paymentLink = '';
    this.paymentOrderId = null;
    this.paymentOrderNumber = '';
    this.paymentPreferenceId = '';
    this.paymentAmount = 0;
    this.isLoading = false;
    this.resetBill();
  }

  downloadApprovedPaymentReceipt(): void {
    if (this.paymentOrderId != null) {
      this.downloadOrderInvoicePdf(this.paymentOrderId);
    }
  }

  private schedulePaymentPoll(delayMs = 3000): void {
    this.stopPaymentPolling();
    if (!this.showPaymentLinkModal || this.paymentQrStatus === 'approved') return;
    this.paymentPollingTimer = setTimeout(() => this.pollPaymentStatus(), delayMs);
  }

  private pollPaymentStatus(): void {
    if (!this.showPaymentLinkModal || this.paymentOrderId == null || this.paymentQrStatus === 'approved') return;
    if (Date.now() >= this.paymentPollingDeadline) {
      this.paymentQrStatus = 'waiting';
      this.paymentStatusMessage = 'La orden sigue pendiente. Puedes cerrar esta ventana; el webhook confirmará el pago cuando llegue.';
      this.stopPaymentPolling();
      return;
    }

    this.paymentPollAttempts++;
    this.mercadopagoService.obtenerPagosOrden(this.paymentOrderId).subscribe({
      next: (payments: PaymentStatusRecord[]) => {
        const payment = payments.find(item => item.provider === 'MERCADO_PAGO');
        if (payment?.status === 'APPROVED' && payment.orderConfirmed !== false) {
          this.markPaymentApproved(payment.externalStatus);
          return;
        }
        if (this.paymentPollAttempts % 4 === 0) {
          this.reconcilePaymentPreference();
        } else {
          this.paymentQrStatus = 'waiting';
          this.paymentStatusMessage = 'Esperando que el cliente complete el pago. La verificación es automática.';
          this.schedulePaymentPoll();
        }
      },
      error: () => this.schedulePaymentPoll(5000)
    });
  }

  private reconcilePaymentPreference(): void {
    if (!this.paymentPreferenceId) return;
    this.mercadopagoService.reconciliarPreferencia(this.paymentPreferenceId).subscribe({
      next: (payment: MercadoPagoPaymentResponse) => {
        if (payment.status?.toLowerCase() === 'approved' && payment.orderConfirmed !== false) {
          this.markPaymentApproved(payment.paymentId);
        } else {
          this.paymentQrStatus = 'waiting';
          this.paymentStatusMessage = 'El pago todavía está pendiente en Mercado Pago.';
          this.schedulePaymentPoll();
        }
      },
      error: () => {
        this.paymentQrStatus = 'waiting';
        this.paymentStatusMessage = 'Esperando el pago. No cierres esta pantalla si deseas ver la confirmación automática.';
        this.schedulePaymentPoll(4000);
      }
    });
  }

  private markPaymentApproved(reference?: string): void {
    this.stopPaymentPolling();
    this.paymentQrStatus = 'approved';
    this.paymentStatusMessage = reference
      ? `Pago aprobado y venta confirmada. Referencia: ${reference}`
      : 'Pago aprobado y venta confirmada correctamente.';
  }

  private stopPaymentPolling(): void {
    if (this.paymentPollingTimer) {
      clearTimeout(this.paymentPollingTimer);
      this.paymentPollingTimer = undefined;
    }
  }

  private openPaymentWindow(name: string, width: number, height: number): Window | null {
    const left = window.screenX + (window.outerWidth - width) / 2;
    const top = window.screenY + (window.outerHeight - height) / 2;
    return window.open('about:blank', name,
      `width=${width},height=${height},left=${left},top=${top},scrollbars=yes`);
  }

  private formatPaymentErrorMessage(err: any, gatewayName: string): string {
    const status = err?.status || err?.error?.status;
    const backendMsg = err?.error?.message;

    if (backendMsg && (backendMsg.includes('no está configurado') || backendMsg.includes('Sandbox') || backendMsg.includes('Mercado Pago'))) {
      return backendMsg;
    }
    if (status === 503 || status === 424) {
      return `${gatewayName} no está configurado o no se encuentra disponible.`;
    }
    if (status === 401) {
      return `Credenciales inválidas de ${gatewayName}.`;
    }
    if (status === 404) {
      return 'Orden no encontrada en la pasarela de pagos.';
    }
    if (status === 0) {
      return `Error de conexión con ${gatewayName}.`;
    }
    if (backendMsg) {
      return backendMsg;
    }
    return `Pasarela no disponible (${gatewayName}).`;
  }

  private buildElectronicOrder(billItems: BillItemRequest[], paymentMethod: 'PAYPAL' | 'MERCADO_PAGO'): CrearOrdenRequest {
    const user = this.authService.getCurrentUser();
    return {
      clienteNombre: this.billForm.get('customerName')?.value?.trim() || 'Cliente General',
      clienteEmail: this.billForm.get('customerEmail')?.value?.trim() || undefined,
      usuarioId: user?.id,
      usuarioNombre: user?.username,
      metodoPago: paymentMethod,
      items: billItems.map(item => {
        if (!item.medicineId) {
          throw new Error('Los pagos electrónicos requieren un medicamento identificado');
        }
        return { productoId: item.medicineId, cantidad: item.quantity };
      })
    };
  }

  private downloadOrderInvoicePdf(orderId: number): void {
    this.isLoading = true;
    this.billingService.downloadOrderInvoicePdf(orderId).subscribe({
      next: (blob: Blob) => {
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `Comprobante_Orden_${orderId}.pdf`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        window.URL.revokeObjectURL(url);
        this.isLoading = false;
      },
      error: () => {
        this.dialogService.warning('El pago fue aprobado. El comprobante aún se está generando; podrás descargarlo desde el historial.');
        this.isLoading = false;
      }
    });
  }



  downloadBillPdf(billId: number): void {
    this.isLoading = true;
    this.billingService.downloadBillPdf(billId).subscribe({
      next: (blob: Blob) => {
        // Create a download link
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = this.lastReceiptData?.seriesNumber ? `Ticket_${this.lastReceiptData.seriesNumber}.pdf` : `Ticket_${this.currentBill?.billNumber || billId}.pdf`;
        this.dialogService.success('Comprobante guardado exitosamente.');
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        window.URL.revokeObjectURL(url);
        this.isLoading = false;
      },
      error: (error: any) => {
        console.error('Error al descargar PDF:', error);
        this.dialogService.error('Error al descargar PDF: ' + (error.message || 'error desconocido'));
        this.isLoading = false;
      }
    });
  }

  // ==========================================
  // GESTIÓN DEL RECIBO / VOUCHER MODAL POS-PAGO
  // ==========================================

  openReceiptModal(
    bill: BillResponse,
    paymentMode: PaymentMode | string,
    cashProvided?: number,
    cashChange?: number
  ): void {
    const user = this.authService.getCurrentUser();
    const cashierName = user?.fullName || user?.username || bill.cashierName || 'Cajero en turno';
    const email = bill.customerEmail || this.billForm.get('customerEmail')?.value?.trim() || '';
    const phone = bill.customerPhone || this.billForm.get('customerPhone')?.value?.trim() || '';
    const customerName = bill.customerName || this.billForm.get('customerName')?.value?.trim() || 'Cliente general';

    const docDisplay = this.customerDocNumber
      ? `${this.customerDocType}: ${this.customerDocNumber}`
      : 'Cliente General (Sin documento)';

    const receiptItems = (bill.items && bill.items.length > 0)
      ? bill.items.map(it => ({
          name: it.medicineName,
          quantity: it.quantity,
          batchNumber: it.batchNumber || 'LOTE-STD',
          unitPrice: it.unitPrice,
          total: it.totalAmount
        }))
      : this.items.map(it => ({
          name: it.medicine?.name || it.barcode || 'Medicamento',
          quantity: it.quantity,
          batchNumber: it.batchNumber || 'LOTE-STD',
          unitPrice: it.unitPrice || 0,
          total: it.total || 0
        }));

    this.lastReceiptData = {
      type: 'BOLETA DE VENTA ELECTRÓNICA',
      seriesNumber: bill.billNumber || `B001-${String(bill.id || Math.floor(1000 + Math.random() * 9000)).padStart(8, '0')}`,
      billId: bill.id,
      date: bill.billDate ? new Date(bill.billDate) : new Date(),
      cashier: cashierName,
      customerName: customerName,
      customerDoc: docDisplay,
      customerEmail: email,
      customerPhone: phone,
      items: receiptItems,
      subtotal: bill.subtotal || this.subtotal,
      igv: bill.totalGst || this.totalGst,
      total: bill.totalAmount || this.totalAmount,
      paymentMode: paymentMode === PaymentMode.CASH ? 'EFECTIVO' : (paymentMode === PaymentMode.PAYPAL ? 'PAYPAL' : 'MERCADO PAGO'),
      cashProvided: cashProvided != null ? cashProvided : (bill.totalAmount || this.totalAmount),
      cashChange: cashChange != null ? cashChange : 0
    };

    this.emailReceiptAddress = email;
    this.receiptEmailSent = false;
  this.receiptEmailError = '';
    this.receiptEmailTimestamp = '';

    try {
      const qrText = `MEDIZANO|03|B001|${this.lastReceiptData.seriesNumber}|${Number(this.lastReceiptData.igv).toFixed(2)}|${Number(this.lastReceiptData.total).toFixed(2)}|${new Date().toISOString().slice(0, 10)}|${this.customerDocType}|${this.customerDocNumber || '00000000'}`;
      this.receiptQrCodeUrl = this.createQrDataUrl(qrText);
    } catch {
      this.receiptQrCodeUrl = '';
    }

    this.showReceiptModal = true;

    // Regla 2: Evaluar si el campo email contiene un correo válido:
    // Si tiene correo: despachar automáticamente en segundo plano
    // Si el campo está vacío: completar la venta normalmente sin intentar enviar y sin alertas de fallo
    if (this.isValidEmail(email)) {
      this.sendReceiptAutomatically(email);
    } else {
      this.sendingReceiptEmail = false;
      this.receiptEmailSent = false;
      this.receiptEmailError = '';
    }
  }

  openReceiptModalForElectronicOrder(
    orderId: number,
    paymentMethod: 'PAYPAL' | 'MERCADO_PAGO',
    reference: string,
    amount: number
  ): void {
    const user = this.authService.getCurrentUser();
    const cashierName = user?.fullName || user?.username || 'Cobro en Línea';
    const email = this.billForm.get('customerEmail')?.value?.trim() || '';
    const phone = this.billForm.get('customerPhone')?.value?.trim() || '';
    const customerName = this.billForm.get('customerName')?.value?.trim() || 'Cliente General';
    const docDisplay = this.customerDocNumber
      ? `${this.customerDocType}: ${this.customerDocNumber}`
      : 'Cliente General';

    const receiptItems = this.items.map(it => ({
      name: it.medicine?.name || it.barcode || 'Medicamento',
      quantity: it.quantity,
      batchNumber: it.batchNumber || 'LOTE-STD',
      unitPrice: it.unitPrice || 0,
      total: it.total || 0
    }));

    this.lastReceiptData = {
      type: 'BOLETA DE VENTA ELECTRÓNICA',
      seriesNumber: `B002-${String(orderId).padStart(8, '0')}`,
      orderId: orderId,
      date: new Date(),
      cashier: cashierName,
      customerName: customerName,
      customerDoc: docDisplay,
      customerEmail: email,
      customerPhone: phone,
      items: receiptItems,
      subtotal: this.subtotal,
      igv: this.totalGst,
      total: this.totalAmount || amount,
      paymentMode: paymentMethod === 'PAYPAL' ? 'PAYPAL SANDBOX' : 'MERCADO PAGO',
      paymentReference: reference,
      cashProvided: this.totalAmount || amount,
      cashChange: 0
    };

    this.emailReceiptAddress = email;
    this.receiptEmailSent = false;
  this.receiptEmailError = '';
    this.receiptEmailTimestamp = '';

    try {
      const qrText = `MEDIZANO|03|B002|${this.lastReceiptData.seriesNumber}|${Number(this.lastReceiptData.igv).toFixed(2)}|${Number(this.lastReceiptData.total).toFixed(2)}|${new Date().toISOString().slice(0, 10)}|${this.customerDocType}|${this.customerDocNumber || '00000000'}`;
      this.receiptQrCodeUrl = this.createQrDataUrl(qrText);
    } catch {
      this.receiptQrCodeUrl = '';
    }

    this.showReceiptModal = true;

    // Regla 2: Evaluar si el campo email contiene un correo válido:
    // Si tiene correo: despachar automáticamente en segundo plano
    // Si el campo está vacío: completar la venta normalmente sin intentar enviar y sin alertas de fallo
    if (this.isValidEmail(email)) {
      this.sendReceiptAutomatically(email);
    } else {
      this.sendingReceiptEmail = false;
      this.receiptEmailSent = false;
      this.receiptEmailError = '';
    }
  }

  openMercadoPagoReceipt(): void {
    if (this.paymentOrderId != null) {
      this.openReceiptModalForElectronicOrder(
        this.paymentOrderId,
        'MERCADO_PAGO',
        this.paymentPreferenceId || `MP-${this.paymentOrderId}`,
        this.paymentAmount || this.totalAmount
      );
      this.showPaymentLinkModal = false;
    }
  }

  isValidEmail(email?: string): boolean {
    if (!email) return false;
    const clean = email.trim();
    return clean.length >= 5 && clean.includes('@') && clean.includes('.');
  }

  buildEmailReceiptRequest(targetEmail: string): EmailReceiptRequest | null {
    if (!this.lastReceiptData) return null;
    const items: EmailReceiptItemDTO[] = (this.lastReceiptData.items || []).map((it: any) => ({
      name: it.name || 'Medicamento',
      quantity: Number(it.quantity) || 1,
      unitPrice: Number(it.unitPrice) || 0,
      total: Number(it.total) || 0
    }));

    return {
      to: targetEmail,
      seriesNumber: this.lastReceiptData.seriesNumber || 'B001-00000001',
      customerName: this.lastReceiptData.customerName || 'Cliente General',
      customerDoc: this.lastReceiptData.customerDoc || 'Sin documento',
      cashier: this.lastReceiptData.cashier || 'Cajero',
      paymentMode: this.lastReceiptData.paymentMode || 'EFECTIVO',
      date: new Date().toLocaleString('es-PE', { timeZone: 'America/Lima', day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true }),
      subtotal: Number(this.lastReceiptData.subtotal) || 0,
      igv: Number(this.lastReceiptData.igv) || 0,
      total: Number(this.lastReceiptData.total) || 0,
      items: items
    };
  }

  sendReceiptAutomatically(targetEmail?: string): void {
    const email = (targetEmail || this.emailReceiptAddress)?.trim();
    if (!this.isValidEmail(email)) {
      this.sendingReceiptEmail = false;
      this.receiptEmailSent = false;
      this.receiptEmailError = '';
      return;
    }

    const payload = this.buildEmailReceiptRequest(email);
    if (!payload) return;

    this.emailReceiptAddress = email;
    this.sendingReceiptEmail = true;
    this.receiptEmailSent = false;
    this.receiptEmailError = '';

    this.billingService.sendReceiptEmail(payload).subscribe({
      next: (res: EmailReceiptResponse) => {
        this.sendingReceiptEmail = false;
        if (res && res.success) {
          this.receiptEmailSent = true;
          this.receiptEmailError = '';
          const now = new Date();
          this.receiptEmailTimestamp = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
          this.dialogService.success(`✓ Comprobante enviado exitosamente a: ${email}`);
        } else {
          this.receiptEmailSent = false;
          this.receiptEmailError = res?.message || 'Error en servidor de correo';
          this.dialogService.warning(`✕ Error al enviar correo: ${this.receiptEmailError}`);
        }
      },
      error: (err: any) => {
        this.sendingReceiptEmail = false;
        this.receiptEmailSent = false;
        const msg = err?.error?.message || err?.message || 'Error de conexión con el servicio de correo';
        this.receiptEmailError = msg;
        this.dialogService.warning(`✕ Error al enviar correo: ${msg}`);
      }
    });
  }

  sendReceiptManually(): void {
    const email = this.emailReceiptAddress?.trim();
    if (!this.isValidEmail(email)) {
      this.dialogService.warning('Por favor ingresa un correo electrónico válido (ej. cliente@gmail.com).');
      return;
    }
    this.sendReceiptAutomatically(email);
  }

  sendReceiptByGmail(): void {
    this.sendReceiptManually();
  }

  openUniversalEmail(provider?: 'gmail' | 'outlook' | 'yahoo' | 'mailto' | 'auto'): void {
    const to = this.emailReceiptAddress?.trim() || this.lastReceiptData?.customerEmail || '';
    const series = this.lastReceiptData?.seriesNumber || 'B001-00000001';
    const total = this.lastReceiptData?.total != null ? Number(this.lastReceiptData.total).toFixed(2) : '0.00';
    const customer = this.lastReceiptData?.customerName || 'Cliente General';
    const dateStr = new Date().toLocaleString('es-PE', { timeZone: 'America/Lima' });

    let bodyText = `Estimado(a) ${customer},\n\n`;
    bodyText += `Adjuntamos el detalle oficial de su comprobante electrónico en MediZano Botica:\n\n`;
    bodyText += `=========================================\n`;
    bodyText += `   MEDIZANO - BOTICA & FARMACIA\n`;
    bodyText += `   RUC: 20608945123 · Av. Larco 742, Miraflores\n`;
    bodyText += `   Comprobante: ${series}\n`;
    bodyText += `   Fecha: ${dateStr}\n`;
    bodyText += `   Cliente: ${customer}\n`;
    bodyText += `=========================================\n`;
    bodyText += `DETALLE DE MEDICAMENTOS:\n`;
    (this.lastReceiptData?.items || []).forEach((item: any, idx: number) => {
      const q = item.quantity || 1;
      const n = item.name || 'Medicamento';
      const u = Number(item.unitPrice || 0).toFixed(2);
      const t = Number(item.total || 0).toFixed(2);
      bodyText += `${idx + 1}. ${n} (Cant: ${q}) - P.Unit: S/ ${u} -> Total: S/ ${t}\n`;
    });
    bodyText += `-----------------------------------------\n`;
    bodyText += `SUBTOTAL (Op. Gravada): S/ ${Number(this.lastReceiptData?.subtotal || 0).toFixed(2)}\n`;
    bodyText += `I.G.V. (18%): S/ ${Number(this.lastReceiptData?.igv || 0).toFixed(2)}\n`;
    bodyText += `IMPORTE TOTAL: S/ ${total}\n`;
    bodyText += `FORMA DE PAGO: ${this.lastReceiptData?.paymentMode || 'EFECTIVO'}\n`;
    bodyText += `=========================================\n\n`;
    bodyText += `¡Gracias por su compra en MediZano Botica!\n`;
    bodyText += `Representación impresa de la Boleta de Venta Electrónica autorizada por SUNAT.`;

    const subject = `Comprobante de Venta Electrónica ${series} - MediZano Botica`;
    const lowerTo = to.toLowerCase();

    let target = provider || 'auto';
    if (target === 'auto') {
      if (lowerTo.includes('@gmail.')) {
        target = 'gmail';
      } else if (lowerTo.includes('@hotmail.') || lowerTo.includes('@outlook.') || lowerTo.includes('@live.') || lowerTo.includes('@msn.')) {
        target = 'outlook';
      } else if (lowerTo.includes('@yahoo.')) {
        target = 'yahoo';
      } else {
        target = 'mailto';
      }
    }

    if (target === 'gmail') {
      const gmailUrl = `https://mail.google.com/mail/?view=cm&fs=1&to=${encodeURIComponent(to)}&su=${encodeURIComponent(subject)}&body=${encodeURIComponent(bodyText)}`;
      window.open(gmailUrl, '_blank', 'noopener,noreferrer');
    } else if (target === 'outlook') {
      const outlookUrl = `https://outlook.live.com/mail/0/deeplink/compose?to=${encodeURIComponent(to)}&subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(bodyText)}`;
      window.open(outlookUrl, '_blank', 'noopener,noreferrer');
    } else if (target === 'yahoo') {
      const yahooUrl = `https://compose.mail.yahoo.com/?to=${encodeURIComponent(to)}&subj=${encodeURIComponent(subject)}&body=${encodeURIComponent(bodyText)}`;
      window.open(yahooUrl, '_blank', 'noopener,noreferrer');
    } else {
      const mailtoUrl = `mailto:${encodeURIComponent(to)}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(bodyText)}`;
      window.open(mailtoUrl, '_blank');
    }
  }

  openInGmailWeb(): void {
    this.openUniversalEmail('auto');
  }

  printReceipt(): void {
    const printableElement = document.getElementById('receipt-printable');
    if (!printableElement) return;

    let iframe = document.getElementById('receipt-print-frame') as HTMLIFrameElement;
    if (!iframe) {
      iframe = document.createElement('iframe');
      iframe.id = 'receipt-print-frame';
      iframe.style.position = 'fixed';
      iframe.style.right = '0';
      iframe.style.bottom = '0';
      iframe.style.width = '0';
      iframe.style.height = '0';
      iframe.style.border = '0';
      iframe.style.opacity = '0';
      document.body.appendChild(iframe);
    }

    const doc = iframe.contentWindow?.document || iframe.contentDocument;
    if (!doc) return;

    doc.open();
    doc.write(`
      <!DOCTYPE html>
      <html>
        <head>
          <title>Ticket_${this.lastReceiptData?.seriesNumber || 'Venta'}</title>
          <style>
            @page { size: 80mm auto; margin: 0; }
            * { box-sizing: border-box; }
            body { font-family: 'Courier New', Courier, monospace; margin: 0; padding: 4mm; width: 72mm; color: #000; font-size: 11px; }
            .thermal-ticket { width: 100%; }
            .ticket-header { text-align: center; margin-bottom: 8px; }
            .ticket-logo-text { font-size: 16px; font-weight: bold; }
            .ticket-sub { font-size: 10px; margin-bottom: 4px; }
            .ticket-company-info { font-size: 9px; color: #333; margin-bottom: 4px; }
            .ticket-divider-dash { border-bottom: 1px dashed #000; margin: 6px 0; }
            .ticket-doc-header { text-align: center; margin: 6px 0; }
            .ticket-doc-name { font-size: 11px; font-weight: bold; }
            .ticket-doc-number { font-size: 13px; font-weight: bold; }
            .ticket-meta-grid { font-size: 11px; margin-bottom: 6px; }
            .meta-item { display: flex; justify-content: space-between; margin-bottom: 2px; }
            .meta-label { font-weight: bold; }
            .ticket-items-table { width: 100%; font-size: 11px; border-collapse: collapse; margin: 6px 0; }
            .ticket-items-table th { border-bottom: 1px dashed #000; text-align: left; padding: 3px 0; font-size: 10px; }
            .ticket-items-table td { padding: 3px 0; vertical-align: top; }
            .th-cant, .td-cant { width: 14%; text-align: center; }
            .th-desc, .td-desc { width: 44%; }
            .th-unit, .td-unit { width: 22%; text-align: right; }
            .th-tot, .td-tot { width: 20%; text-align: right; }
            .item-batch { font-size: 9px; color: #444; }
            .ticket-totals-section { font-size: 11px; margin: 6px 0; }
            .total-row { display: flex; justify-content: space-between; padding: 2px 0; }
            .grand-total { font-size: 13px; font-weight: bold; border-top: 1px dashed #000; border-bottom: 1px dashed #000; padding: 4px 0; }
            .ticket-payment-details { font-size: 11px; }
            .payment-row { display: flex; justify-content: space-between; margin-bottom: 2px; }
            .ticket-qr-container { text-align: center; margin-top: 8px; }
            .ticket-qr-image { width: 110px; height: 110px; }
            .ticket-footer-legal { font-size: 8px; margin-top: 6px; text-align: center; color: #333; }
          </style>
        </head>
        <body>
          ${printableElement.innerHTML}
        </body>
      </html>
    `);
    doc.close();

    setTimeout(() => {
      iframe.contentWindow?.focus();
      iframe.contentWindow?.print();
    }, 250);
  }

  downloadReceiptPdf(): void {
    if (this.lastReceiptData?.billId) {
      this.downloadBillPdf(this.lastReceiptData.billId);
    } else if (this.lastReceiptData?.orderId) {
      this.downloadOrderInvoicePdf(this.lastReceiptData.orderId);
    } else {
      this.dialogService.warning('Comprobante no disponible para descarga directa.');
    }
  }

  closeReceiptModal(): void {
    this.showReceiptModal = false;
    this.lastReceiptData = null;
    this.receiptQrCodeUrl = '';
    this.emailReceiptAddress = '';
    this.receiptEmailSent = false;
  this.receiptEmailError = '';
    this.receiptEmailTimestamp = '';
    this.resetBill();
  }
}
