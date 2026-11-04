import { Component, OnInit } from '@angular/core';
import { FormBuilder, FormGroup, Validators } from '@angular/forms';
import { ProveedorService } from '../../core/services/proveedor.service';
import { Proveedor } from '../../core/models/proveedor.model';
import { AuthService } from '../../core/services/auth.service';

@Component({
  selector: 'app-suppliers',
  templateUrl: './suppliers.component.html',
  styleUrls: ['./suppliers.component.scss'],
  standalone: false
})
export class SuppliersComponent implements OnInit {
  proveedores: Proveedor[] = [];
  loading = false;
  filtro = '';
  page = 0;
  size = 10;
  totalPages = 0;
  totalElements = 0;

  showModal = false;
  isEditing = false;
  selectedProveedorId?: number;
  proveedorForm!: FormGroup;

  errorMessage = '';
  successMessage = '';

  constructor(
    private proveedorService: ProveedorService,
    private fb: FormBuilder,
    public authService: AuthService
  ) {
    this.initForm();
  }

  ngOnInit(): void {
    this.cargarProveedores();
  }

  initForm(): void {
    this.proveedorForm = this.fb.group({
      ruc: ['', [Validators.required, Validators.pattern(/^(10|15|17|20)\d{9}$/)]],
      razonSocial: ['', [Validators.required, Validators.minLength(3)]],
      nombreComercial: [''],
      contactoResponsable: [''],
      telefono: ['', [Validators.required, Validators.pattern(/^[\d\s\-\+\(\)]{6,20}$/)]],
      email: ['', [Validators.required, Validators.email]],
      direccion: ['', [Validators.required, Validators.minLength(5)]],
      observaciones: [''],
      activo: [true]
    });
  }

  cargarProveedores(): void {
    this.loading = true;
    this.proveedorService.listarProveedores({
      filtro: this.filtro.trim(),
      page: this.page,
      size: this.size
    }).subscribe({
      next: (resp) => {
        this.proveedores = resp.content;
        this.totalPages = resp.totalPages;
        this.totalElements = resp.totalElements;
        this.loading = false;
      },
      error: (err) => {
        this.errorMessage = err.message || 'Error al cargar proveedores';
        this.loading = false;
      }
    });
  }

  buscar(): void {
    this.page = 0;
    this.cargarProveedores();
  }

  limpiar(): void {
    this.filtro = '';
    this.page = 0;
    this.cargarProveedores();
  }

  abrirCrear(): void {
    this.isEditing = false;
    this.selectedProveedorId = undefined;
    this.proveedorForm.reset({ activo: true });
    this.errorMessage = '';
    this.successMessage = '';
    this.showModal = true;
  }

  abrirEditar(p: Proveedor): void {
    this.isEditing = true;
    this.selectedProveedorId = p.id;
    this.errorMessage = '';
    this.successMessage = '';
    this.proveedorForm.patchValue({
      ruc: p.ruc,
      razonSocial: p.razonSocial,
      nombreComercial: p.nombreComercial,
      contactoResponsable: p.contactoResponsable,
      telefono: p.telefono,
      email: p.email,
      direccion: p.direccion,
      observaciones: p.observaciones,
      activo: p.activo
    });
    this.showModal = true;
  }

  cerrarModal(): void {
    this.showModal = false;
    this.proveedorForm.reset();
  }

  guardar(): void {
    if (this.proveedorForm.invalid) {
      this.proveedorForm.markAllAsTouched();
      return;
    }

    const val = this.proveedorForm.value;
    const payload = {
      ...val,
      direccionFiscal: val.direccion,
      telefonoContacto: val.telefono,
      emailContacto: val.email
    };
    this.loading = true;

    if (this.isEditing && this.selectedProveedorId) {
      this.proveedorService.actualizarProveedor(this.selectedProveedorId, payload).subscribe({
        next: () => {
          this.successMessage = 'Proveedor actualizado con éxito.';
          this.loading = false;
          this.cerrarModal();
          this.cargarProveedores();
        },
        error: (err) => {
          this.errorMessage = err.message || 'Error al actualizar proveedor';
          this.loading = false;
        }
      });
    } else {
      this.proveedorService.crearProveedor(payload).subscribe({
        next: () => {
          this.successMessage = 'Proveedor registrado exitosamente.';
          this.loading = false;
          this.cerrarModal();
          this.cargarProveedores();
        },
        error: (err) => {
          this.errorMessage = err.message || 'Error al registrar proveedor';
          this.loading = false;
        }
      });
    }
  }

  desactivar(p: Proveedor): void {
    if (!confirm(`¿Está seguro de desactivar al proveedor ${p.razonSocial}?`)) {
      return;
    }
    this.loading = true;
    this.proveedorService.desactivarProveedor(p.id).subscribe({
      next: (resp) => {
        this.successMessage = resp.message || 'Proveedor desactivado correctamente.';
        this.cargarProveedores();
      },
      error: (err) => {
        this.errorMessage = err.message || 'Error al desactivar proveedor';
        this.loading = false;
      }
    });
  }

  cambiarPagina(delta: number): void {
    const nueva = this.page + delta;
    if (nueva >= 0 && nueva < this.totalPages) {
      this.page = nueva;
      this.cargarProveedores();
    }
  }
}

