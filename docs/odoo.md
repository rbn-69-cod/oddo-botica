# Migración a Odoo 18

El proyecto utiliza ahora Odoo 18 como ERP principal. La funcionalidad de
botica vive en el módulo personalizado [`Pharmacy`](../addons/Pharmacy/README.md):

- productos farmacéuticos, lotes y vencimientos;
- FEFO y movimientos de inventario;
- POS, dispensación y recetas;
- pacientes, seguros y contactos;
- compras, proveedores y recepción;
- contabilidad, IGV, facturación y reportes;
- auditoría y configuración específica de farmacia.

## Arquitectura

```text
Odoo 18
├── módulos estándar: Contacts, Purchase, Stock, Sales/POS, Account, Mail
├── localización peruana: l10n_pe, l10n_pe_pos
└── módulo personalizado: addons/Pharmacy
    ├── farmacia y pacientes
    ├── dispensación y prescripciones
    ├── FEFO, lotes y vencimientos
    ├── POS y pagos
    └── reportes y auditoría
```

PostgreSQL se ejecuta como servicio separado mediante
[`docker-compose.yml`](../docker-compose.yml). Las credenciales se configuran
únicamente en `.env`; nunca deben guardarse en el repositorio.

## Puesta en marcha

```bash
cp .env.example .env
docker compose up -d
```

Después de crear la base de datos desde Odoo, instala el módulo
**MediZano - ERP de Farmacia y Botica (Perú)** desde Apps. Para actualizarlo
tras un cambio:

```bash
docker compose exec odoo odoo -d NOMBRE_DE_LA_BASE -u Pharmacy --stop-after-init
docker compose restart odoo
```

La arquitectura Java anterior permanece disponible únicamente como referencia
en [`docker-compose.microservices.yml`](../docker-compose.microservices.yml).
