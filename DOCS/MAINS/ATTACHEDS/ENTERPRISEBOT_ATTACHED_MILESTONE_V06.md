# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V06.md

# Anexo de Hito V06 — Procesador de Partes de Trabajo PDF -> Excel + BBDD
# Proyecto: EnterpriseBot
# Estado: EN PROGRESO
# Fecha de inicio: 2026-04-21

---

## 1. Visión General del Hito

El Hito 6 incorpora a EnterpriseBot una funcionalidad de procesamiento documental
que permite a empresas cliente cargar archivos PDF que contienen fotografías de
partes de trabajo diarios de sus operarios. El sistema extrae automáticamente los
datos de cada parte mediante visión artificial (Gemini Vision), los persiste en
base de datos y genera un informe Excel descargable con la información estructurada.

La funcionalidad se construye sobre la app Django `work_order_processor` creada
desde cero (Opción B auditada en Paso 1), con arquitectura multiempresa desde
el inicio. La app `fleet` gestiona el catálogo de maquinaria como centros de
gasto y el libro de mantenimiento de cada activo.

---

## 2. Arquitectura Técnica

### 2.1. Flujo de Procesamiento

    Usuario sube PDF
        -> Django recibe el archivo (vista de carga)
        -> Celery task: extrae páginas del PDF como imágenes (200 DPI, en memoria)
        -> Por cada página/imagen:
            -> Gemini Vision analiza la foto del parte
            -> Se extraen hasta 4 bloques de trabajo por página (JSON multi-tramo)
            -> Se persiste WorkOrderEntry (cabecera de página) + WorkOrderEntryLine (por bloque)
            -> Se resuelve MachineAsset del catálogo fleet por código normalizado D4
        -> Se genera fichero Excel con openpyxl (17 columnas, skill partes-trabajo v1.2)
        -> Usuario descarga el Excel desde el panel

### 2.2. Apps Django involucradas

- `work_order_processor` — pipeline completo PDF->Excel, modelos WorkOrder /
  WorkOrderEntry / WorkOrderEntryLine.
- `fleet` — catálogo de maquinaria (MachineAsset), libro de mantenimiento
  (MaintenanceLog, MaintenanceItem). Centro de gasto por activo.

### 2.3. Campos extraídos por bloque (WorkOrderEntryLine)

| Campo              | Tipo            | Descripción                                      |
|--------------------|-----------------|--------------------------------------------------|
| maquina_raw        | CharField       | Código tal como lo extrae Gemini                 |
| maquina_norm       | CharField       | Normalizado según D4                             |
| machine_asset      | FK MachineAsset | Resuelto del catálogo fleet                      |
| descripcion_averia | TextField       | Descripción de la avería                         |
| reparacion         | TextField       | Descripción de la reparación                     |
| hc                 | TimeField       | Hora de comienzo (redondeada D3)                 |
| hf                 | TimeField       | Hora de finalización (redondeada D3)             |
| or_val             | CharField       | Referencia O.R.                                  |
| delta_horas        | DecimalField    | Horas netas (descontada pausa comida 13:30-15h)  |
| flags              | JSONField       | Campos con lectura incierta                      |

### 2.4. Stack Tecnológico

- Extracción de páginas PDF: PyMuPDF (fitz) — 200 DPI en memoria.
- Visión artificial: google-genai (Vertex AI) — modelo gemini-2.5-flash.
  Timeout: HttpOptions(timeout=360000) — 360 segundos en milisegundos. CRITICO.
- Generación Excel: openpyxl — 17 columnas, skill partes-trabajo v1.2.
- Procesamiento asíncrono: Celery + DjangoTask, cola work_orders, broker Redis Cloud.
- connection.close() antes de cada persistencia para evitar MySQL wait_timeout.

### 2.5. Modelo de Datos

WorkOrder — ciclo de vida del PDF: PENDING / PROCESSING / DONE / ERROR.
WorkOrderEntry — cabecera de página: worker_name (del nombre del PDF), work_date,
  fecha_incierta, raw_gemini_response, extraction_confidence.
WorkOrderEntryLine — un registro por bloque de trabajo (hasta 4/página).
MachineAsset — centro de gasto de flota. 313 activos importados del
  LISTADO MAQUINARIA de Grupo Álvarez. FK a Company.
MaintenanceLog — intervención de mantenimiento por MachineAsset.
  FK work_entry_line a WorkOrderEntryLine activado tras migración fleet.0002.
MaintenanceItem — línea de repuesto/mano de obra por intervención.
  tipos: REPUESTO_ALMACEN / REPUESTO_TERCERO / MANO_OBRA_TERCERO.

### 2.6. Excel generado (skill partes-trabajo v1.2 + col Q)

Filas 1-3: area de configuracion (titulo, precio hora extra C2, coste hora
ordinaria C3). Fila 4: cabeceras. Fila 5+: datos (una fila por WorkOrderEntryLine).

17 columnas: FECHA, OPERARIO, CODIGO/VEH., MARCA/MODELO, KM, HORAS VEH.,
DESCRIPCION AVERIA, REPARACION, H.C., H.F., O.R., Delta HORAS (neta),
HORAS NETAS DIA, HORAS EXTRAS, SALARIO EXTRAS, REVISION HORARIO, COSTE M.O.

