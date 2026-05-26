# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V16.md

# Anexo de Hito V16 — Motor de Presupuestos para Sección ASISTENCIA
# Proyecto: EnterpriseBot
# Fecha de inicio: 2026-05-25

---

## 1. Visión General del Hito

La sección de ASISTENCIA de la empresa cliente gestiona servicios de grúa y
asistencia en carretera cubiertos total o parcialmente por compañías aseguradoras.
Cada aseguradora tiene una tarifa propia (kilómetros, servicios especiales, esperas,
recargos nocturnos, festivos, etc.). Actualmente los presupuestos se elaboran de
forma manual consultando las tarifas en papel, lo que genera errores y consume
tiempo.

Este hito implementa un motor de presupuestos integrado en el panel de EnterpriseBot
que permita:

1. **Gestionar tarifas por aseguradora**: altas, bajas y edición de conceptos y
   precios de tarifa de cada compañía desde el panel.
2. **Generar presupuestos**: a partir de los datos de entrada del operario
   (tipo de servicio, kilómetros, esperas, condiciones especiales) el motor
   aplica la tarifa vigente de la aseguradora correspondiente y genera el
   presupuesto desglosado.
3. **Exportar el presupuesto**: documento PDF o Excel descargable desde el panel.
4. **Skill de referencia**: antes de implementar nada, se construye una skill
   que documente el esquema de tarifas, los campos de entrada y las reglas de
   cálculo, derivada de los datos reales entregados por el cliente (tarifas por
   aseguradora, facturas de ejemplo).

---

## 2. Arquitectura Técnica

### 2.1. App Django `budgets`

App creada y operativa en producción desde la sesión 001. Modelos:

- `Insurer`: compañía aseguradora. FK Company. Campos: name, code, is_active,
  management_fee_percent, surcharges_cumulative, notes.
- `VehicleType`: tipo de vehículo con nomenclatura propia de cada aseguradora.
  FK Insurer. Campos: name, sort_order, is_active.
- `InsurerTariff`: tarifa vigente con histórico. FK Insurer. Campos: year,
  valid_from, valid_to (null = activa), notes.
- `TariffLine`: línea de concepto de tarifa. FK InsurerTariff + VehicleType
  (nullable = concepto genérico). Conceptos: DEPARTURE, SERVICE_LOCAL,
  KM_NORMAL, KM_LONG, UNLOCK, RESCUE_HOUR, WAIT_HOUR, WORKER_HOUR,
  ASSISTANT_HOUR, CUSTODY_DAY, NYF_PERCENT, LOADED_PERCENT.
- `Budget`: presupuesto generado. FK Company, Insurer, InsurerTariff,
  CompanyUser, VehicleType. Campos: is_overnight, km_phase1, km_phase2,
  km_total, has_unlock, is_night_or_holiday, is_loaded, wait_hours,
  rescue_hours, assistant_hours, worker_hours, custody_days,
  total_amount, status (DRAFT/ACCEPTED/REJECTED).
- `BudgetLine`: desglose de cálculo. FK Budget. Solo visible para ADMIN.

### 2.2. Motor de cálculo (`budgets/services.py`)

Función `calculate_budget(budget)` idempotente:
1. Resuelve la `InsurerTariff` activa (valid_to=None).
2. Calcula km_total = km_phase1 + km_phase2 (antes del save).
3. Aplica salidas (1 o 2 si pernocta).
4. Aplica km (KM_NORMAL o KM_LONG según umbral km_threshold).
5. Aplica desbloqueo si has_unlock.
6. Aplica conceptos opcionales (rescate, espera, MO, ayudante, custodia)
   respetando min_units.
7. Aplica recargos (NYF, cargado) según surcharges_cumulative de Insurer.
8. Aplica management_fee si procede (solo COVEI 5%).
9. Devuelve lista de BudgetLine sin guardar. El caller persiste atómicamente.

### 2.3. Rol y usuario

- Rol `ROLE_ASSISTANCE` = "ASSISTANCE" añadido a CompanyUser.
- Usuario `asistencia` / `1234` creado con must_change_password=False.
- Mixin `AssistanceRequiredMixin` en panel/mixins.py.
- Sidebar: rol ASSISTANCE ve solo "Presupuestos → Nuevo presupuesto".
  Rol ADMIN ve además "Historial presupuestos".

### 2.4. Tarifas cargadas

23 aseguradoras, 188 tipos de vehículo, 550 líneas de tarifa cargadas
mediante `python manage.py seed_insurer_tariffs` (idempotente, con --dry-run).

Aseguradoras: Transsorual/Mondial, Europ Assistance, ARAG, Avinatan/ATE,
IMA Ibérica, Treasca, Asitur, TAI 2026, RACE, Mapfre, Inter Partner/AXA,
Servireac (SVR), Grúas Alvarez (tarifa propia), MAN Truck, Petit Forestier,
COVEI, TVA (ALSA), Scora y Selltruck (Ford), Veinluc, UTE Envases Ligeros,
Prosegur, F.C.C., Angal Truck.

### 2.5. URLs

Registradas en `enterprise_core/urls.py`:
`path('panel/budgets/', include('budgets.urls', namespace='budgets'))`

Endpoints: wizard, vehicle_types (HTMX), optional_concepts (HTMX),
result, status_update, history (ADMIN), detail (ADMIN).

---

## 3. Hoja de Ruta

