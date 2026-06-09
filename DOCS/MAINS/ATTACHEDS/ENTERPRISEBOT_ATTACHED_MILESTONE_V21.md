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

S052 (pendiente): Fase A -- auditoria y clasificacion de clases.

---

### Hoja de Ruta para la Siguiente Sesion (S052)

#### Contexto obligatorio previo

Auditar el numero de lineas actual de panel/views.py antes de comenzar:

  wc -l /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/views.py

#### Paso 1 - Fase A: mapa de clases

Ejecutar el grep de clasificacion y entregar el mapa al usuario:

  grep -n "^class " \
      /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/views.py \
      | tee /home/MiguelAeTxio/SWAP/class_map.txt

Clasificar cada clase en su modulo destino segun la matriz de Fase A.
Presentar la clasificacion al usuario para validacion. No extraer ninguna
clase hasta recibir confirmacion explicita.

#### Paso 2 - Fase B: extraccion views_operator.py

Con el mapa validado, ejecutar la extraccion del bloque operator siguiendo
el procedimiento de Fase B al completo. Una sola caja de modificacion por
prompt. Verificacion py_compile + django check + recarga tras cada fase.

#### Paso 3 - Fases C a G

Ejecutar en sesiones sucesivas segun disponibilidad. Cada fase es
autocontenida y verificable de forma independiente.