Hoja LEYENDA + MANIFIESTO DE INCIDENCIAS al pie (D1-D5 de la skill).

---

## 3. Hoja de Ruta

### Paso 1 — Auditoria de delivery_note_processor
- Estado: COMPLETADO (2026-04-22) — Decision Opcion B: nueva app work_order_processor.

### Paso 2 — Dependencias
- Estado: COMPLETADO (2026-04-22) — PyMuPDF 1.27.2.2, openpyxl 3.1.5, redis 7.4.0.

### Paso 3 — Modelo de Datos
- Estado: COMPLETADO (2026-04-22) — WorkOrder + WorkOrderEntry. Migracion 0001.

### Paso 4 — Servicio de Extraccion Gemini
- Estado: COMPLETADO (2026-04-22) — services.py inicial con prompt plano.

### Paso 5 — Tarea Celery de Procesamiento
- Estado: COMPLETADO (2026-04-22) — DjangoTask, reintentos, 200 DPI.

### Paso 6 — Generacion de Excel
- Estado: COMPLETADO (2026-04-22) — Excel 11 columnas inicial.

### Paso 7 — Vista de Carga y Descarga en Panel
- Estado: COMPLETADO (2026-04-22) — WorkOrderListView + WorkOrderUploadView.

### Paso 8 — Validacion E2E inicial
- Estado: COMPLETADO (2026-04-22/23) — Pipeline E2E validado. Bloqueante detectado:
  Excel no cumple especificacion skill partes-trabajo. Paso 9 registrado.

### Paso 9 — Rediseno del modelo de extraccion y del generador Excel
- Estado: EN PROGRESO (2026-04-23).

Trabajo completado en sesion 004:

  A) App fleet creada:
     - Modelos: MachineAsset, MaintenanceLog, MaintenanceItem.
     - 313 activos importados del LISTADO MAQUINARIA (seed_fleet_catalog.py en SWAP).
     - Admin completo con inlines. MaintenanceLog.work_entry_line FK activado
       tras migracion 0002 de work_order_processor.
     - fleet registrada en INSTALLED_APPS. Migraciones 0001 y 0002 aplicadas.

  B) Reestructuracion work_order_processor:
     - WorkOrderEntry: eliminados campos de tramo. Anadidos: fecha_incierta.
       worker_name deriva del nombre del fichero PDF.
     - Nuevo modelo WorkOrderEntryLine: campos de bloque + FK MachineAsset.
     - Migracion 0002 aplicada.

  C) services.py reescrito:
     - _EXTRACTION_PROMPT: JSON multi-tramo con lista entradas[] hasta 4 bloques/pagina.
     - Helpers: _normalise_machine_code (D4), _resolve_machine_asset,
       _compute_delta_horas (descuento pausa comida 13:30-15:00).
     - _worker_name_from_pdf_path: deriva nombre del operario del nombre del fichero.
     - generate_work_order_excel(): 17 columnas, skill v1.2, PatternFill, LEYENDA,
       MANIFIESTO DE INCIDENCIAS, columna COSTE M.O. (delta_horas x C3).
     - HttpOptions(timeout=360000): 6 minutos en milisegundos. CRITICO.

  D) tasks.py adaptado:
     - Persiste WorkOrderEntry + WorkOrderEntryLine por bloque.
     - Normalizacion D4 + resolucion MachineAsset en el pipeline.
     - connection.close() antes de cada bloque de persistencia.

  E) admin.py de work_order_processor actualizado.

  F) Senal post_save en ivr_config para generacion automatica de CallFlow de seccion:
     - ivr_config/signals.py creado. Registrado en apps.py ready().
     - Al crear Section: genera CallFlow desde plantilla canonica con maquinaria
       de fleet filtrada por section.fleet_families.
     - Al modificar Section: backup + regeneracion del system_instruction.
     - ivr_config/models.py: campo fleet_families (JSONField) anadido a Section.
     - Migracion ivr_config.0011 aplicada.

  G) Fix backup/restore de CallFlow en panel:
     - Campo backup_name anadido a CallFlow. Migracion ivr_config.0012 aplicada.
     - CallFlowUpdateView.form_valid: values() directa a BD para estado pre-guardado.
     - CallFlowRestoreView: QuerySet.update() con variables locales pre-swap.
       Check has_backup incluye backup_name.
     - Template form.html: boton Restaurar fuera del form de edicion.
       Boton guardar renombrado a "Guardar".