### Paso 1 — Recopilación de datos y construcción de la skill
- Estado: COMPLETADO (S001 — integrado directamente en la app)

### Paso 2 — Validación de la skill con Miguel Ángel
- Estado: COMPLETADO (S001 — diseño validado iterativamente)

### Paso 3 — Modelo de datos Django (app budgets)
- Estado: COMPLETADO (S001 — migración 0001_initial aplicada en producción)

### Paso 4 — CRUD de aseguradoras y tarifas en el panel
- Estado: PENDIENTE — actualmente solo via Django Admin y management command.
  Futura mejora: formularios en el panel para gestión de tarifas sin admin.

### Paso 5 — Motor de generación de presupuestos
- Estado: COMPLETADO (S001 — formulario secuencial HTMX operativo)

### Paso 6 — Exportación del presupuesto
- Estado: PENDIENTE

### Paso 7 — Integración en sidebar del panel
- Estado: COMPLETADO (S001)

---

## 4. Registro de Sesiones

| Sesión | Fecha      | Pasos trabajados | Resumen |
|--------|------------|-----------------|---------|
| S001   | 2026-05-26 | 1–5, 7          | Implementación completa de la app budgets: modelos, motor de cálculo, vistas, templates, rol ASSISTANCE, usuario asistencia, 23 tarifas 2026 cargadas en BD (550 líneas). Formulario secuencial HTMX operativo. Vista de desglose ADMIN. Sidebar adaptado por rol. Directriz PEP8 añadida al SYSTEM_PROMPTS_NEW.md. |

---

## 5. Hoja de Ruta para la Siguiente Sesión (002)

### Contexto

La app `budgets` está operativa en producción y validada visualmente.
La siguiente sesión debe centrarse en mejoras de UX y funcionalidad
identificadas durante las pruebas de la sesión 001.

### Orden de trabajo

**MEJORA 1 — Marcar presupuestos como Aceptado/Rechazado desde el historial:**
  Actualmente el cambio de estado solo es posible desde la vista de resultado
  (`/panel/budgets/<pk>/result/`). El historial (`/panel/budgets/history/`)
  muestra el estado pero no permite cambiarlo. Añadir en cada fila del
  historial los botones Aceptar/Rechazar para presupuestos en estado DRAFT,
  usando HTMX para actualizar el badge de estado sin recargar la página.

  Implementación:
  - Añadir endpoint HTMX en `budgets/urls.py`:
    `path("<int:pk>/status/htmx/", BudgetStatusHTMXView.as_view(), name="status_htmx")`
  - Crear `BudgetStatusHTMXView` en `views.py` (POST, devuelve fragmento badge).
  - Modificar `history.html`: añadir botones inline condicionados a `b.status == 'DRAFT'`.
  - Añadir fragmento `_status_badge_fragment.html` para el swap HTMX.

**MEJORA 2 — Validación del motor contra factura real AXA (C/260178):**
  La factura de referencia tiene: 1 salida B35 (184,10€), desbloqueo/enganche
  (62,80€), 115 km a 1,95€/km (224,25€), recargo nocturno/festivo (235,58€).
  Total sin descuento: 706,73€. Con descuento 2%: 692,60€.
  La tarifa AXA en BD (código AXA / Inter Partner) usa km a 1,91€ para el
  tramo De 6.001 hasta 10.000 kg. Verificar que el motor reproduce el importe
  y si hay diferencia, identificar si es por tramo de peso distinto o por
  precio de km distinto en la tarifa cargada.

**MEJORA 3 — Valores tope de presupuesto por aseguradora:**
  Algunas aseguradoras tienen un importe máximo autorizable sin llamada previa
  a la central (ej: la factura AXA indica "Gastos autorizados: 706,73€ sin IVA").
  Añadir campo `max_authorized_amount` (DecimalField, nullable) en el modelo
  `Insurer`. Si el total calculado supera este tope, mostrar advertencia visual
  al operario en la pantalla de resultado (no bloquear, solo avisar).

  Implementación:
  - PMA en `budgets/models.py`: añadir campo `max_authorized_amount`.
  - `makemigrations budgets` + `migrate`.
  - PMA en `budgets/views.py` `BudgetResultView.get`: calcular si
    `budget.total_amount > insurer.max_authorized_amount` e inyectar
    `over_limit=True` en el contexto.
  - PMA en `result.html`: mostrar alerta Bootstrap warning si `over_limit`.
  - Actualizar el management command `seed_insurer_tariffs` con los topes
    conocidos (AXA: 706,73€ según factura de referencia).

**MEJORA 4 — Google Maps API para cálculo automático de kilómetros:**
  Añadir campos de ubicación al formulario de presupuesto:
  origen (dirección del siniestro) y destino (taller destino).
  Usar la Google Maps Distance Matrix API para calcular km reales de conducción
  (ida + vuelta). El operario puede aceptar el valor calculado o editarlo.
  Requiere `GOOGLE_MAPS_API_KEY` en el `.env` y actualización online previa
  (Directriz 4.4 del MASTER_DOCUMENT).

**MEJORA 5 — Exportación del presupuesto a PDF (Paso 6 del hito):**
  Generar un documento PDF del presupuesto con membrete.
  Usar la librería disponible en el entorno (verificar con
  `pip list | grep -i pdf` antes de implementar).
  El PDF debe incluir: datos del servicio, total, aseguradora, fecha,
  operario. Sin desglose de líneas (el desglose es solo para ADMIN).
