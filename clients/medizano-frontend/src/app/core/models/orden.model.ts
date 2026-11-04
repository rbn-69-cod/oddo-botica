export interface DetalleOrden {
  id?: number;
  productoId: number;
  productoNombre?: string;
  cantidad: number;
  precioUnitario: number;
  subtotal: number;
}

export type EstadoOrden = 'PENDING' | 'PAGADA' | 'CANCELADA' | 'REEMBOLSADA';

export interface Orden {
  id: number;
  numeroOrden: string;
  fecha: string;
  clienteId?: number;
  clienteNombre?: string;
  clienteEmail?: string;
  usuarioId?: number;
  usuarioNombre?: string;
  subtotal: number;
  impuesto: number;
  total: number;
  estado: EstadoOrden;
  metodoPago?: string;
  referenciaPago?: string;
  detalles: DetalleOrden[];
  createdAt?: string;
}

export interface CrearOrdenRequest {
  clienteId?: number;
  clienteNombre?: string;
  clienteEmail?: string;
  usuarioId?: number;
  usuarioNombre?: string;
  metodoPago: string;
  items: {
    productoId: number;
    cantidad: number;
  }[];
}
