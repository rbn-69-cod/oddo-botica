export type TipoDocumentoCompra = 'FACTURA' | 'BOLETA' | 'GUIA_REMISION' | 'ORDEN_COMPRA';
export type EstadoCompra = 
  | 'BORRADOR' 
  | 'PENDIENTE' 
  | 'ORDEN_ACEPTADA' 
  | 'EMPAQUETANDO' 
  | 'EN_CAMINO' 
  | 'EN_ENTREGA' 
  | 'POR_VERIFICAR' 
  | 'VERIFICANDO' 
  | 'RECIBIDA' 
  | 'CANCELADA';

export interface DetalleCompra {
  id?: number;
  productoId: number;
  nombreProducto: string;
  codigoBarra?: string;
  categoria?: string;
  presentacion?: string;
  cantidadComprada: number;
  cantidadRecibida?: number;
  costoUnitario: number;
  precioVenta?: number;
  descuento?: number;
  subtotal?: number;
  loteSugerido?: string;
  fechaVencimiento?: string;
}

export interface Compra {
  id: number;
  numeroDocumento: string;
  tipoDocumento: TipoDocumentoCompra;
  proveedorId: number;
  proveedorRuc: string;
  proveedorRazonSocial: string;
  proveedorNombreComercial?: string;
  proveedorTelefono?: string;
  proveedorDireccion?: string;
  fechaEmision: string;
  fechaRegistro: string;
  fechaRecepcion?: string;
  estado: EstadoCompra;
  subtotal: number;
  igv: number;
  descuento: number;
  total: number;
  observaciones?: string;
  usuarioRegistro?: string;
  usuarioRecepcion?: string;
  totalItems?: number;
  guiaRemision?: string;
  tiempoEstimadoDias?: number;
  detalles: DetalleCompra[];
}

export interface CompraRequest {
  proveedorId: number;
  numeroDocumento: string;
  tipoDocumento: TipoDocumentoCompra;
  fechaEmision: string;
  observaciones?: string;
  detalles: {
    productoId: number;
    nombreProducto: string;
    cantidadComprada: number;
    costoUnitario: number;
    precioVenta?: number;
    descuento?: number;
    loteSugerido?: string;
    fechaVencimiento?: string;
    codigoBarra?: string;
  }[];
}

export interface ItemRecepcion {
  detalleId: number;
  cantidadRecibida: number;
  batchNumber?: string;
  expiryDate?: string;
  purchasePrice?: number;
  sellingPrice?: number;
  codigoBarra?: string;
}

export interface RecepcionCompraRequest {
  usuarioRecepcion?: string;
  observaciones?: string;
  items: ItemRecepcion[];
}

export interface PaginatedCompras {
  content: Compra[];
  totalElements: number;
  totalPages: number;
  size: number;
  number: number;
}
