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

### 2.1. Fase 0 — Construcción de la Skill

Antes de escribir ningún modelo Django ni ninguna vista, se construye una skill
de referencia que documente:

- **Esquema de tarifas**: estructura de datos de la tarifa de cada aseguradora.
  Conceptos mínimos esperados: kilómetros (precio/km con tramos si aplica),
  servicio base (precio fijo por activación), espera (precio/hora o fracción),
  recargo nocturno (porcentaje o importe fijo), recargo festivo, recargo en
  autopista, servicios especiales (vehículo pesado, 4×4, embarcación, etc.).
- **Campos de entrada del presupuesto**: datos que el operario introduce para
  generar el presupuesto (aseguradora, tipo de vehículo asistido, kilómetros
  recorridos, hora del servicio, duración de la espera, condiciones especiales).
- **Reglas de cálculo**: lógica de aplicación de cada concepto de tarifa sobre
  los datos de entrada, incluyendo tramos, topes y exclusiones.
- **Estructura de factura de referencia**: campos extraídos de las facturas de
  ejemplo entregadas por el cliente para validar que el motor reproduce los
  importes correctamente.

La skill se construye iterativamente: el cliente entrega datos (tarifas en PDF/Excel,
facturas de ejemplo) y el modelo los procesa y estructura en la skill hasta que
Miguel Ángel valida que el esquema es correcto y completo.

### 2.2. Fase 1 — Modelos Django

Nueva app Django `budgets` con los siguientes modelos (sujetos a ajuste tras
la skill):

- `Insurer`: compañía aseguradora. Campos: company (FK), name, code, is_active.
- `InsurerTariff`: tarifa vigente de una aseguradora. Campos: insurer (FK),
  valid_from, valid_to (nullable), notes.
- `TariffLine`: línea de concepto de tarifa. Campos: tariff (FK), concept_code,
  concept_name, unit (KM, HOUR, FIXED, PERCENT), price, min_units, max_units
  (tramos), applies_condition (nullable, ej: NIGHT, HOLIDAY, HIGHWAY).
- `Budget`: presupuesto generado. Campos: company (FK), insurer (FK),
  tariff (FK), operator (FK CompanyUser), created_at, service_date,
  vehicle_type, km_total, wait_hours, conditions (JSON), status
  (DRAFT/CONFIRMED/BILLED), total_amount.
- `BudgetLine`: línea de desglose del presupuesto. Campos: budget (FK),
  tariff_line (FK nullable), concept_name, units, unit_price, subtotal, notes.

### 2.3. Fase 2 — Vistas y Panel

- CRUD de aseguradoras y tarifas desde el panel (AdminRoleRequiredMixin).
- Formulario de generación de presupuesto (SupervisorAccessMixin).
- Vista de listado de presupuestos con filtros por aseguradora, fecha y estado.
- Vista de detalle / edición de presupuesto (añadir/quitar líneas manualmente).
- Exportación PDF o Excel del presupuesto con membrete.

### 2.4. Fase 3 — Exportación

Motor de exportación del presupuesto a PDF (usando la librería ya disponible
en el entorno) o Excel (openpyxl / xlsxwriter según lo disponible). El documento
exportado replica el formato de las facturas de referencia entregadas por el cliente.

---

## 3. Hoja de Ruta

### Paso 1 — Recopilación de datos y construcción de la skill
- Solicitar al cliente: tarifas por aseguradora (PDF, Excel o imagen),
  facturas de ejemplo emitidas (mínimo 3 por aseguradora).
- Procesar cada tarifa y extraer: conceptos, unidades, precios, tramos,
  recargos y condiciones especiales.
- Procesar cada factura de ejemplo y extraer: campos de cabecera, líneas
  de desglose, importes y condiciones aplicadas.
- Redactar la skill con el esquema validado.
- Estado: PENDIENTE

### Paso 2 — Validación de la skill con Miguel Ángel
- Revisión conjunta del esquema de tarifas y reglas de cálculo.
- Ajustes hasta que el esquema reproduzca correctamente los importes
  de las facturas de ejemplo.
- Estado: PENDIENTE

### Paso 3 — Modelo de datos Django (app budgets)
- Crear app budgets con modelos Insurer, InsurerTariff, TariffLine,
  Budget, BudgetLine.
- Migraciones generadas y aplicadas en producción.
- Estado: PENDIENTE

### Paso 4 — CRUD de aseguradoras y tarifas en el panel
- Vistas de alta, edición y baja de aseguradoras.
- Vistas de gestión de líneas de tarifa por aseguradora.
- Estado: PENDIENTE

### Paso 5 — Motor de generación de presupuestos
- Formulario de entrada de datos del servicio.
- Lógica de aplicación de tarifa y generación de BudgetLine por concepto.
- Vista de revisión y edición manual del presupuesto generado.
- Estado: PENDIENTE

### Paso 6 — Exportación del presupuesto
- Motor de exportación a PDF/Excel con formato de factura de referencia.
- Estado: PENDIENTE

### Paso 7 — Integración en sidebar del panel
- Nueva sección "Presupuestos" visible para ADMIN y SUPERVISOR.
- Estado: PENDIENTE

---

## 4. Registro de Sesiones

| Sesión | Fecha | Pasos trabajados | Resumen |
|--------|-------|-----------------|---------|
| —      | —     | —               | Hito inaugurado. Skill pendiente de datos del cliente. |

---

## 5. Hoja de Ruta para la Siguiente Sesión (001)

### Objetivo de la sesión 001

Construir la skill de referencia del motor de presupuestos a partir de los
datos reales entregados por el cliente.

### Orden de trabajo

PASO 0 — Entrega de datos por el cliente:
  Miguel Ángel entrega en la sesión 001 los siguientes materiales:
    - Tarifas de cada aseguradora en el formato disponible (PDF, Excel, imagen,
      texto libre). Mínimo una tarifa completa para arrancar.
    - Facturas de ejemplo emitidas (mínimo 2-3 por aseguradora entregada).
  El modelo los procesa uno a uno y construye el esquema de la skill.

PASO 1 — Extracción de conceptos de tarifa:
  Para cada tarifa entregada:
    - Identificar todos los conceptos facturables (servicio base, km, espera,
      recargos, especiales).
    - Determinar la unidad de cada concepto (fijo, por km, por hora, porcentaje).
    - Extraer los precios y tramos si los hay.
    - Documentar las condiciones de aplicación (nocturno, festivo, autopista, etc.).

PASO 2 — Extracción de estructura de facturas de referencia:
  Para cada factura de ejemplo:
    - Identificar los campos de cabecera (aseguradora, número de expediente,
      fecha, datos del vehículo asistido, operario).
    - Extraer las líneas de desglose con concepto, unidades, precio unitario
      e importe.
    - Verificar que los importes son reproducibles con los conceptos de tarifa
      extraídos en el Paso 1.

PASO 3 — Redacción de la skill:
  Redactar el archivo de skill con:
    - Sección de esquema de tarifa (estructura de datos).
    - Sección de campos de entrada del presupuesto.
    - Sección de reglas de cálculo con ejemplos concretos de los datos reales.
    - Sección de estructura de factura de referencia.
  La skill se guarda en /mnt/skills/user/ con nombre budgets-asistencia.

CRITERIO DE ÉXITO:
  La skill permite que en la sesión 002 el modelo implemente el modelo de datos
  Django sin necesidad de que Miguel Ángel explique de nuevo la lógica de negocio.
  El esquema reproduce correctamente los importes de las facturas de ejemplo.
