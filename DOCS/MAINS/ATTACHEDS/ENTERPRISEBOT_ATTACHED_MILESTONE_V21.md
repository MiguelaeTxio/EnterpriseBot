# ENTERPRISEBOT_ATTACHED_MILESTONE_V21.md

## Hito 21 - Refactorizacion Arquitectonica: Split de panel/views.py

### Objetivo

Desmantelar el fichero monolitico panel/views.py que acumula 16.482 lineas
y 102 clases tras S051. Extraer los bloques funcionales a modulos independientes
para reducir el consumo de tokens en sesion, eliminar los tiempos de carga
excesivos y sentar las bases para la posterior elevacion de cada bloque a app
Django independiente siguiendo el patron establecido con la app analytics.

El objetivo final es panel/views.py < 200 lineas (solo imports y re-exports).

---

### Arquitectura Objetivo

Modulos resultantes del split:

  panel/views.py              -- < 200 lineas: solo imports y re-exports
  panel/views_operator.py     -- vistas de operario (~4.900 lineas)
  panel/views_workorders.py   -- vistas de supervisor/partes (~3.500 lineas)
  panel/views_fleet.py        -- vistas de flota (~820 lineas)
  panel/views_ivr.py          -- vistas IVR config (~1.500 lineas)
  panel/views_auth.py         -- vistas auth + WhatsApp (~740 lineas)

Total estimado extraible: ~11.460 lineas.
Residuo en panel/views.py: imports, re-exports y clases no clasificables.

---

### Estrategia de Split

El split se ejecuta fase por fase. Cada fase es una sesion independiente.
El criterio de exito de cada fase es: servidor recargado, 0 errores de
navegacion, django check --deploy sin errores nuevos.

PRINCIPIO CRITICO: panel/urls.py referencia las clases por nombre importado
desde panel.views. El split NO debe romper esas referencias. Cada modulo
nuevo re-exporta sus clases en panel/views.py para que panel/urls.py no
necesite cambios hasta que se eleve cada bloque a app independiente.

Patron de re-export obligatorio en panel/views.py:
  from panel.views_operator import (
      OperatorDashboardView,
      WorkOrderEntryFormView,
      ...
  )

---

### Fases de Ejecucion

#### Fase A - Auditoria y Clasificacion (S052 - primera accion obligatoria)

Antes de mover ninguna linea, generar el mapa completo de clases de
panel/views.py con su numero de linea de inicio y bloque funcional asignado:

  grep -n "^class " panel/views.py | tee /home/MiguelAeTxio/SWAP/class_map.txt

Clasificar cada clase en uno de los cinco modulos destino segun su dominio:
  - views_operator:   clases WorkOrderEntry*, Operator*, WorkshopAsset*,
                      WorkOrderDescription*, WorkdayGap*, WorkerSignup*
  - views_workorders: clases WorkOrder*, WorkdaySchedule*, AbsenceCategory*,
                      ExportTemplate*
  - views_fleet:      clases MachineAsset*, Fleet*, MaintenanceLog*
  - views_ivr:        clases Section*, Contact*, CallFlow*, PhoneNumber*,
                      CorporateVoiceProfile*, BlockedCaller*, DataCapture*,
                      IVR*, VoiceProfile*
  - views_auth:       clases PanelLogin*, Logout*, TrustDevice*,
                      CompanyUser*, Password*, OwnProfile*, CompanySettings*,
                      WhatsApp*

Cualquier clase no clasificable permanece en panel/views.py.

Entregar el mapa clasificado al usuario para validacion antes de ejecutar
ninguna extraccion.

#### Fase B - Extraccion views_operator.py (~4.900 lineas)

1. Identificar el bloque exacto de clases a extraer usando el mapa de Fase A.
2. Auditar imports necesarios: grep de todos los simbolos usados en el bloque
   que no se definen en el propio bloque.
3. Crear panel/views_operator.py como Neonato Puro (PEA) con:
   - Cabecera de imports minima y suficiente.
   - Las clases extraidas integras sin modificacion.
4. Eliminar las clases extraidas de panel/views.py (PMA).
5. Anadir re-exports al inicio de panel/views.py (PMA).
6. Verificar: python3 -m py_compile sobre ambos archivos.
7. django check --deploy: 0 errores nuevos.
8. Recargar servidor y verificar navegacion en las rutas afectadas.

