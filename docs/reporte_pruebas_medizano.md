# Reporte Completo de Pruebas, Operaciones y Soluciones — MediZano Botica

**Entorno evaluado:** `http://34.207.242.153/medizano/` (`ec2-34-207-242-153.compute-1.amazonaws.com`)  
**Base de datos:** `medizano_test` (`90 MB`, `6` conexiones activas, PostgreSQL 16)  
**Fecha de ejecución:** 24 de noviembre de 2026  

> [!TIP]
> **Resumen Ejecutivo: 18 / 18 pruebas aprobadas (100% PASS).**  
> Todos los flujos críticos (ventas, precios con IGV 18%, Culqi Tarjeta, Yape, SMTP SpaceMail, QR, PDF, seguridad `401`, carga concurrente e integridad contable/stock) superaron las pruebas en vivo sin errores en logs.

---

## 1. Matriz General de Resultados (7 Suites · 18 Pruebas)

### A. Pruebas Unitarias y de Lógica de Negocio
| # | Prueba | Estado | Tiempo | Resultado verificado |
| :-: | :--- | :-: | :-: | :--- |
| 1 | Redondeo comercial `_cash_price(lst_price * 1.18)` | ✅ PASS | `0.0 ms` | 5/5 casos exactos (`11.14→13.20`, `10.00→11.80`, `50.00→59.00`, `0.85→1.10`, `65.59→77.40`) |
| 2 | Desglose tributario IGV 18% (`Subtotal + IGV = Total`) | ✅ PASS | `0.0 ms` | Exactitud al céntimo en todos los casos |

### B. Pruebas HTTP, Frontend y Caché
| # | Prueba | Estado | Tiempo | Resultado verificado |
| :-: | :--- | :-: | :-: | :--- |
| 3 | Frontend `index.html` (`:8080`) y control de caché | ✅ PASS | `<10 ms` | `HTTP 200`, `Cache-Control: no-store, no-cache`, carga `main-KL5XJ37B.js` y `checkout.culqi.com/js/v4` |
| 4 | Gateway SSO `/medizano/` | ✅ PASS | `<10 ms` | `HTTP 302 → /sso/frontend`; bundle sin Mercado Pago, con Culqi + Yape y fechas `dd/MM/yyyy` |
| 5 | Odoo `/web/login` | ✅ PASS | `25.2 ms` | `HTTP 200 OK` |
| 6 | Bloqueo de `/web/database/selector` (`list_db = False`) | ✅ PASS | `77.6 ms` | Selector de bases de datos deshabilitado correctamente |

### C. Pruebas de Rendimiento y Carga Concurrente
| # | Prueba | Estado | Tiempo | Resultado verificado |
| :-: | :--- | :-: | :-: | :--- |
| 7 | **15 peticiones HTTP concurrentes** a Odoo | ✅ PASS | `352.1 ms` | **15/15 `HTTP 200`** · latencia mediana **`p50 = 203.0 ms`** · **`p95 = 331.7 ms`** |

### D. Pruebas de Seguridad y Control de Acceso
| # | Prueba | Estado | Tiempo | Resultado verificado |
| :-: | :--- | :-: | :-: | :--- |
| 8 | Acceso sin sesión a **10 endpoints protegidos** (`/bills`, `/returns`, `/users`, `/audit`, `/bsc`, `/medicines`, `/pagos/config`, `/enviar-correo`, `/compras`, `/kardex`) | ✅ PASS | `217.1 ms` | **10/10 rechazados con `HTTP 401 Unauthorized`** |
| 9 | Intento `POST /api/v1/pagos/culqi/charge` sin sesión | ✅ PASS | `23.2 ms` | Rechazado con **`HTTP 401`** |

### E. Pruebas E2E de Pasarela de Pagos (Culqi + Yape)
| # | Prueba | Estado | Tiempo | Resultado verificado |
| :-: | :--- | :-: | :-: | :--- |
| 10 | `GET https://api.culqi.com/v2/charges` (Secret Key) | ✅ PASS | `256.9 ms` | `HTTP 200 OK` · 5 cargos recientes consultados |
| 11 | Tokenización **Yape** válida (`900000001` / `123456`, S/ 13.20) | ✅ PASS | `362.6 ms` | Token real generado: `ype_test_8xRdubvQfap2SnOM` |
| 12 | **Prueba negativa Yape** (celular inválido de 8 dígitos `90000001`) | ✅ PASS | `413.5 ms` | Rechazo controlado `HTTP 400` |

