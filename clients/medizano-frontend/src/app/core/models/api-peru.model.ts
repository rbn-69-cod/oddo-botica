/**
 * DTOs y Modelos de Integración con apiperu.pe
 * Consultas oficiales de RENIEC (DNI) y SUNAT (RUC)
 */

export interface DniRequest {
  dni: string;
}

export interface DniData {
  numero: string;
  nombre_completo: string;
  nombres: string;
  apellido_paterno: string;
  apellido_materno: string;
  codigo_verificacion?: number;
  direccion?: string;
  direccion_completa?: string;
  ubigeo_reniec?: string;
  ubigeo_sunat?: string;
  ubigeo?: (string | null)[];
}

export interface RucRequest {
  ruc: string;
}

export interface RucData {
  ruc: string;
  nombre_o_razon_social: string;
  estado: string;
  condicion: string;
  departamento?: string;
  provincia?: string;
  distrito?: string;
  direccion?: string;
  direccion_completa?: string;
  ubigeo_sunat?: string;
  ubigeo?: (string | null)[];
  es_agente_de_retencion?: string;
  es_agente_de_percepcion?: string;
  es_agente_de_percepcion_combustible?: string;
  es_buen_contribuyente?: string;
}

export interface ApiPeruResponse<T> {
  success: boolean;
  message: string;
  data: T;
}

export type DniApiResponse = ApiPeruResponse<DniData>;
export type RucApiResponse = ApiPeruResponse<RucData>;

export interface ApiPeruError {
  status: number;
  code: 'UNAUTHORIZED' | 'NOT_FOUND' | 'VALIDATION_ERROR' | 'RATE_LIMIT' | 'SERVER_ERROR' | 'NETWORK_ERROR';
  message: string;
  details?: any;
}