#### Fase C - Extraccion views_workorders.py (~3.500 lineas)

Mismo procedimiento que Fase B aplicado al bloque de vistas de partes
y ordenes de trabajo.

#### Fase D - Extraccion views_fleet.py (~820 lineas)

Mismo procedimiento que Fase B aplicado al bloque de flota.

#### Fase E - Extraccion views_ivr.py (~1.500 lineas)

Mismo procedimiento que Fase B aplicado al bloque IVR config.

#### Fase F - Extraccion views_auth.py (~740 lineas)

Mismo procedimiento que Fase B aplicado al bloque auth + WhatsApp.

#### Fase G - Limpieza final

1. Verificar que panel/views.py < 200 lineas.
2. Eliminar imports huerfanos de panel/views.py.
3. Ejecutar django check --deploy y verificar 0 errores nuevos.
4. Recargar servidor y ejecutar verificacion E2E completa de navegacion:
   operario, supervisor, admin, IVR, flota, auth, WhatsApp.

---

### Trabajo Realizado

**Nota de reparación (2026-07-06):** este registro estaba desactualizado
-- decía "Fase A pendiente" cuando en realidad las Fases B y C ya se
habían ejecutado en una sesión anterior sin dejar constancia aquí.
Reparado tras verificación empírica del tamaño real de los archivos
(`wc -l`), no de memoria.

- **Fase B -- COMPLETADA.** `panel/views_operator.py` existe: 4.879
  líneas (vistas de operario: `WorkOrderEntryFormView`,
  `WorkOrderEntryConfirmView`, `WorkOrderEntryUploadView`,
  `OperatorDashboardView`, etc.).
- **Fase C -- COMPLETADA.** `panel/views_workorders.py` existe: 6.488
  líneas (vistas de supervisor/partes/presupuestos -- más grande que
  la estimación original de ~3.500, sin más detalle disponible sobre
  cuándo ni en qué sesión se ejecutó).
- **Fase D (`views_fleet.py`), Fase E (`views_ivr.py`), Fase F
  (`views_auth.py`) -- PENDIENTES.** Ninguno de los tres archivos
  existe todavía.
- **Fase G (limpieza final) -- PENDIENTE.** `panel/views.py` tiene
  actualmente 4.033 líneas -- lejos del objetivo `<200`, porque
  todavía contiene las clases de flota/IVR/auth sin extraer.

### Hoja de Ruta para la Siguiente Sesion (S052)

#### Contexto obligatorio previo

Auditar el numero de lineas actual de panel/views.py antes de comenzar:

  wc -l /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/views.py

**Reparación 2026-07-06:** confirmado en 4.033 líneas -- ver "Trabajo
Realizado" arriba. Las Fases A y B originales de este documento ya NO
aplican (B y C están hechas). Empezar directamente por la Fase D.

#### Paso 1 - Fase D: extraccion views_fleet.py (~820 lineas estimadas)

Mismo procedimiento que Fase B/C (ya validado en la práctica): mapa de
clases del bloque flota (`MachineAsset*`, `Fleet*`, `MaintenanceLog*`)
dentro de `panel/views.py`, auditoría de imports, extracción como
Neonato Puro, re-exports, verificación `py_compile` + `django check
--deploy` + recarga y navegación real.

#### Paso 2 - Fase E: extraccion views_ivr.py (~1.500 lineas estimadas)

Bloque IVR config (`Section*`, `Contact*`, `CallFlow*`, `PhoneNumber*`,
`CorporateVoiceProfile*`, `BlockedCaller*`, `DataCapture*`, `IVR*`,
`VoiceProfile*`). Mismo procedimiento.

#### Paso 3 - Fase F: extraccion views_auth.py (~740 lineas estimadas)

Bloque auth + WhatsApp (`PanelLogin*`, `Logout*`, `TrustDevice*`,
`CompanyUser*`, `Password*`, `OwnProfile*`, `CompanySettings*`,
`WhatsApp*`). Mismo procedimiento.

#### Paso 4 - Fase G: limpieza final

Solo tras D/E/F: verificar `panel/views.py < 200 líneas`, eliminar
imports huérfanos, `django check --deploy`, verificación E2E completa
de navegación (operario, supervisor, admin, IVR, flota, auth,
WhatsApp).