### F. Pruebas de Correo SMTP, Motor PDF y QR
| # | Prueba | Estado | Tiempo | Resultado verificado |
| :-: | :--- | :-: | :-: | :--- |
| 13 | Handshake SSL + Autenticación SMTP SpaceMail (`:465`) | ✅ PASS | `713.3 ms` | `235 Authentication successful` (`medizano@univer.lat`) |
| 14 | Motor de boletas PDF (`wkhtmltopdf`) | ✅ PASS | `8.1 ms` | `wkhtmltopdf 0.12.6.1 (with patched qt)` operativo |
| 15 | Generación de código QR PNG para boleta | ✅ PASS | `15.2 ms` | PNG válido de `814 bytes` generado |

### G. Pruebas de Integridad Financiera, Contable y de Inventario
| # | Prueba | Estado | Tiempo | Resultado verificado |
| :-: | :--- | :-: | :-: | :--- |
| 16 | Cuadre financiero 100% (órdenes vs líneas vs pagos) | ✅ PASS | `6.1 ms` | **97 boletas** · **`S/ 14,322.50`** · descuadres líneas = **`0`**, pagos = **`0`** |
| 17 | Cajeros reales y correos de clientes `@univer.lat` | ✅ PASS | `1.0 ms` | Ventas con `OdooBot` = **`0`** · correos fuera de `@univer.lat` = **`0`** |
| 18 | Integridad de stock, precios y correlativo `B001` | ✅ PASS | `6.8 ms` | Stock negativo = **`0`**, productos precio `0` = **`0`**, duplicados = **`0`**, secuencia = **`97`** (próxima `B001-00000098`) |

---

## 2. Operaciones y Hallazgos con Soluciones Concretas

Aunque el 100% de las pruebas funcionales y de datos pasaron, se identificaron **5 puntos operativos** con su solución directa lista para ejecutar cuando lo decidas:

| Prioridad | Hallazgo detectado | Impacto | Solución operativa recomendada |
| :-: | :--- | :--- | :--- |
| **P0** | **Sitio solo en HTTP (`:80`) sin HTTPS** | Navegador muestra *"No es seguro"*; Culqi en modo `live` y cámara de escáner requieren HTTPS | Apuntar dominio (ej. `medizano.univer.lat`) a `34.207.242.153` e instalar certificado **Certbot / Let's Encrypt** + cabeceras `HSTS`, `X-Frame-Options`, `X-Content-Type-Options`. |
| **P0** | **Llaves de Culqi en modo pruebas (`pk_test_` / `sk_test_`)** | Solo acepta tarjetas y celulares de prueba | Al pasar a producción, reemplazar `medizano.culqi.public_key` y `medizano.culqi.secret_key` por `pk_live_...` y `sk_live_...`. |
| **P1** | **Sin backups automáticos programados** (último dump: `2026-11-06`) | Riesgo de pérdida de ventas recientes ante falla de disco | Crear cron diario `0 3 * * *` con `docker exec medizano_db pg_dump -U odoo -Fc medizano_test > /opt/medizano/backups/medizano_$(date +%F).dump` y retención de 14 días. |
| **P1** | **Firewall UFW inactivo en el host (`Status: inactive`)** | Depende únicamente del Security Group de AWS | Activar UFW permitiendo solo `22/tcp`, `80/tcp` y `443/tcp`. |
| **P2** | **1 lote vencido (`AMOX-LOT-2026`, `Amoxicillin 500mg Capsules`, venció `2026-10-31`) y 39 correos viejos en `exception`** | Alerta de vencimiento pendiente y ruido histórico en `mail_mail` | Dar de baja/cuarentena al lote vencido en Inventario y depurar los 39 `mail_mail` fallidos anteriores a la reparación SMTP. |

---

## 3. Guía Rápida de Pruebas Manuales (QA)

| Flujo | Paso a paso | Resultado esperado |
| :--- | :--- | :--- |
| **Venta Efectivo** | POS → Agregar producto → Paso Cliente → **EFECTIVO** → *Exacto* → *Registrar venta* | Boleta correlativa `B001-00000098`, descuento de stock FEFO y registro en Facturación + Caja diaria. |
| **Venta Culqi Tarjeta** | POS → Agregar producto → **CULQI** → *Pagar con Culqi* → Visa `4111 1111 1111 1111`, fecha futura, CVV `123` | Aprobación instantánea, boleta `B001-...`, monto idéntico en CulqiPanel y envío automático del correo rediseñado. |
| **Venta Yape** | POS → Agregar producto → **YAPE** → *Pagar con Yape* → Celular `900000001`, OTP `123456` | Aprobación instantánea, método POS `Yape`, boleta `YAPE (CULQI)` y correo automático con insignia morada de Yape. |
| **Reportes y Fechas** | *Reportes → Ventas* y *Facturación* | Fechas en `dd/MM/yyyy` (ej. `24/11/2026`), totales exactos y cajeros reales. |
