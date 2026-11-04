export interface Proveedor {
  id: number;
  ruc: string;
  razonSocial: string;
  nombreComercial?: string;
  contactoResponsable?: string;
  telefono?: string;
  telefonoContacto?: string;
  email?: string;
  emailContacto?: string;
  direccion?: string;
  direccionFiscal?: string;
  activo: boolean;
  observaciones?: string;
  fechaRegistro?: string;
  fechaCreacion?: string;
  fechaActualizacion?: string;
}

export interface ProveedorFiltro {
  filtro?: string;
  page?: number;
  size?: number;
  sort?: string;
}

export interface PaginatedProveedores {
  content: Proveedor[];
  totalElements: number;
  totalPages: number;
  size: number;
  number: number;
}

