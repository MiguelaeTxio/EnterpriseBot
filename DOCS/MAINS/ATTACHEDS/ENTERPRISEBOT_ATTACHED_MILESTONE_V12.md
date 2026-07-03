# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V12.md

# Anexo de Hito V12 — Gestion de Centros de Gasto y Reorganizacion del Panel
# Proyecto: EnterpriseBot
# Estado: EN PROGRESO
# Fecha de inicio: 2026-05-01

---

## 1. Vision General del Hito

El Hito 12 agrupa dos lineas de trabajo estrechamente relacionadas que deben
ejecutarse de forma conjunta antes de retomar el Hito 7 (Partes Diarios de
Reparacion):

LINEA A — Gestion de Centros de Gasto:
  Ampliacion del concepto MachineAsset a Centro de Gasto. El catalogo de
  maquinaria ha demostrado en los partes historicos que los operarios no solo
  trabajan sobre maquinas sino tambien sobre entidades no catalogadas: secciones
  de alquiler, administracion, almacen, trabajos en exterior con terceros, etc.
  Estas entidades deben poder crearse, modificarse y darse de baja desde el panel
  sin acceder al admin de Django, y deben poder importarse desde un fichero
  actualizado entregado por el cliente.

LINEA B — Reorganizacion de la navegacion del panel:
  La navegacion actual del panel ha crecido de forma organica durante los hitos
  anteriores mezclando secciones que deberian estar agrupadas de forma distinta.
  Los flujos IVR, los usuarios, los partes de trabajo, la maquinaria y los centros
  de gasto deben quedar en secciones logicas e intuitivas para los roles ADMIN
  y SUPERVISOR.

Ambas lineas son prerequisito para el Hito 7, donde los operarios seleccionaran
centros de gasto desde desplegables poblados con datos correctos y completos.

---

## 2. Arquitectura Tecnica

### 2.1. Linea A — Modelo de Datos

El modelo MachineAsset en fleet/models.py es la base. Antes de implementar
cualquier cosa se debe solicitar fleet/models.py via SFTP para verificar:
  - Campos actuales del modelo.
  - Existencia o ausencia del campo activo (BooleanField).
  - Relacion con Company (multiempresa).
  - Migraciones aplicadas hasta la fecha.

Si el campo activo no existe, se creara como:
  activo = models.BooleanField(default=True, db_index=True,
      verbose_name="Activo",
      help_text="Desmarca para dar de baja sin eliminar el historico.")
  Con su correspondiente migracion.

El concepto de Centro de Gasto no requiere renombrar el modelo MachineAsset
en BD — el cambio es semantico y de presentacion en el panel. El verbose_name
del modelo se actualizara a "Centro de gasto" y el verbose_name_plural a
"Centros de gasto".

### 2.2. Linea A — Comando import_cost_centers

Archivo nuevo (neonato puro):
  fleet/management/commands/import_cost_centers.py

El comando recibe un fichero CSV o Excel con el listado actualizado de centros
de gasto y lo importa contra la BD de la empresa indicada.

Columnas minimas esperadas en el fichero:
  codigo, familia, marca_modelo, matricula

Logica:
  - Por cada fila del fichero: buscar MachineAsset por (company, codigo).
  - Si existe y hay cambios: actualizar campos. Registrar en log.
  - Si existe y no hay cambios: omitir. Registrar en log como sin cambios.
  - Si no existe: crear nuevo MachineAsset con activo=True. Registrar alta.
  - Flag --company <pk_o_nombre>: obligatorio. Acotar a empresa concreta.
  - Flag --dry-run: mostrar cambios detectados sin persistir nada.
  - Flag --apply: persistir cambios. IRREVERSIBLE sin --dry-run previo.
  - Flag --deactivate-missing: marcar activo=False en los MachineAsset de la
    empresa que no aparezcan en el fichero. Solo disponible si el campo activo
    existe. Requiere confirmacion explicita en consola [s/N].
  Informe de salida: altas / actualizaciones / sin cambios / bajas (si --deactivate-missing).

### 2.3. Linea A — Vistas CRUD en el panel

Nueva vista MachineAssetListView (AdminRoleRequiredMixin):
  Endpoint: GET /panel/fleet/
  Tabla paginada con todos los MachineAsset de la empresa ordenados por codigo:
    codigo, familia, marca_modelo, matricula, activo (si existe el campo).
  Filtro por familia y por activo/inactivo.
  Boton de alta manual via modal Bootstrap con formulario inline.
  Boton de edicion por fila via modal Bootstrap.
  Boton de baja (activo=False) por fila con confirmacion — no elimina el registro.
  Boton de eliminacion definitiva por fila con confirmacion — solo para ADMIN y
    solo si el MachineAsset no tiene WorkOrderEntryLine asociadas (integridad).
  Integracion HTMX para altas, ediciones y bajas sin recarga completa de pagina.

Nuevas vistas auxiliares:
  MachineAssetCreateView  — POST /panel/fleet/create/
  MachineAssetUpdateView  — POST /panel/fleet/<pk>/update/
  MachineAssetDeactivateView — POST /panel/fleet/<pk>/deactivate/
  MachineAssetDeleteView  — POST /panel/fleet/<pk>/delete/
  Todas con AdminRoleRequiredMixin.
  Todas devuelven fragmentos HTMX (filas de tabla actualizadas).

### 2.4. Linea B — Reorganizacion del panel

La reorganizacion afecta a _nav_items.html y a la agrupacion logica de las
secciones del sidebar. El diseno exacto se acordara al inicio de la sesion 001
del hito tras revisar el estado actual del sidebar con el usuario.

