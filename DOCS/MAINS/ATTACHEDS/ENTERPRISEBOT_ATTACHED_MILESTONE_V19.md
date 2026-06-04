# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V19.md

# Hito 19 — Mejoras WorkOrderAdminHistoryView: Filtros, Búsqueda, Ordenación y Exportación por Plantillas

## Estado General
EN PROGRESO. Pivotaje desde Hito 7 en S044 (2026-06-04).

---

## Alcance y Arquitectura

### Vista objetivo
`WorkOrderAdminHistoryView` + `panel/templates/panel/work_orders/admin_history.html`.
Roles con acceso: SUPERVISOR y ADMIN exclusivamente. WORKSHOP sin acceso a ninguna
funcionalidad de este hito.

### 1. Ordenación por columna (ya implementado en S044)
Parámetros GET `sort` y `dir` operativos en `WorkOrderAdminHistoryView`.
Columnas ordenables: fecha, operator_name, horas_totales, reviewed.
sort_col y sort_dir disponibles en el contexto del template para las cabeceras.
**Estado:** COMPLETADO (S044). Pendiente: actualizar cabeceras del template con indicadores
visuales (▲/▼) y enlaces que alternen `dir=asc`/`dir=desc` preservando filtros activos.

### 2. Filtro por familia de avería
Añadir un desplegable `fault_category` a la barra de filtros existente.
Valores: los distintos `fault_category` presentes en `WorkOrderEntryLine` de la empresa.
Filtra los WorkOrders cuyas líneas tengan la categoría seleccionada.
La columna `fault_category` se añade al listado en las tres pestañas (Pendientes, Revisados, Histórico).

**Archivos a modificar:**
- `panel/views.py` — `WorkOrderAdminHistoryView.get()`: leer `fault_category` del GET,
  aplicar filtro al queryset, pasar lista de categorías disponibles al contexto.
- `_apply_filters()`: añadir rama fault_category.
- `_enrich_work_orders()`: añadir campo `fault_category` al dict enriquecido.
- `panel/templates/panel/work_orders/admin_history.html`: desplegable en barra de filtros
  y columna familia de avería en las tres tablas.

### 3. Campo de búsqueda libre
Input de texto que busca simultáneamente en `fault_description` e `repair_notes`
de las líneas del parte (AND lógico con los demás filtros activos).
Parámetro GET: `q`.

**Archivos a modificar:**
- `panel/views.py` — `WorkOrderAdminHistoryView.get()`: leer `q`, aplicar filtro
  `entries__lines__fault_description__icontains` OR `entries__lines__repair_notes__icontains`.
- `_apply_filters()`: añadir rama `q`.
- `admin_history.html`: input de búsqueda en barra de filtros.

### 4. Acción desmarcar revisado
En la pestaña Revisados, añadir acción individual para revertir `reviewed=True` a `reviewed=False`.
El parte pasa a aparecer en la pestaña Pendientes.

**Archivos a modificar:**
- `panel/views.py` — `WorkOrderAdminHistoryView.post()`: nueva acción `unmark_reviewed`.
- `admin_history.html`: botón desmarcar en columna Acciones de la pestaña Revisados.

### 5. Motor de exportación por plantillas
Sustituye completamente a `WorkOrderAdminExportView` y su modal actual.
Toda exportación pasa obligatoriamente por el modal de selección de plantilla.

#### 5.1 Modelo ExportTemplate
Nueva app: `work_order_processor`. Migración nueva.

Campos:
- `company_user` FK → CompanyUser (on_delete=CASCADE)
- `name` CharField(max_length=100) — nombre de la plantilla
- `is_default` BooleanField(default=False) — plantilla por defecto del usuario
- `columns` JSONField — lista de claves de columna a incluir en el Excel
- `sheet_format` CharField choices: `single_sheet` | `multi_sheet`
- `operator_scope` CharField choices: `all` | `selection` — alcance de operarios
- `created_at` DateTimeField(auto_now_add=True)
- `updated_at` DateTimeField(auto_now=True)

Plantilla por defecto: creada automáticamente si el usuario no tiene ninguna,
con columnas estándar (fecha, operario, máquina, descripción, horas, estado, familia).

#### 5.2 Vistas CRUD de plantillas
- `ExportTemplateListView` — lista las plantillas del usuario autenticado.
- `ExportTemplateCreateView` — formulario de creación.
- `ExportTemplateUpdateView` — formulario de edición.
- `ExportTemplateDeleteView` — confirmación de eliminación.
Accesibles desde el modal de exportación y desde una sección de gestión en el panel.

