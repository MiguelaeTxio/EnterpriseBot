# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V17.md

# Anexo de Hito V17 — Albaranes y Órdenes de Trabajo ASISTENCIA
# Proyecto: EnterpriseBot
# Fecha de creación: 2026-05-29

---

## 1. Visión General del Hito

La sección de ASISTENCIA necesita digitalizar el flujo completo de trabajo
desde que se acepta un presupuesto (o se genera una orden directa) hasta que
el operario entrega el servicio al cliente y este firma el albarán. El objetivo
es eliminar el papel, reducir errores de transcripción y dejar el albarán
listo para facturación con un solo clic desde el panel de administración.

El flujo tiene dos vías de entrada y un único flujo de salida:

**Vías de entrada:**
1. Presupuesto aceptado → se convierte automáticamente en Orden de Trabajo.
2. Orden de Trabajo nueva directa → sin presupuesto previo.

**Flujo de salida:**
El albarán digital firmado queda en el sistema listo para revisión ADMIN
y exportación a facturación.

---

## 2. Arquitectura Técnica

### 2.1. Modelos Django nuevos (app `budgets` o nueva app `work_orders`)

- `WorkOrderAssistance`: orden de trabajo de asistencia.
  - FK nullable a `Budget` (null cuando entrada directa).
  - FK a `Insurer`, `VehicleType`, `CompanyUser` (operario).
  - Campos: `service_date`, `status` (PENDING/IN_PROGRESS/COMPLETED/INVOICED),
    `base_location` (FK a base de operación), `extra_notes`.
  - Los datos del servicio (km, conceptos) se heredan del Budget si existe,
    o se introducen manualmente en la orden directa.

- `WorkOrderAssistanceLine`: líneas de incidencia adicionales del parte.
  - FK a `WorkOrderAssistance`.
  - Campos: `concept` (desplegable: espera adicional, rescate adicional,
    km adicionales, desbloqueo, custodia, etc.), `units`, `notes`.

- `WorkOrderAssistanceSignature`: firma digital del cliente.
  - OneToOneField a `WorkOrderAssistance`.
  - Campo: `signature_data` (TextField, base64 SVG/PNG capturado con
    signature_pad JS).
  - Campo: `signed_at` (DateTimeField auto).
  - Campo: `signer_name` (CharField, opcional — nombre del firmante).

### 2.2. Flujo de notificación al operario

Al crear una WorkOrderAssistance (desde presupuesto aceptado o entrada directa):
1. El sistema genera la URL directa al albarán digital del operario:
   `/panel/asistencia/ordenes/<pk>/albaran/`
2. Se envía un mensaje WhatsApp al operario via canal WhatsApp ya operativo
   en EnterpriseBot, con el enlace al albarán y los datos básicos del servicio.

### 2.3. Interfaz móvil del operario

Template `asistencia/albaran_operario.html`:
- Diseño mobile-first con Bootstrap 5.
- El albarán llega prellenado: compañía, vehículo, conceptos del presupuesto.
- Sección de incidencias adicionales: botón "Añadir concepto" desplegable
  con los conceptos disponibles y campo de unidades.
- Sección de firma: canvas con `signature_pad` JS (librería sin dependencias
  de servidor, funciona offline).
- Botón "Finalizar y firmar" — POST al servidor con firma base64 y líneas
  adicionales.

### 2.4. Modo offline PWA

Service Worker que cachea la página del albarán al abrirla con cobertura.
Al recuperar cobertura, el SW detecta la conexión y sincroniza el POST
pendiente automáticamente.

Indicador visual en la interfaz: banner "Sin cobertura — los datos se
guardarán al recuperar conexión" cuando `navigator.onLine === false`.

### 2.5. Exportación para facturación

PDF generado con `weasyprint` desde template `asistencia/albaran_pdf.html`.
Incluye: datos del servicio, conceptos del presupuesto, incidencias
adicionales, firma del cliente y totales.
Botón "Exportar PDF" en la vista de detalle ADMIN de la orden de trabajo.

### 2.6. Bases de operación en presupuestos y órdenes

El campo `Company.operation_bases` (TextField, ya migrado) contiene las
bases de operación. Para el wizard de presupuestos y para las órdenes de
trabajo, el operario selecciona la base de salida desde un desplegable.
Las bases se parsean desde `operation_bases` al cargar el wizard.
No se usa Google Maps API — los km se introducen manualmente o se derivan
del presupuesto.

---

## 3. Hoja de Ruta

### Paso 1 — Modelos y migración
- Estado: PENDIENTE
- Crear `WorkOrderAssistance`, `WorkOrderAssistanceLine`,
  `WorkOrderAssistanceSignature` en `budgets/models.py` o nueva app.
- Migración con `makemigrations` + `migrate`.

### Paso 2 — Vistas y URLs
- Estado: PENDIENTE
- `WorkOrderCreateFromBudgetView`: crea WorkOrderAssistance desde Budget aceptado.
- `WorkOrderCreateDirectView`: crea WorkOrderAssistance directa.
- `WorkOrderAlbaranView`: interfaz móvil del operario (firma + incidencias).
- `WorkOrderDetailView`: vista ADMIN de detalle.
- `WorkOrderPdfView`: exportación PDF.

### Paso 3 — Template móvil operario
- Estado: PENDIENTE
- `albaran_operario.html`: mobile-first, signature_pad, SW offline.

### Paso 4 — Notificación WhatsApp al operario
- Estado: PENDIENTE
- Integrar el envío de WhatsApp al crear la orden de trabajo.

### Paso 5 — Exportación PDF
- Estado: PENDIENTE
- `albaran_pdf.html` + `WorkOrderPdfView`.

### Paso 6 — Botón en BudgetResultView para crear orden de trabajo
- Estado: PENDIENTE
- Añadir botón "Generar orden de trabajo" en `result.html` cuando
  `budget.status == 'ACCEPTED'`.

---

## 4. Registro de Sesiones

| Sesión | Fecha | Pasos trabajados | Resumen |
|--------|-------|-----------------|---------|
| — | — | — | Hito creado en S005 (2026-05-29). Pendiente de iniciar. |

---

## 5. Hoja de Ruta para la Siguiente Sesión (S006 — NO EJECUTAR, H16 EN PROGRESO)

Este hito está PENDIENTE. No ejecutar hasta que el MASTER_DOCUMENT lo
marque EN PROGRESO. La hoja de ruta de S006 pertenece al Hito 16.

Cuando este hito pase a EN PROGRESO, arrancar por el Paso 1 (modelos
y migración) siguiendo el orden definido en la sección 3.