Principios de reorganizacion:
  - Seccion IVR: flujos, numeros de telefono, perfiles de voz, presencia.
  - Seccion Operaciones: partes de trabajo (PDFs + entradas digitales), centros
    de gasto, maquinaria.
  - Seccion Administracion: usuarios, empresas (solo superadmin), configuracion.
  - Seccion Analitica: informes, graficas, exportaciones.
  Cada seccion tiene un encabezado visual claro en el sidebar.
  Los roles WORKSHOP y DRIVER ven unicamente la seccion Operaciones reducida.
  El rol SUPERVISOR ve Operaciones completa y Analitica.
  El rol ADMIN ve todo excepto administracion de empresas (solo superadmin).

---

## 3. Hoja de Ruta

### Paso 1 — Verificacion del modelo MachineAsset
- Solicitar fleet/models.py y fleet/management/ via SFTP.
- Verificar campos actuales, relacion Company, migraciones aplicadas.
- Determinar si el campo activo existe o hay que crearlo.
- Estado: COMPLETADO (2026-05-04). Campo es_activo ya existia — renombrado a is_active via migracion 0003.

### Paso 2 — Migracion campo activo (si no existe)
- Anadir activo = BooleanField(default=True, db_index=True) a MachineAsset.
- Generar y aplicar migracion.
- Estado: DESCARTADO (2026-05-04). Campo ya existia en BD.

### Paso 3 — Comando import_cost_centers
- Neonato puro: fleet/management/commands/import_cost_centers.py
- Validar con --dry-run sobre el fichero actualizado entregado por el cliente.
- Ejecutar con --apply tras validacion.
- Estado: COMPLETADO (2026-05-04). 474 registros importados en produccion. Parser PDF reescrito con estrategia de ancla de fecha.

### Paso 4 — Vistas CRUD MachineAsset en el panel
- MachineAssetListView + vistas auxiliares Create/Update/Deactivate/Delete.
- Templates nuevos: panel/fleet/list.html + parciales HTMX.
- URLs en panel/urls.py.
- Estado: COMPLETADO (2026-05-04). Vistas CRUD operativas con HTMX. Incluye ReactivateView.

### Paso 5 — Reorganizacion del sidebar
- Revision del estado actual de _nav_items.html con el usuario.
- Acuerdo sobre la nueva estructura de secciones.
- PMA sobre _nav_items.html.
- Estado: COMPLETADO (2026-05-04). Nueva estructura de navegacion: IVR, WhatsApp, Taller, Administracion, Analitica. Icono sidebar actualizado a bi-building-fill.

### Paso 6 — Validacion E2E
- Verificar importacion del fichero actualizado contra BD de produccion.
- Verificar alta, edicion y baja desde el panel.
- Verificar que centros de gasto no resueltos en partes historicos son
  ahora asignables tras crear el centro correspondiente.
- Verificar nueva navegacion del panel para todos los roles.
- Estado: PENDIENTE. Validacion E2E parcial realizada durante la sesion 001.

---

## 4. Registro de Sesiones

| Sesion | Fecha | Pasos trabajados | Resumen |
|--------|-------|-----------------|---------|
| 001 | 2026-05-04 | 1,2(desc),3,4,5 + Nomenclatura | Renombrado completo de campos fleet a ingles (migracion 0003). Parser PDF import_machine_catalog reescrito con estrategia de ancla de fecha: 474 registros importados. Vistas CRUD MachineAsset con HTMX (List, Create, Update, Deactivate, Reactivate, Delete). Reorganizacion completa del sidebar del panel. |
| 003 | 2026-06-23 | Split fleet/views.py + mejoras CRUD + CdG EMPRESA_* + PCH→H07 | Split de vistas fleet de panel/views.py a fleet/views.py (neonato) y fleet/forms.py (neonato); re-exports en panel/views.py y panel/forms.py. Tabla CRUD mejorada: columnas Tipo, Contad. (iconos), badges EMP/PER, ordenación por columna via GET sort/dir. 5 CdG EMPRESA_* creados en producción (TALLER_MECANICO, TALLER_ELEVACION, TALLER_HUELVA, ALMACEN, DEPENDENCIAS) vía seed_empresa_assets.py (neonato). Fix DateInput format="%Y-%m-%d". Fix persistencia de filtros tras edición: hidden inputs renombrados a _f_* para evitar colisión con campos del formulario — diagnóstico con script JS de interceptación XHR (método empírico). PCH ejecutado: H12→H07. |

---

## 5. Hoja de Ruta para la Siguiente Sesion

H12 queda PAUSADO. PCH H12→H07 ejecutado (2026-06-23).

Trabajo pendiente cuando H12 vuelva a EN PROGRESO:

PRIORIDAD 0 — Validar borrado de CdG desde el panel (MachineAssetDeleteView).

PRIORIDAD 1 — Mejoras adicionales al CRUD:
  - Paginación ajustable (25/50/100 registros por página).
  - Indicador de uso mejorado.

PRIORIDAD 2 — Analítica de CdG (MachineAssetAnalyticsView):
  - Ya implementada en fleet/views.py — verificar que sigue funcionando
    tras el split (URL /panel/fleet/analytics/).

DEUDA TÉCNICA — Renombrado de campos en work_order_processor (Regla de Oro
del Idioma): maquina_raw→machine_raw, maquina_norm→machine_norm,
descripcion_averia→fault_description, reparacion→repair_notes,
fecha_incierta→uncertain_date. Requiere solicitar todos los archivos
afectados via SFTP antes de generar migraciones RenameField.
