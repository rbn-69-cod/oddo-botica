# Oddo Botica — ERP farmacéutico con Odoo 18

Sistema ERP para una botica peruana construido sobre Odoo 18. El módulo
personalizado `Pharmacy` integra ventas POS, productos farmacéuticos, lotes,
vencimientos FEFO, pacientes, recetas, compras, inventario, contabilidad,
auditoría y reportes en una sola plataforma ERP.

> El nombre del repositorio se conserva como `oddo-botica` para respetar el
> proyecto solicitado. La plataforma y el módulo son Odoo 18.

## Funcionalidades

- **Ventas y POS:** venta de medicamentos, recetas y medios de pago.
- **Productos e inventario:** lotes, fechas de vencimiento, control de stock y FEFO.
- **Compras:** proveedores, órdenes de compra y recepción de mercadería.
- **Facturación y contabilidad:** facturas, impuestos IGV y diarios contables.
- **Pacientes y contactos:** historial, seguros y datos del comprador.
- **Farmacia:** dispensación, prescripciones, sustancias controladas y devoluciones.
- **Reportes y auditoría:** dashboard, reportes financieros y trazabilidad de acciones.
- **Perú:** dependencias `l10n_pe` y `l10n_pe_pos`, con estructura preparada para SUNAT.

## Requisitos

- Docker y Docker Compose.
- Al menos 4 GB de RAM disponibles para Odoo y PostgreSQL.

## Inicio rápido

```bash
cp .env.example .env
# Cambie ODOO_DB_PASSWORD por una contraseña segura
docker compose up -d
```

Abra <http://localhost:8069>, cree o seleccione una base de datos e instale
**MediZano - ERP de Farmacia y Botica (Perú)** desde Apps.

### Frontend visual MediZano

El frontend Angular original de MediZano se encuentra en
`clients/medizano-frontend`. Se ejecuta junto con Odoo mediante Compose:

```bash
docker compose up -d --build
```

La interfaz visual queda disponible en <http://localhost:8080> y consume
`/api` del módulo `Pharmacy`, que autentica la sesión en Odoo y consulta sus
modelos ORM para inventario, lotes, proveedores, compras, órdenes y reportes.
El backend de Odoo continúa disponible en <http://localhost:8069>.

Para revisar los logs:

```bash
docker compose logs -f odoo
```

Para detener el entorno:

```bash
docker compose down
```

Los datos se guardan en los volúmenes `odoo-db-data` y `odoo-data`. No elimine
esos volúmenes si necesita conservar la base de datos.

## Estructura

```text
addons/Pharmacy/                 # Módulo Odoo personalizado
config/odoo.conf                 # Configuración sin secretos
docker-compose.yml               # Entorno Odoo 18 + PostgreSQL
.env.example                     # Variables requeridas
```

## Desarrollo del módulo

Después de editar el módulo, actualice la instalación con:

```bash
docker compose exec odoo odoo \
  --db_host=db \
  --db_user="$ODOO_DB_USER" \
  --db_password="$ODOO_DB_PASSWORD" \
  -d NOMBRE_DE_LA_BASE \
  -u Pharmacy \
  --stop-after-init
```

El nombre técnico del módulo es `Pharmacy`, tal como aparece en su manifest.
Para una instalación productiva, use HTTPS mediante un proxy inverso y
mantenga las credenciales únicamente en `.env` o en un gestor de secretos.

## Pruebas y validación

El módulo incluye pruebas Odoo en `addons/Pharmacy/tests`. Las pruebas de
integración requieren una base Odoo inicializada y PostgreSQL disponible.