Pendiente del Paso 9:
  - Validacion E2E con ALEJANDRO_GARCIA_LUQUE_21-10_AL_20-11.pdf (WorkOrder #10).
    Worker procesando en el momento del cierre de sesion.
  - Comparacion del Excel generado contra GARCIA_LUQUE_21-10_AL_20-11.xlsx.
  - Vista de edicion de WorkOrderEntryLine (correccion manual de incidencias).
  - Mejoras de UX en sidebar y panel de partes de trabajo (ver seccion 5).

---

## 4. Registro de Sesiones

| Sesion | Fecha      | Pasos trabajados | Resumen |
|--------|------------|-----------------|---------|
| 001    | 2026-04-21 | —               | Creacion del anexo. Inicio formal del hito. |
| 002    | 2026-04-22 | 1-8             | Pipeline PDF->Excel inicial. App work_order_processor. E2E validado. Bloqueante Excel detectado. |
| 003    | 2026-04-22 | Tarea 0, 8, 9 inicio | Sidebar dual. DjangoTask. E2E PDF real 23 pags. Diagnostico Paso 9. |
| 004    | 2026-04-23 | Paso 9 parcial  | App fleet completa. Reestructuracion work_order_processor. Prompt multi-tramo. Excel 17 cols. Senal IVR secciones. Fix backup/restore CallFlow. Fix timeout Gemini Vision ms. E2E en curso al cierre. |

---

## 5. Hoja de Ruta para la Siguiente Sesion

### Objetivo principal
Completar el Paso 9: validar E2E y arrancar mejoras de UX del panel.

### Subtarea 9.5 — Validacion E2E (PRIMERA ACCION DE LA SESION)

Al inicio de sesion verificar el estado del WorkOrder #10:

    python -m dotenv run python manage.py shell -c "
    from work_order_processor.models import WorkOrder, WorkOrderEntry, WorkOrderEntryLine
    wo = WorkOrder.objects.get(pk=10)
    print(f'Estado: {wo.status} | Pags: {wo.processed_pages}/{wo.total_pages}')
    entries = wo.entries.prefetch_related('lines').order_by('page_number')
    for e in entries[:3]:
        lines = e.lines.all()
        print(f'  Pag {e.page_number}: fecha={e.work_date} | lines={lines.count()} | conf={e.extraction_confidence}')
        for l in lines:
            print(f'    Bloque {l.line_number}: maq={l.maquina_raw}->{l.maquina_norm} | {l.hc}-{l.hf} | Delta={l.delta_horas}h')
    "

Si estado=DONE y hay WorkOrderEntryLine con datos -> descargar Excel y comparar con
GARCIA_LUQUE_21-10_AL_20-11.xlsx (Excel de referencia del agente).

Si estado=ERROR o lineas vacias -> diagnosticar segun error_log y log del worker.

### Nota tecnica critica — Timeout Gemini Vision

HttpOptions(timeout=360000) — el valor es en MILISEGUNDOS. 360000 = 6 minutos.
El SDK google-genai pasa este valor directamente a httpx por peticion, sobrescribiendo
cualquier timeout a nivel de cliente. Es el unico mecanismo fiable.
El cliente httpx personalizado es IGNORADO por el SDK.
Referencia: https://github.com/pydantic/pydantic-ai/issues/4031

### Subtarea 9.6 — Mejoras de UX del panel (tras validacion E2E exitosa)

A) Reestructuracion sidebar en secciones:
   - Voz: Flujos IVR, Secciones, Contactos, Numeros de telefono, Perfil de voz.
   - WhatsApp: Plantillas, Sesiones activas.
   - Administracion: Usuarios, Conjuntos de captura, PDFs.
   - Presencia: seccion propia.

B) Seccion PDFs — renombrar "Partes de Trabajo" -> "PDFs":
   Acciones por WorkOrder: Carga, Edicion y Vista, Exportar, Cancelar/Borrar/Renombrar.
   Desplegable de acciones en la vista de listado.

C) Botones del panel — leyenda clara:
   - Botones de guardado: "Guardar" en todos los formularios.
   - Botones de editar en listados: "Editar" sin nombre de entidad.

### Subtarea 9.7 — Vista de Edicion y Vista de WorkOrderEntryLine

Vista tabla editable que permita:
   - Ver todas las WorkOrderEntryLine de un WorkOrder agrupadas por pagina.
   - Editar inline: maquina_norm, descripcion_averia, reparacion, hc, hf, or_val.
   - Ver y corregir flags de incidencia.
   - Recalcular delta_horas al modificar hc/hf.
   - Boton "Regenerar Excel" para regenerar tras correcciones.

URL sugerida: /panel/work-orders/{pk}/edit/

### Estado de migraciones al cierre de sesion 004

| App                    | Ultima migracion aplicada                              |
|------------------------|--------------------------------------------------------|
| fleet                  | 0002_maintenancelog_work_entry_line                    |
| work_order_processor   | 0002_remove_workorderentry_end_time_and_more           |
| ivr_config             | 0012_callflow_backup_name                              |

### Archivos modificados en sesion 004 (resumen)

fleet/models.py, fleet/admin.py, fleet/apps.py, fleet/migrations/0001+0002
work_order_processor/models.py, work_order_processor/services.py,
work_order_processor/tasks.py, work_order_processor/admin.py,
work_order_processor/migrations/0002
ivr_config/models.py, ivr_config/signals.py, ivr_config/apps.py,
ivr_config/migrations/0011+0012
panel/views.py
panel/templates/panel/callflows/form.html
enterprise_core/settings.py
