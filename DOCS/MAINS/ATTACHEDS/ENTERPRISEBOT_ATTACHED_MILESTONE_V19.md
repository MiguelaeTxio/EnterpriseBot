# ENTERPRISEBOT_ATTACHED_MILESTONE_V19.md

## Hito 19 — Filtros, búsqueda, ordenación y exportación por plantillas en WorkOrderAdminHistoryView

### Objetivo
Implementar en `WorkOrderAdminHistoryView` un sistema completo de filtrado por familia de avería, búsqueda libre, ordenación por columnas y exportación Excel configurable mediante plantillas de usuario.

---

### Trabajo Realizado en S045

#### P1 — Cabeceras de ordenación en `admin_history.html` ✓
Cabeceras de columna (Operario, Fecha, Horas, Estado) convertidas en enlaces con indicadores ▲/▼ en las tres pestañas (Pendientes, Revisados, Histórico). Hidden inputs `sort` y `dir` preservan la ordenación al filtrar.

#### P2 — Filtro familia de avería + columna Familia + búsqueda libre ✓
- `WorkOrderAdminHistoryView._apply_filters()` extendida con parámetros `fault_category` (exact, con `.distinct()`) y `q` (OR icontains sobre `fault_description` + `repair_notes`).
- Helper `_dominant_fault_category()` añadido — devuelve el label en castellano de la familia dominante de las líneas del parte (usando `FaultCategory.choices`).
- Campo `fault_category` añadido al dict de `_enrich_work_orders()`.
- Barra de filtros actualizada: desplegable familia, input búsqueda, columnas Bootstrap ajustadas a `col-md-2`.
- Columna "Familia" añadida en las tres pestañas con badge `.badge-sm`.
- Clase `.badge-sm` añadida a `panel.css`.
- Bug corregido: `fault_category_choices` usaba `fc.value` → corregido a `fc[0]`.
- Bug corregido: hidden inputs `fault_category` y `q` duplicaban el valor GET → eliminados.
- Bug corregido: `.distinct()` añadido al filtro ORM para evitar duplicados por JOIN.

#### P4 — Desmarcar revisado individual + bulk ✓
- Rama `unmark_reviewed` añadida al `bulk_action` de `WorkOrderAdminHistoryView.post()`.
- Pestaña Revisados refactorizada: export bar antiguo eliminado, bulk bar con Desmarcar revisados / Marcar revisados / Eliminar, checkboxes por fila y global, botón HTMX individual de desmarcar, botón eliminar individual.
- `.djlintrc` creado con `per-file-ignores` H025 para `admin_history.html`.

#### P5 — Modelo ExportTemplate + migración 0022 ✓
Modelo `ExportTemplate` añadido a `work_order_processor/models.py` con `SheetFormat`, `OperatorScope`, `columns` JSONField, `UniqueConstraint` por usuario+nombre, `save()` override para unicidad de `is_default`, y `get_or_create_default()` classmethod. Migración `0022_exporttemplate` generada y aplicada.

#### P6 — Motor de exportación por plantillas ✓
- `build_export_from_template(template, work_orders_qs)` añadida a `work_order_processor/services.py`. Soporta `single_sheet` (con filas separadoras de operario) y `multi_sheet` (una hoja por operario). 11 columnas configurables.
- Vistas CRUD: `ExportTemplateListView`, `ExportTemplateCreateView`, `ExportTemplateUpdateView`, `ExportTemplateDeleteView` añadidas a `panel/views.py`.
- Vista `WorkOrderAdminExportByTemplateView` añadida — resuelve plantilla y partes, llama a `build_export_from_template`, devuelve xlsx attachment.
- 5 URLs nuevas añadidas a `panel/urls.py`.
- Modal `modalExportTemplate` añadido a `admin_history.html` — carga plantillas via AJAX, muestra resumen, gestiona selector de operarios, envía POST con PKs seleccionados.
- Formulario oculto `form-export-by-template` añadido al template.
- Template `panel/export_templates/list.html` creado — página CRUD standalone con cards por plantilla, modales crear/editar, fetch JSON API, botón establecer por defecto, delete con confirmación.
- `column_choices` añadido al contexto de `ExportTemplateListView`.

#### Skills actualizadas ✓
- `ped-format`: bloque INTEGRIDAD reemplazado por script Python inline — `git diff` eliminado completamente. Regla anti-fallo-silencioso `[ -z "$outN" ]`.
- `ped-pma`: scripts en SWAP, comprobaciones de variables vacías, sin `git diff`.

---

### Bugs Pendientes de Auditoría

#### BUG ACTIVO — Filtro familia de avería no filtra correctamente
**Síntoma:** Al seleccionar una familia en el desplegable, la tabla sigue mostrando partes de otras familias.
**Estado:** Se aplicó `.distinct()` al filtro ORM en S045. Pendiente verificación en producción y auditoría completa del flujo GET → `_apply_filters` → queryset → `_enrich_work_orders` → template.
**Acción requerida S046:** Auditar el flujo completo. Verificar que el valor GET del desplegable coincide exactamente con los valores almacenados en BD. Comprobar si el problema persiste tras el `.distinct()`.

---

### Archivos Modificados en S045

- `panel/views.py` — `_apply_filters`, `_dominant_fault_category`, `_enrich_work_orders`, `bulk_action`, 5 vistas CRUD ExportTemplate, `WorkOrderAdminExportByTemplateView`, `ExportTemplateListView` contexto `column_choices`
- `panel/urls.py` — 5 URLs nuevas ExportTemplate + export-by-template
- `panel/templates/panel/work_orders/admin_history.html` — barra filtros, columna Familia, bulk bar Revisados, modal exportación por plantilla
- `panel/templates/panel/export_templates/list.html` — neonato puro
- `panel/static/panel/css/panel.css` — clase `.badge-sm`
- `work_order_processor/models.py` — modelo `ExportTemplate`
- `work_order_processor/services.py` — función `build_export_from_template`
- `work_order_processor/migrations/0022_exporttemplate.py` — migración aplicada
- `.djlintrc` — neonato puro, `per-file-ignores` H025

---

### Hoja de Ruta para la Siguiente Sesión (S046)

#### Paso 1 — Auditoría del filtro de familia de avería
Verificar en producción si el filtro funciona tras el `.distinct()` aplicado en S045.
Si no funciona, auditar el flujo completo:
1. Confirmar que el desplegable envía el valor interno correcto (ej. `ENGINE_TRANSMISSION`) y no el label.
2. Confirmar que `_apply_filters` recibe el valor GET correctamente.
3. Confirmar que el filtro ORM `entries__lines__fault_category=fault_category` produce el queryset esperado ejecutando la query en la shell de Django.
4. Si el problema persiste, considerar filtrar via subquery con `WorkOrder.pk__in` en lugar de JOIN directo.

#### Paso 2 — Verificación E2E completa de la pestaña Revisados
- Verificar bulk bar: Desmarcar revisados, Marcar revisados, Eliminar.
- Verificar botón HTMX individual de desmarcar.
- Verificar botón Exportar y modal de plantillas.

#### Paso 3 — Fix botón Exportar cortado en bulk bar
El botón verde "Exportar" se desborda por la derecha en la bulk bar de Revisados. Ajustar el layout Bootstrap para que quede contenido.

#### Paso 4 — Verificación E2E motor de exportación
Probar exportación completa: seleccionar partes revisados → abrir modal → seleccionar plantilla → exportar → verificar xlsx descargado.
