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

- **Fase B -- COMPLETADA.** `panel/views_operator.py`: 4.879 líneas
  (vistas de operario).
- **Fase C -- COMPLETADA.** `panel/views_workorders.py`: 6.488 líneas
  (vistas de supervisor/partes/presupuestos).
- **Fase D -- DESCARTADA (2026-07-06).** Las clases `MachineAsset*`/
  `Fleet*`/`MaintenanceLog*` ya vivían en su propia app Django `fleet/`
  (`fleet/views.py`), no en `panel/views.py` -- nada que extraer.
  Confirmado por Miguel Ángel.
- **Fase E -- COMPLETADA (2026-07-06, primera sesión NFS de este
  hito).** `panel/views_ivr.py` creado: 1.986 líneas, 24 clases del
  bloque IVR config (`Section*`, `Contact*`, `CallFlow*`,
  `PhoneNumber*`, `CorporateVoiceProfile*`, `BlockedCaller*`,
  `DataCaptureSet*`, `SectionDefaultRoleView`, `InboundCallLog*`).
  Cabecera de imports auditada por grep contra el cuerpo extraído (no
  copia superset). `panel/views.py` bajó de 4.033 a 2.084 líneas.
- **Fase F -- COMPLETADA (misma sesión).** `panel/views_auth.py`
  creado: 1.966 líneas, las 18 clases restantes (`CompanyUser*`,
  `WorkerScheduleUpdateView`, `PanelLogin/LogoutView`, `TrustDevice*`,
  `PresenceStatusUpdateView`, `PanelDashboardView`,
  `PanelPasswordChangeView`, `WhatsApp*`, `OwnProfileView`,
  `CompanySettingsView`).
- **Fase G -- COMPLETADA de facto (misma sesión).** Al extraer las 18
  clases de la Fase F no quedaba lógica propia en `panel/views.py`, así
  que se reescribió directamente como archivo de solo imports y
  re-exports encadenados (B→C→E→F): **115 líneas**, por debajo del
  objetivo `<200`. Todos los imports de uso directo (django,
  `panel.mixins`, `panel.forms`, `ivr_config.models`,
  `whatsapp.models`, `work_order_processor`, `fleet`,
  `logging`/`plotly`) se eliminaron por quedar huérfanos.
  `panel/urls.py` sigue importando desde `panel.views` sin cambios
  (cadena de re-exports intacta, verificado por grep).

**Verificación realizada:** `python3 -m py_compile` OK en los 5 módulos
resultantes. **Verificación pendiente (fuera del alcance del modelo en
este flujo NFS, sin acceso de red a PythonAnywhere):** `django check
--deploy` y navegación E2E real (operario, supervisor, admin, IVR,
flota, auth, WhatsApp) tras el `git pull` en producción.

### Hoja de Ruta para la Siguiente Sesión

**H21 queda funcionalmente completo** salvo la verificación E2E real
en producción, que no puede ejecutar el modelo. Próxima sesión que
retome H21 (o continúe con H21 EN PROGRESO si se decide reactivar):

1. Confirmar que el `git pull` en PythonAnywhere no dio conflictos
   (ver script de despliegue entregado en la sesión de las Fases E/F/G).
2. Ejecutar `django check --deploy` en el servidor y recargar la app.
3. Navegación E2E real por las 7 áreas: operario, supervisor, admin,
   IVR, flota, auth, WhatsApp -- confirmar 0 errores de rutas rotas
   tras el split completo (`panel/views.py` ya no tiene lógica propia).
4. Si todo verifica correctamente, dar H21 por **CERRADO** y evaluar
   si procede la elevación de cada bloque a app Django independiente
   (mencionada en el Objetivo del hito como paso posterior, no
   incluida en el alcance de las Fases A-G).