#### 5.3 Motor de generación Excel
Función `build_export_from_template(template, work_orders_qs)` en
`work_order_processor/services.py`. Genera el Excel según la configuración
de la plantilla: columnas seleccionadas, formato de hoja, agrupación por operario.

#### 5.4 Flujo de exportación
1. Usuario pulsa "Exportar" en `admin_history.html`.
2. Modal muestra las plantillas del usuario con opción de selección y acceso a gestión.
3. Usuario selecciona plantilla y confirma.
4. POST a nueva vista `WorkOrderAdminExportByTemplateView` con pks + template_pk.
5. Vista genera el Excel y devuelve HttpResponse attachment.

---

## Columnas disponibles para plantillas

| Clave | Descripción |
|---|---|
| `fecha` | Fecha del parte (work_date) |
| `operario` | Nombre del operario (uploaded_by) |
| `maquina` | Código de máquina / Centro de gasto |
| `descripcion` | Descripción de avería (fault_description) |
| `notas` | Notas de reparación (repair_notes) |
| `hc` | Hora de inicio |
| `hf` | Hora de fin |
| `delta_horas` | Horas trabajadas (delta_hours) |
| `estado` | Estado del parte (reviewed) |
| `familia` | Familia de avería (fault_category) |
| `origen` | Origen del parte (source) |

---

## Directrices Técnicas Vinculantes

- **SDK IA:** `google-genai 2.7.0` — Modelo: `gemini-live-2.5-flash-native-audio` — Vertex AI
- **Framework:** Django `5.2.12` — Servidor async: `aiohttp 3.13.5` — Puerto `8081`
- **Twilio SDK:** `twilio 9.10.4` — Auth via API Key
- **Entorno:** PythonAnywhere — Python `3.10.5` — `EnterpriseBot_venv`
- **BD:** MySQL `MiguelAeTxio$enterprisebot`
- Directriz 4.4 activa: actualización online obligatoria antes de implementar
  código con APIs externas.

---

## Hoja de Ruta para S045

### Prioridad 1 — Cabeceras de ordenación en admin_history.html
Actualizar el template `admin_history.html` con cabeceras de columna enlazadas
que alternen `dir=asc`/`dir=desc` preservando todos los filtros activos,
con indicador visual (▲/▼) en la columna activa.

### Prioridad 2 — Filtro familia de avería + columna
Añadir desplegable `fault_category` en barra de filtros y columna familia
en las tres pestañas del listado. Requiere modificar `_apply_filters()`,
`_enrich_work_orders()` y el template.

### Prioridad 3 — Campo de búsqueda libre
Input `q` en barra de filtros. Busca en `fault_description` + `repair_notes`.

### Prioridad 4 — Acción desmarcar revisado
Botón en pestaña Revisados. Acción `unmark_reviewed` en el POST de la vista.

### Prioridad 5 — Modelo ExportTemplate + migración
Crear modelo en `work_order_processor/models.py`, generar y aplicar migración.

### Prioridad 6 — Motor de exportación por plantillas
Función `build_export_from_template` en services.py, vistas CRUD, modal de
selección en admin_history.html, sustitución de WorkOrderAdminExportView.

**Orden de ejecución en S045:**
1. Solicitar `admin_history.html` actualizado y `work_order_processor/models.py`.
2. PMA cabeceras de ordenación en admin_history.html (P1).
3. PMA filtro familia + columna en views.py (P2).
4. PMA filtro familia + columna en admin_history.html (P2).
5. PMA búsqueda libre en views.py + admin_history.html (P3).
6. PMA acción desmarcar revisado (P4).
7. PMA modelo ExportTemplate en models.py + migración (P5).
8. PEA función build_export_from_template + vistas CRUD + modal (P6).
9. Verificar E2E en producción.

---

## Registro de Sesiones

### S044 — 2026-06-04
**Título:** Apertura del Hito 19 y definición de arquitectura completa
**Descripción:** Sesión inaugural del Hito 19. Durante la sesión S044 (originalmente del Hito 7) se debatió el alcance de las mejoras de WorkOrderAdminHistoryView y se concluyó que el volumen justificaba un hito propio. Se definió la arquitectura completa: ordenación ya implementada en views.py (sort/dir), filtro por familia de avería con columna visible, campo de búsqueda libre acotado a fault_description y repair_notes, acción desmarcar revisado en pestaña Revisados, y motor de exportación por plantillas con modelo ExportTemplate en work_order_processor (columnas configurables, formato de hoja, alcance de operarios, plantilla por defecto automática, CRUD por usuario). El MASTER_DOCUMENT fue actualizado (H7 → PAUSADO, H19 → EN PROGRESO) y el anexo V07 registró el pivotaje. La sesión cierra con este anexo como única hoja de ruta activa.
