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
- Estado: PENDIENTE.

### Paso 2 — Migracion campo activo (si no existe)
- Anadir activo = BooleanField(default=True, db_index=True) a MachineAsset.
- Generar y aplicar migracion.
- Estado: PENDIENTE (condicional al resultado del Paso 1).

### Paso 3 — Comando import_cost_centers
- Neonato puro: fleet/management/commands/import_cost_centers.py
- Validar con --dry-run sobre el fichero actualizado entregado por el cliente.
- Ejecutar con --apply tras validacion.
- Estado: PENDIENTE.

### Paso 4 — Vistas CRUD MachineAsset en el panel
- MachineAssetListView + vistas auxiliares Create/Update/Deactivate/Delete.
- Templates nuevos: panel/fleet/list.html + parciales HTMX.
- URLs en panel/urls.py.
- Estado: PENDIENTE.

### Paso 5 — Reorganizacion del sidebar
- Revision del estado actual de _nav_items.html con el usuario.
- Acuerdo sobre la nueva estructura de secciones.
- PMA sobre _nav_items.html.
- Estado: PENDIENTE.

### Paso 6 — Validacion E2E
- Verificar importacion del fichero actualizado contra BD de produccion.
- Verificar alta, edicion y baja desde el panel.
- Verificar que centros de gasto no resueltos en partes historicos son
  ahora asignables tras crear el centro correspondiente.
- Verificar nueva navegacion del panel para todos los roles.
- Estado: PENDIENTE.

---

## 4. Registro de Sesiones

| Sesion | Fecha | Pasos trabajados | Resumen |
|--------|-------|-----------------|---------|

---

## 5. Hoja de Ruta para la Siguiente Sesion (001)

### Orden de trabajo sesion 001

PRIMERA ACCION — Solicitar y leer fleet/models.py y el directorio
fleet/management/ para verificar el estado actual del modelo MachineAsset
y las migraciones aplicadas. Determinar si el campo activo existe.

SEGUNDA ACCION — Acordar con el usuario la nueva estructura de navegacion
del panel antes de tocar ningun archivo. Solicitar _nav_items.html y revisar
el estado actual del sidebar. Proponer la nueva estructura de secciones y
esperar confirmacion explicita antes de implementar.

TERCERA ACCION — Implementar en este orden:
  1. Migracion campo activo si no existe (Paso 2).
  2. Comando import_cost_centers con --dry-run sobre el fichero del cliente (Paso 3).
  3. Vistas CRUD en el panel (Paso 4).
  4. Reorganizacion del sidebar tras acuerdo con el usuario (Paso 5).
  5. Validacion E2E (Paso 6).

NOTA CRITICA: el fichero actualizado de centros de gasto lo entrega el usuario
al inicio de la sesion. No iniciar el Paso 3 sin tener el fichero en mano.
