# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V24.md

# Anexo de Hito V24 — Vacaciones, Ausencias y Control Horario
# (título anterior: "Vacaciones y Calendario"; ampliado y renombrado en S127)
# Proyecto: EnterpriseBot
# Fecha de inicio: 2026-07-14 (S018)

---

## 1. Visión General del Hito

Origen: funcionalidad especificada por Miguel Ángel al cierre de S017,
inicialmente registrada dentro de H23 por no tener hito propio todavía.
Dominio distinto (RRHH/planificación) al de H23 (documentación) — se abre
como hito independiente en S018, con app Django dedicada `hr_calendar`
(directriz arquitectónica de H22: cada dominio funcional nuevo va en app
propia, sin engordar apps existentes).

Dos piezas:

1. **Tarea automática de vacaciones** — al registrar el periodo de
   vacaciones de un operario/chófer, se genera automáticamente un bloque
   de ausencia (centro de gasto PERSONAL, categoría VACATION) en la
   última jornada laboral antes del inicio de las vacaciones.
2. **Aplicación de calendario** — vista con código de colores por día,
   visible para todos los roles autenticados, con alcance de datos según
   rol.

---

## 2. Hallazgo clave de S018 — infraestructura ya existente, NO reinventar

**Verificado empíricamente sobre el repositorio en esta sesión (principio
de método empírico — nunca se asume, se comprueba):**

- El centro de gasto **PERSONAL** ya existe como `MachineAsset` especial
  (`work_order_processor/management/commands/seed_personal_asset.py`,
  código reservado `PERSONAL`, creado por H10). El formulario digital de
  parte de trabajo (H7) ya reconoce este código y cambia el bloque de
  modo reparación a modo ausencia.
- El catálogo de motivos **ya es** `ivr_config.AbsenceCategory`
  (`work_order_processor/management/commands/seed_absence_categories.py`),
  gestionado por el supervisor desde el panel
  (`panel/views_workorders.py::AbsenceCategory*View`,
  `/panel/absence-categories/`). **El código `VACATION` ("Vacaciones")
  ya está en el catálogo estándar precargado** — no hace falta añadir
  nada al desplegable, contra lo que se apuntó al cierre de S017.
- El campo "donde normalmente iría la resolución de la avería" es
  `WorkdayGap.absence_category` (FK a `AbsenceCategory`) +
  `WorkdayGap.note` (texto libre) — mecanismo de Gate 4
  (`WorkdayGapResolutionView`, `work_order_processor/models.py` ~L1390).
  El bloque de ausencia manual ya sobreescribe `fault_description` con la
  etiqueta de la categoría (`panel/views_operator.py::_parse_entry_lines_from_post`,
  ~L465-520) — mismo patrón a replicar para el día de fin de vacaciones,
  probablemente en `repair_notes` o en un campo de la tarea generada
  automáticamente (**a confirmar el campo exacto al empezar — la sesión
  de S017 no llegó a tocar código de este hito, ver sección 4**).

**Consecuencia para la hoja de ruta:** el trabajo real de la pieza 1 no es
crear un mecanismo nuevo, es **automatizar la generación** de un bloque
que ya se puede crear manualmente — localizar el punto de entrada correcto
(señal de "última jornada antes de vacaciones", probablemente disparada
desde el alta/edición de un periodo de vacaciones en el nuevo módulo de
calendario) y llamar a la lógica de persistencia ya existente
(`save_blocks`/creación de `WorkdayGap` sintético, mencionada en el
docstring de `_parse_entry_lines_from_post`) con los valores fijos:
`machine_asset=PERSONAL`, `absence_category=VACATION`, duración 1 hora.

---

## 3. Especificación funcional (tal como la dio Miguel Ángel al cierre de S017, refinada en S018)

### 3.0. Decisión de diseño cerrada en S018 — `VacationPeriod` como fuente de verdad

Tras discutirlo explícitamente con Miguel Ángel: **`VacationPeriod` (app
`hr_calendar`) es un modelo propio**, no una fecha incrustada en la tarea
automática. Motivos (ver docstring completo en
`hr_calendar/models.py`):
1. La tarea automática vive dentro de un `WorkOrder`, cuyo ciclo de vida
   (`PENDING_GAPS`→`DONE`, correcciones) es ajeno al seguimiento de
   vacaciones.
2. Consultas directas (quién está de vacaciones, pintar el calendario,
   futura alarma WhatsApp) necesitan un `VacationPeriod.objects.filter(...)`
   plano, sin atravesar `WorkOrder`→`WorkOrderEntry`→`WorkOrderEntryLine`.
3. `WorkOrderEntryLine.repair_notes` es texto libre — apoyar el cálculo del
   calendario en parsear una fecha de ahí habría sido la misma fragilidad
   que el proyecto evita deliberadamente en otros sitios (código de
   máquina siempre impreso, nunca manuscrito).

**Construido en S018:** modelo `VacationPeriod` (app nueva `hr_calendar`,
registrada en `INSTALLED_APPS`) — `company`, `operator` (FK a
`CompanyUser`, cualquier rol, sin restricción a nivel de modelo),
`generated_entry_line` (FK opcional a `WorkOrderEntryLine`, trazabilidad
de la tarea automática una vez exista), `created_by`, `date_start`,
`date_end` (`CheckConstraint` que impone `date_end >= date_start`),
`created_at`. Migración `0001_initial` escrita a mano (sin acceso a
`makemigrations`, formato replicado de `machine_documents/0001_initial.py`).

### 3.1. Tarea automática de vacaciones
- Centro de gasto `PERSONAL`, categoría `VACATION` (ambos ya existentes,
  ver sección 2).
- Se dispara al guardar un `VacationPeriod` nuevo — se genera en la última
  jornada de trabajo antes de `date_start` (generación automática, no
  manual).
- Duración automática: 1 hora.
- `repair_notes` de la tarea puede mencionar la fecha de fin en texto
  legible para el operario/supervisor, pero **nada la parsea** — el dato
  real vive en `VacationPeriod.date_end` (ver 3.0).
- **No cuenta en el cómputo de horas** — excluir explícitamente de
  cualquier agregado de horas trabajadas/facturables (localizar todos los
  puntos de agregación en `analytics/` y en el propio `work_order_processor`
  que suman horas por operario/periodo, y excluir bloques con
  `machine_asset.code == PERSONAL` y `absence_category.code == VACATION`
  — verificar si el resto de categorías PERSONAL ya se excluyen o si es
  un caso nuevo).

### 3.2. Aplicación de calendario
- Visible para todo el mundo (todos los roles autenticados).
- `ADMIN`/`SUPERVISOR`: filtro por operario/chófer, puede ver el
  calendario de cualquiera.
- `WORKSHOP` (mecánico) / `DRIVER` (chófer): solo su propio calendario,
  sin selector.
- Código de colores por día (regla exacta cerrada en S018 — nivel de
  detalle: existencia de tarea real ese día, no proporción de horas):
  - **Azul (normal)** — existe al menos una `WorkOrderEntryLine` de ese
    día con centro de gasto distinto de `PERSONAL` (hay tarea real) Y NO
    hay ningún `WorkdayGap` resuelto ese mismo día — jornada completa.
  - **Azul celeste** — mismo caso anterior (hay tarea real) PERO además
    existe un `WorkdayGap` resuelto ese día (ausencia parcial de
    `PERSONAL`, p. ej. faltan 2-3 horas) — jornada incompleta, no llega
    a las 8 horas. Añadido en S018 a petición de Miguel Ángel para
    distinguir visualmente este caso del día completo.
  - **Verde** — día de vacaciones (derivado de `VacationPeriod`, sección 3.0).
  - **Naranja** — ese día NO hay ninguna tarea real (todas las líneas,
    si las hay, son `PERSONAL`) y sí hay una `AbsenceCategory` distinta
    de `VACATION` cubriéndolo — el día completo es ausencia por motivo
    personal (catálogo: el mismo `AbsenceCategory` ya usado al elegir
    `PERSONAL` como centro de gasto en una `WorkOrderEntryLine` — "baja"
    no es una sub-lista aparte, es cualquier categoría que no sea
    `VACATION`).
  - **Rojo** — día laborable (según `WorkdaySchedule` del operario) sin
    ninguna de las anteriores: ni tarea real, ni ausencia, ni
    vacaciones, ni festivo — laguna sin explicar.
  - **Amarillo** — festivo (fuente: `Base.labor_calendar`, sección 3.3 —
    ya no es una pregunta abierta, resuelta en Q4).

### 3.3. Agrupación por periodos — decisión cerrada en S018

El calendario **reutiliza `ivr_config.WorkPeriodGroup`** (periodo
administrativo de empresa ya existente, creado a mano por el supervisor —
no hay ningún ciclo "21 al 20" hardcodeado en el código, es una
convención operativa que Miguel Ángel aplica al crear esos grupos) en vez
de inventar un concepto de periodo nuevo. Regla de titulado, tal como la
especificó Miguel Ángel:
- El `WorkPeriodGroup` más reciente con `is_closed=False` → **"Periodo
  activo: meses {mes inicio} y {mes fin}"**.
- Cualquier `WorkPeriodGroup` con `is_closed=True` → **"Periodo
  liquidado: meses {mes inicio} y {mes fin}"**.
- Si no hay ningún `WorkPeriodGroup` cubriendo el rango consultado, cae a
  mes natural (calendario estándar) — comportamiento por defecto, a
  validar con Miguel Ángel si hace falta ajustarlo cuando se construya la
  vista.

---

## 4. Preguntas Abiertas — Resolver al Empezar la Sesión que Retome Este Hito

1. ~~Dónde se registra el periodo de vacaciones~~ — **RESUELTO en S018**,
   ver sección 3.0. Modelo `VacationPeriod` ya construido.
2. ~~Campo exacto donde va el día de fin de vacaciones~~ — **RESUELTO en
   S018**: no hace falta ningún campo estructurado en la tarea —
   `VacationPeriod.date_end` es la fuente de verdad (ver 3.0).
   `repair_notes` de la tarea es solo texto legible, no se parsea.
3. ~~Catálogo de motivos de "baja"~~ — **RESUELTO en S018**: no es una
   sub-lista aparte, es el mismo catálogo `AbsenceCategory` ya usado al
   elegir `PERSONAL` como centro de gasto (menú "Categorías de ausencia"
   del panel) — cualquier categoría que no sea `VACATION` cuenta como
   naranja, ver regla completa en sección 3.2.
4. ~~Fuente de festivos~~ — **RESUELTO en S018**: se reutiliza
   `budgets.models.Base.labor_calendar` (ya sincronizado desde
   calendariosnacionales.com vía `sync_base_calendars`, H16/H18) — no
   hace falta modelo `Holiday` nuevo. Requería cerrar un hueco real:
   `CompanyUser` no tenía ningún campo de pertenencia a base aplicable a
   `WORKSHOP`/`DRIVER` (solo `workshop_family`, exclusivo de
   `WORKSHOPBOSS`). Construido en S018: `CompanyUser.base` (FK a
   `budgets.Base`, referencia por string para evitar import circular) +
   comando `hr_calendar.management.commands.assign_operator_bases`
   (idempotente, `--dry-run` por defecto) que crea las bases Maqueda/
   Huelva y asigna cada operario/chófer según la lista dada por Miguel
   Ángel (dos mecánicos de Huelva + una supervisora: Carlos Bas y David
   Márquez confirmados, María sin apellido confirmar — el comando se
   niega a ejecutar hasta entonces, ver su docstring). El resto de
   operarios/chóferes activos van a Maqueda por defecto.
5. ~~Puntos de agregación de horas a excluir~~ — **RESUELTO en S018**:
   NO se excluye nada del resto de categorías `PERSONAL` (médico,
   asuntos propios, etc.) — cuentan como horas trabajadas normales,
   incluso a efectos de horas extra, comportamiento ya correcto y sin
   tocar. **Únicamente la hora fantasma de la tarea automática
   `VACATION`** (sección 3.1) debe quedar excluida en los tres puntos
   localizados por código real: `work_order_processor/services.py`
   ~L1534 (suma diaria para Excel), `work_order_processor/services.py`
   ~L2737 (horas extra sobre 8h) y `analytics/views.py` ~L2245
   (denominador de coste). Como la generación automática de la tarea
   todavía no está construida (paso 2 de la hoja de ruta), no hay nada
   que tocar en estos tres puntos ahora mismo — queda como requisito
   obligatorio del paso 2, no como tarea independiente.
   **Relacionado pero fuera de alcance de H24:** el reparto del coste
   de las horas reales de vacaciones (y del resto de `PERSONAL`) como
   sobrecoste entre el resto de centros de gasto queda registrado como
   deuda técnica en `ENTERPRISEBOT_MASTER_DOCUMENT.md` sección 4.7 — no
   se aborda en esta sesión ni en este hito, a petición explícita de
   Miguel Ángel.
6. ~~Cómo agrupar el calendario en periodos~~ — **RESUELTO en S018**, ver
   sección 3.3 (reutiliza `WorkPeriodGroup`).
7. ~~Apellido de "María"~~ — **RESUELTO en S018**: confirmado por
   captura de panel de Miguel Ángel que `MARIA` no tiene apellido en el
   sistema y su rol real es `SUPERVISOR` (no `WORKSHOPBOSS`, como se
   había asumido). `assign_operator_bases` corregido: `HUELVA_MEMBERS`
   usa `"Maria"` (nombre de pila, emparejamiento seguro por nombre
   completo concatenado) y `SUPERVISOR` añadido a
   `BASE_ASSIGNABLE_ROLES`. Comando listo para ejecutar (primero sin
   `--apply` para revisar, luego con `--apply`).

---

## 5. Hoja de Ruta para la Siguiente Sesión

### COMPLETADAS EN S018

Sesión que abrió el hito (desvío desde H23, a petición explícita de
Miguel Ángel — "cerrar la decisión" significaba implementar el
calendario). Resumen narrativo completo en el mensaje del commit de
cierre de esta sesión; aquí solo el registro estructurado para consulta
rápida en sesiones futuras.

**Decisiones de diseño cerradas:**
- `VacationPeriod` (app nueva `hr_calendar`) como modelo propio y única
  fuente de verdad del periodo de vacaciones — no una fecha incrustada
  en la tarea automática (motivos completos en sección 3.0 y en el
  docstring de `hr_calendar/models.py`).
- `CompanyUser.base` (FK a `budgets.Base`, string reference) para cerrar
  el hueco de pertenencia a base física, inexistente hasta ahora para
  `WORKSHOP`/`DRIVER` (motivos en sección 3.0/pregunta 4).
- Calendario reutiliza `ivr_config.WorkPeriodGroup` para los periodos
  (titulado "Periodo activo"/"Periodo liquidado"), en vez de un ciclo
  "21-20" hardcodeado que nunca existió como tal.
- Regla completa de colores del calendario cerrada (sección 3.2):
  azul/azul celeste/verde/naranja/rojo/amarillo, todos con criterio
  exacto verificado contra el modelo de datos real.
- Fuente de festivos: se reutiliza `budgets.models.Base.labor_calendar`
  (ya sincronizado vía `sync_base_calendars`, H16/H18) — sin modelo
  `Holiday` nuevo.
- Catálogo de "baja" (naranja): el mismo `AbsenceCategory` ya usado al
  elegir `PERSONAL` como centro de gasto — sin sub-lista aparte.
- Agregación de horas: solo la hora fantasma de la tarea `VACATION`
  queda excluida (tres puntos localizados por código real, sección 3.1/
  pregunta 5); el resto de `PERSONAL` sigue contando como hoy, sin
  cambios.
- Deuda técnica nueva registrada en `ENTERPRISEBOT_MASTER_DOCUMENT.md`
  sección 4.7: reparto futuro del coste de `PERSONAL` como sobrecoste
  entre el resto de centros de gasto — anotada, explícitamente no
  abordada por decisión de Miguel Ángel.

**Construido:**
- Modelo `VacationPeriod` con migración `0001_initial` escrita a mano.
- Campo `CompanyUser.base` con migración `0042_companyuser_base`.
- Comando `hr_calendar.management.commands.assign_operator_bases`
  (idempotente, `--dry-run` por defecto).
- `whatsapp/services.py::OnboardingService` ampliado para preguntar la
  base al dar de alta un empleado nuevo.
- Master document actualizado: sección 1 (visión general desactualizada)
  reescrita con mapa de apps real, sección 2 (modelo Live IVR)
  corregida para coincidir con la 4.1, sección 4.7 (deuda técnica)
  añadida.

**Ejecutado en producción (Grupo Álvarez, pk=1):** base `Maqueda`
(pk=75, ya existía) y `Huelva` (pk=76, creada en esta sesión). 14
operarios/chóferes asignados — 3 a Huelva (Carlos Bas Blanco, David
Contreras Marquez, `MARIA` sin nombre/apellido en el sistema,
emparejada por username), 11 a Maqueda. Calendario laboral de Huelva
sincronizado — 14 festivos obtenidos para 2026.

**Incidencias reales encontradas y resueltas, todas en el propio
comando `assign_operator_bases` antes de aplicarlo:**
- Primera versión de `HUELVA_MEMBERS` tenía nombres incompletos
  ("Carlos Bas"/"David Marquez") — los apellidos reales son más largos
  ("Bas Blanco"/"Contreras Marquez"), detectado por el propio dry-run
  (0 coincidencias en el primer intento).
- `MARIA` resultó tener nombre Y apellido vacíos en el sistema (no
  vacía de apellido nada más, que era la asunción inicial) — dos
  `SUPERVISOR` en blanco indistinguibles por nombre en el dry-run;
  resuelto emparejando por `username="MARIA"` en vez de nombre, tras
  confirmación por captura de panel de Miguel Ángel.
- Rol real de `MARIA` es `SUPERVISOR`, no `WORKSHOPBOSS` como se había
  asumido — `BASE_ASSIGNABLE_ROLES` corregido para incluirlo.
- Bug propio en el comando: comparación `operator.base_id ==
  getattr(target_base, "pk", None)` daba `None == None` → `True`
  cuando la base destino todavía no existía (caso Huelva antes de
  `--apply`), contando en silencio a los 3 miembros de Huelva como "ya
  correctos" y ocultándolos del listado de dry-run. Detectado
  comparando la salida real contra lo esperado, corregido antes de
  aplicar nada.

### Hoja de ruta — continuación de este hito

1. Implementar la generación automática de la tarea de vacaciones al
   guardar un `VacationPeriod` (dispara `WorkdayGap`/bloque `PERSONAL`
   sintético, ver sección 2) — no crear un mecanismo de persistencia
   paralelo. Incluye aplicar la exclusión de la hora fantasma en los
   tres puntos localizados en la pregunta 5 de la sección 4.
2. Formulario de alta/edición de `VacationPeriod` en el panel (rol a
   confirmar — candidato natural ADMIN/SUPERVISOR).
3. Vista de calendario con el código de colores completo (sección 3.2)
   y la agrupación por `WorkPeriodGroup`/mes natural (sección 3.3), con
   el alcance de datos por rol ya descrito.
4. Una vez completado H24 (o cuando Miguel Ángel decida pausarlo), la
   siguiente parada es **retomar H23** (Documentación de Centros de
   Gasto, pausado desde S018 con su hoja de ruta intacta) — orden
   indicado explícitamente por Miguel Ángel al cierre de esta sesión.

---

### COMPLETADAS EN S019 (2026-07-15)

**Corrección de flujo — S019 sobre el diseño S018:** el anexo dejaba sin
cerrar del todo ("probablemente") quién dispara la generación de la
tarea automática de vacaciones. Se había interpretado como
"CRUD de panel: supervisor crea el periodo → se genera la tarea", y se
construyó así (pasos 1 y 2 de la hoja de ruta anterior). Miguel Ángel
corrigió en esta sesión: el flujo real es el inverso — el propio
operario añade su tarea de vacaciones (PERSONAL, categoría Vacaciones,
1 hora) en su parte digital normal, en su última jornada laboral,
indicando ahí mismo la fecha de fin; de esa tarea real se deriva el
`VacationPeriod`, nunca al revés. Origen del incidente y la directriz
4.8 (fidelidad absoluta a instrucciones explícitas), añadida al
documento maestro en esta misma sesión.

**Paso 1 (generación automática) construido dos veces:** primero como
CRUD-driven (`hr_calendar.services.generate_vacation_task`, crea un
`WorkOrder` sintético nuevo) — se mantiene en el código como vía
secundaria/administrativa del CRUD, Miguel Ángel decide dejarla sin
usarse por defecto. Después, la vía real:
`hr_calendar.services.register_vacation_period_from_line`, que deriva
el `VacationPeriod` de la línea real que el operario mete en su parte,
idempotente por (operario, date_start) en vez de por línea exacta
(necesario porque el guardado progresivo del operario borra y recrea
líneas en cada reguardado). Enganchada en los tres puntos reales donde
se persiste una línea PERSONAL/ausencia: cierre de
`WorkOrderEntryConfirmView`, `save_blocks` de `WorkOrderEntryFormView`,
y el cierre directo de esa misma vista (un tercer camino de
persistencia que no crea `WorkdayGap`, detectado en esta sesión).

**Paso 2 (CRUD) construido según el diseño original** —
`hr_calendar/views.py` (`VacationPeriodListView/Create/Update/Delete`),
`/panel/vacaciones/gestion/`. Se mantiene como vía secundaria a
petición de Miguel Ángel ("me da igual que haya CRUD o no, lo
importante es el flujo real").

**Paso 3 (calendario) construido según sección 3.2/3.3, confirmadas sin
cambios en esta sesión:** `hr_calendar.services.compute_calendar_days`
(motor de color por día) y `resolve_period_group_for_calendar`
(agrupación por `WorkPeriodGroup`, navegación anterior/siguiente).
`VacationCalendarView` en `/panel/vacaciones/` (raíz), visible a todo
rol autenticado, con selector de operario para ADMIN/SUPERVISOR.
Enlace "Calendario" en la sidebar: Administración para
ADMIN/SUPERVISOR/WORKSHOPBOSS, Mi perfil para WORKSHOP/DRIVER — mismo
enlace, dos ubicaciones según rol, a petición explícita de Miguel Ángel
tras plantearle que el anexo exige visibilidad universal.

**Incidencias reales de esta sesión, todas corregidas y verificadas en
producción con datos reales (git log -1 / manage.py check / consultas
a BD y logs, nunca solo el semáforo verde de GitHub Actions):**

- `FieldError` en el calendario: `absence_category` vive en
  `WorkdayGap`, no en `WorkOrderEntryLine` — corregido, la consulta de
  "naranja" (ausencia no vacacional) ahora consulta el modelo correcto.
- Sidebar rota en las tres vistas de `hr_calendar`: faltaba
  `company_user`/`company` en el contexto de `render()` — `_nav_items.html`
  depende de esa variable de contexto a secas, no de
  `request.user.company_user`.
- `ImportError` en producción **dos veces** por el mismo patrón de
  fondo (nombre correcto, enganchado al eslabón equivocado de una
  cadena de imports/reexports): `generate_vacation_task` borrada por
  completo por un `str_replace` que usó su propia firma como ancla de
  inserción (ya había pasado una vez antes en la misma sesión con la
  firma, esta vez con la función entera — restaurada literalmente
  desde `git show` del último commit bueno, no reescrita de memoria);
  y `WorkOrderDetailView` (vista nueva de detalle de solo lectura,
  ver más abajo) que se quedó sin añadir al re-export de
  `panel/views.py`, el hub real de imports de `panel/urls.py` desde el
  split de H21.
- Bug real en `form_entry_assets.js`, no de H24: la validación de envío
  del formulario (Gate 2) comparaba el texto completo del campo
  "Máquina o Sección" contra el código exacto `"PERSONAL"`, pero el
  autocompletado rellena ese campo con `"PERSONAL — Personal"`
  (código + descripción) — la comparación fallaba y el bloque se
  trataba como reparación normal, exigiendo descripción de avería.
  Bloqueaba el flujo real completo. Corregido extrayendo la parte antes
  de `" — "`, mismo criterio que ya usa la Pasada 3 de resolución de
  máquina en el servidor.
- Segunda copia, sin detectar hasta esta sesión, de la validación Gate 1
  de integridad en `WorkOrderEntryFormView` (la vista real de "Nuevo
  parte") — exigía descripción de avería y de reparación **siempre**,
  para cualquier bloque, sin ninguna rama para bloques PERSONAL/ausencia,
  a diferencia de la copia de `WorkOrderEntryConfirmView` que sí la
  tenía desde el commit anterior. Bloqueaba el flujo real desde el
  único sitio donde el operario lo usa a diario. Corregida con la misma
  rama que la primera copia.
- Autorrelleno automático de H.C./H.F. (1 hora fija desde la última
  hora de trabajo) al seleccionar Vacaciones — pedido explícitamente
  tras el caso real de Antonio Fontalba Serón (H.C.=H.F.=15:00 disparaba
  "H.F. debe ser posterior a H.C."). Bug propio detectado y corregido
  antes de desplegar: los campos H.C./H.F. no tienen atributo `id`, solo
  `name` — el primer intento con `getElementById` no habría funcionado
  nunca.
- **Fuera de alcance de H24, corregido igualmente por instrucción
  explícita de Miguel Ángel** (directriz "errores detectados fuera de
  alcance", añadida a la memoria de esta sesión): el patrón de exponer
  el texto crudo de una excepción (`{exc}`) directamente en mensajes de
  usuario, detectado en 17 sitios de `panel/views_operator.py`,
  `panel/views_workorders.py`, `analytics/views.py`,
  `machine_documents/tasks.py`, `work_order_processor/services.py`,
  `work_order_processor/tasks.py`, `budgets/views.py` (7 sitios,
  archivo sin `logger` hasta esta sesión) y `budgets/services.py` (4
  sitios, todos en `RouteCalculationError`, cuyo mensaje llega tal cual
  a la interfaz vía `str(exc)` en las vistas que la capturan). En todos
  los casos el detalle técnico completo sigue disponible únicamente en
  el log del servidor.
- Vista de detalle de solo lectura para Partes Digitales (`WorkOrderDetailView`,
  `/panel/work-orders/<pk>/detail/`), fuera de alcance de H24 pero
  pedida y resuelta en la misma sesión: botón "Ver" en las pestañas
  Revisados e Histórico (Pendientes no lo necesita, ya tiene
  "Editar/Revisar"). Acceso restringido a ADMIN/SUPERVISOR/WORKSHOPBOSS,
  impuesto también en la vista, no solo ocultando el botón.

**Diagnóstico de dos casos reales de "parte no encontrado" (Antonio
Fontalba Serón 22/06/2026, Pablo Cañamero 03/07/2026):** verificado con
consultas reales a BD, `error.log`, `server.log` y `access.log` — cero
rastro en las cuatro fuentes en ambos casos. Conclusión: la petición
nunca llegó al servidor esos días, no es un fallo del sistema. Pendiente
de confirmar con los propios operarios si hubo intento real o ausencia
real que regularizar a mano.

**Fuera de código, decisión de infraestructura para H23 (documentación
de centros de gasto) y H10 (repuestos), relevante para cuando se
retome H23:** Miguel Ángel decide migrar el almacenamiento programático
de Google Drive (OAuth con cuenta personal) a **Google Cloud Storage**
(clase Standard, región europea, cuenta de servicio sobre el proyecto
de GCP ya existente que paga Gemini/Vertex AI) — no Google Workspace.
Motivo: acceso puramente programático sin necesidad de cuentas de
usuario ni entrada por navegador, facturación por consumo real sin
escalones fijos. Implica reescribir `spare_parts/gdrive_service.py`
(reutilizado en repuestos H10, fotos de tarea H7, documentación H23)
para hablar con la API de Cloud Storage en vez de la de Drive —
**no abordado en esta sesión**, queda como tarea de desarrollo futura,
sin fecha decidida todavía.

**Bug detectado y verbalizado al cierre de esta sesión, sin corregir
todavía (ver hoja de ruta siguiente):** `WorkPeriodGroupCreateView`
marca todo grupo nuevo como activo (`is_closed=False` por defecto) sin
comprobar si ya hay otro activo, y `resolve_period_group_for_calendar`
(construida en esta misma sesión, paso 3) coge "el más reciente
abierto" — con dos grupos abiertos a la vez, el calendario muestra el
nuevo en vez del real. Diagnosticado con Miguel Ángel al final de la
sesión; el rediseño completo (cálculo de periodo 21–20 al vuelo sin
tabla, avance de "activo" solo por liquidación explícita, cómputo de
horas extra sumando todos los periodos sin liquidar con partes reales,
visor de horas extra por periodo) se deja para sesión nueva por
decisión explícita de Miguel Ángel ("lo veo más coherente empezarlo
limpio").

### COMPLETADAS EN S020 (2026-07-15)

**Los 5 puntos de la "Tarea principal" quedaron cerrados en esta
sesión** (rediseño de `WorkPeriodGroup`, motivado por el bug de
activación automática sin control detectado al cierre de S019):

1. **Cálculo de periodo por fecha, sin precrear filas (commit
   `cd5d14b`):** `compute_period_bounds_for_date`/
   `ensure_work_period_group_for_date` nuevas en `ivr_config/models.py`
   -- ciclo fijo 21-al-20 calculado al vuelo, la fila se asegura solo
   la primera vez que hace falta (por ahora, la resolución por defecto
   del calendario). Al crearse, `WorkPeriod` se asigna automáticamente
   a todos los operarios WORKSHOP activos (Opción A confirmada por
   Miguel Ángel: se mantiene el registro individual por operario,
   necesario para Analítica, pero la asignación deja de ser manual).
   Eliminadas `WorkPeriodGroupCreateView`/`WorkPeriodGroupAddOperatorView`
   y sus botones/modales en los tres templates afectados -- confirmado
   explícitamente por Miguel Ángel que ni siquiera hace falta un botón.
2. **Activación solo por liquidación explícita + tercer estado
   (mismo commit):** nuevo `WorkPeriodGroup.status`/`status_label`
   (ACTIVE / PENDING_LIQUIDATION / LIQUIDATED) -- a petición explícita
   de Miguel Ángel durante la sesión: el periodo activo es siempre
   aquel cuya fecha de hoy cae dentro de sus márgenes (21-20), sin
   importar `is_closed`; pueden convivir varios periodos sin liquidar
   a la vez (el que ya venció por fecha sin liquidar pasa a
   `PENDING_LIQUIDATION`, no es un bug). Aplicado en el calendario y en
   la pestaña Períodos/detalle de periodo del panel.
3. **Horas extra acumuladas pendientes (commit `205346e`):** el
   resumen del operario ya no mira "el periodo activo" único, suma
   TODOS los `WorkPeriod` sin liquidar (`is_closed=False`) del
   operario, tengan o no partes reales -- criterio confirmado por
   Miguel Ángel. Al liquidar un periodo, sus horas dejan de contar y
   pasan a histórico.
4. **Visor de horas extra por periodo (mismo commit):** dentro del
   detalle de cada `WorkPeriodGroup`, confirmado por Miguel Ángel.
   `WorkPeriodGroupDetailView` pasa de `SupervisorAccessMixin` a
   `CompanyUserRequiredMixin` con control de acceso por objeto:
   ADMIN/SUPERVISOR/WORKSHOPBOSS ven gestión completa + selector de
   operario (`?operator_pk=`); WORKSHOP/DRIVER solo pueden abrir un
   periodo al que pertenezcan y ven directamente sus propias horas
   extra, sin lista de operarios ni acciones de gestión. Nuevo enlace
   "Mis periodos" en la pestaña Pendientes de Partes Digitales.
5. **`resolve_period_group_for_calendar` (commit `cd5d14b`):**
   reescrita para usar `ensure_work_period_group_for_date` en vez de
   "el más reciente `is_closed=False`" -- resuelto de facto al mismo
   tiempo que el punto 1, sin necesitar un paso aparte.

**Fuera de H24, corregido en la misma sesión (directriz de errores
fuera de alcance):** código muerto duplicado en `hr_calendar/services.py`
(cuerpo huérfano de `generate_vacation_task` tras el `return` de
`resolve_period_group_for_calendar`); `WorkPeriodLockView`
(`panel/views_workorders.py`) apuntaba a una URL inexistente
(`panel:work_period_list`) como fallback -- habría dado `NoReverseMatch`
sin `HTTP_REFERER`, corregido al fallback real.

**Comprobación pedida por Miguel Ángel:** el CRUD secundario de
vacaciones (`VacationPeriodListView`/`Create`/`Update`/`Delete`,
`vacation_periods.html`) revisado línea a línea -- no depende en
absoluto de `WorkPeriodGroup`, solo gestiona `VacationPeriod`. Sigue
bien tal cual, sin cambios. El único punto que sí dependía de
`WorkPeriodGroup` es el calendario (`VacationCalendarView`), ya
actualizado en el punto 5.

**Desvío puntual a H10 (Caso A, sin PCH, marcador `EN PROGRESO` sin
mover) -- incidencia real de albaranes de proveedor, ver
`ENTERPRISEBOT_ATTACHED_MILESTONE_V10.md` fila S020 para el detalle
completo:** código de máquina ahora también válido si viene delimitado
(`#`/`*`/`"`) dentro de una línea de artículo, cuando el proveedor no
usa Observaciones; nuevo fallback por palabra clave
(repuesto/stock/almacén) a `WAREHOUSE` sin diferenciar, cuando no hay
código en ninguna fuente -- commit `2aa236c`.

**Incidencia nueva reportada por Miguel Ángel al cierre, sin
diagnosticar todavía en esta sesión (ver hoja de ruta abajo):**
captura de pantalla mostrando que, en "Subir Documentación de Centro
de Gasto" (`/panel/documentacion-centros-gasto/subir/`), un usuario
`alvarez_admin` con rol ADMIN ve el sidebar de operario de taller
(WORKSHOP) en vez del sidebar de administrador -- no investigado
todavía, primera tarea de la siguiente sesión.

**Bug real detectado y corregido justo tras el primer cierre de esta
sesión (commit `d27fec1`), a partir de una captura de pantalla de
Miguel Ángel:** la pestaña Períodos de Partes Digitales mostraba
literalmente en pantalla el texto de un comentario de template. Causa
raíz: la sintaxis `{# ... #}` de Django solo admite una línea -- un
comentario que ocupa varias líneas no se trata como comentario y se
renderiza tal cual. El causante era un comentario introducido en el
propio commit `cd5d14b` de esta sesión (`admin_history.html`).
Corregido, y tras un barrido completo del repositorio con el mismo
patrón (directriz de errores fuera de alcance), otros dos bugs
preexistentes reales, no introducidos hoy: `delivery_note_detail.html`
(S014-H10, dentro de `<head>`, no visible pero inválido) y
`panel/templates/panel/password/_field_pw.html` (visible en la
pantalla de cambio de contraseña). Verificado que no queda ningún
`{# #}` multilínea más en todo el repositorio.

### Hoja de Ruta para la Siguiente Sesión

### Cierre de Hito (S021) -- hito pausado vía PCH, ver ENTERPRISEBOT_ANNEX_ROUTER.md

**Prioridad 1 de la hoja de ruta anterior, resuelta en S021:**
1. Diagnosticada y corregida la incidencia de sidebar de `alvarez_admin`
   -- causa raíz: `MachineDocumentBatchUploadView` (GET y las dos ramas
   de error de POST) era la única vista de todo el panel que no pasaba
   `company_user` al contexto del template, dejando `_nav_items.html` sin
   poder gatear ningún bloque por rol. Corregido en `machine_documents/
   views.py` (commit `e2a5ecc`) -- ver anexo H23 para el detalle, la
   vista pertenece a esa app.

**Funcionalidad de vacaciones/calendario:** completa desde S020, sin
trabajo propio pendiente. El único punto que quedaba anotado sin fecha
(migración Google Drive → Google Cloud Storage) no es específico de
H24 -- afecta también a H7 (`TaskPhoto`), H10 (`DeliveryNote`) y H23
(`MachineDocument`, construido en esta misma sesión) -- pasa a
rastrearse como primera tarea de H23 (ver anexo V23, confirmado
explícitamente por Miguel Ángel al cierre de S021: "siguiente sesión
migramos" -- antes que cualquier otra pieza nueva de H23).

**Pendiente sin fecha, no de H24 específicamente:** deuda técnica de
reparto de coste de `PERSONAL` (sección 4.7 del master document) --
explícitamente no abordada por decisión de Miguel Ángel.

---

## 6. Registro de Sesiones

| Sesión | Fecha | Trabajo realizado |
|---|---|---|
| S018 | 2026-07-14 | Hito creado (desvío desde H23). App `hr_calendar`, modelo `VacationPeriod`, campo `CompanyUser.base`, comando `assign_operator_bases` ejecutado en producción (14 operarios/chóferes, bases Maqueda/Huelva), onboarding WhatsApp ampliado, y las 7 preguntas de la sección 4 resueltas. Ver "COMPLETADAS EN S018" arriba para el detalle completo. Siguiente sesión: construir la generación automática de la tarea, el formulario de alta y la vista de calendario (hoja de ruta arriba). |
| S019 | 2026-07-15 | Pasos 1-3 de la hoja de ruta construidos, con corrección de flujo a mitad de sesión (directriz 4.8): la generación automática se deriva de la tarea real del operario, no de un CRUD de supervisor. Calendario con código de colores y agrupación por `WorkPeriodGroup` construido y desplegado. Ocho incidencias reales encontradas y corregidas en producción (dos `ImportError` que tumbaron el despliegue, `FieldError`, sidebar rota, dos bugs de validación que bloqueaban el flujo real, autorrelleno de H.C./H.F., patrón de errores en crudo en 17 sitios fuera de H24). Vista de detalle de solo lectura para Partes Digitales añadida (fuera de H24). Diagnosticados con datos reales dos casos de "parte no encontrado" sin causa técnica. Decidida la migración futura de Google Drive a Google Cloud Storage (sin implementar). Detectado al cierre un bug real en `WorkPeriodGroup` (activación automática sin control) que Miguel Ángel decide abordar en sesión nueva junto con un rediseño más amplio (cálculo de periodo 21-20 al vuelo, horas extra acumuladas, visor por periodo) — ver "COMPLETADAS EN S019" y la hoja de ruta arriba para el detalle completo. |
| S020 | 2026-07-15 | Rediseño completo de `WorkPeriodGroup` cerrado (5/5 puntos de la tarea principal, commits `cd5d14b`/`205346e`); CRUD de vacaciones comprobado y confirmado correcto sin cambios; desvío puntual a H10 por incidencia real de albaranes (commit `2aa236c`, ver anexo H10 fila S020); bug real de comentarios Django `{# #}` multilínea rotos detectado y corregido tras el primer cierre (commit `d27fec1`, 3 sitios); nueva incidencia de sidebar reportada por Miguel Ángel, sin diagnosticar todavía -- primera tarea de la siguiente sesión. Ver "COMPLETADAS EN S020" arriba para el detalle completo. |
| S021 | 2026-07-16 | Prioridad 1 resuelta (sidebar de `alvarez_admin`, commit `e2a5ecc` -- el bug vivía en `machine_documents`, app de H23). Sin más trabajo propio de H24: funcionalidad de vacaciones/calendario completa desde S020. **PCH ejecutado al cierre: H24 → H23** (confirmado explícitamente por Miguel Ángel). Migración Drive→GCS, anotada aquí desde S019 sin fecha, pasa a rastrearse en el anexo H23 como primera tarea de la sesión siguiente. Ver anexo H23 (S021) para el resto del trabajo real de esta sesión -- H24 solo tuvo el desvío puntual de arriba. |
| S127 | 2026-10-16 | Hito reabierto desde H30, ampliado y renombrado a "Vacaciones, Ausencias y Control Horario" por los requisitos de Alejandro (ver sección 7 y `ENTERPRISEBOT_ANNEX_ROUTER.md`, sección 6). Sin código: contexto real comprobado en el repositorio, reglas de vacaciones decididas con Carolina y hoja de ruta acordada. Aplazado en la misma sesión por Miguel Ángel; el marcador vuelve a H30. |
| S128 | 2026-10-16 | Sin trabajo propio de H24 (la sesión cerró la incidencia del agente H28 y los puntos 1-6 de H30, ver anexo V30). **PCH al cierre: H30 → H24**, por decisión de Miguel Ángel. La hoja de ruta 7.5 queda tal cual: se empieza por el punto 1. |
| S129 | 2026-10-16 → 2026-10-19 | Punto 1 (saldo de vacaciones) construido y a la espera de los datos de Carolina; punto 3 (fichaje) construido entero y cerrado con el fichaje real de Miguel Ángel del 17/10 (entrada 12:33 y salida 18:27 con GPS, Loja), salvo la prueba en iPhone. Partes y fichajes integrados (el parte se cierra con la salida, redondeo a hora/media), pestaña Fichajes de supervisores con municipio, mapa en el panel, incidencias y Excel, y fichajes en la ficha del trabajador. Ver 7.4bis y "COMPLETADAS EN S129" (7.6). |
| S130 | 2026-10-19 → 2026-10-20 | Puntos 1 (fichaje con un solo botón y fichaje manual por olvido) y 4 (ausencias) cerrados con datos reales; punto 2 (iPhone) postergado por Miguel Ángel a producción con Pablo; punto 3 a la espera de los datos de Carolina. Base del trabajador editable y festivos por base en Fichajes. Desvíos a H30/H31: dosieres por correo en un solo borrador (trabajadores y máquinas juntos, desde Personal y Centros de gasto), comprobación de tipo y datos al subir desde la ficha, 26 matrículas de centros de gasto rellenadas, secciones del alta por WhatsApp. Ver "COMPLETADAS EN S130" (7.7). |

---

## 7. Ampliación en S127 — Vacaciones, Ausencias y Control Horario

### 7.1. Origen

Requisitos que Alejandro trasladó a Miguel Ángel (verbatim):

> - Gestionar vacaciones, ausencias y fichajes de entrada y salida.
>   Permitir que los trabajadores fichen desde el móvil con su usuario.
> - Poder consultar los registros y los días de vacaciones disfrutados
>   y pendientes de cada trabajador.

Miguel Ángel: *"Las vacaciones ya tenemos hecho algo. Tenemos que
completarlo para hacerlo funcional."* Se decidió no abrir un hito
nuevo (ver `ENTERPRISEBOT_ANNEX_ROUTER.md`, sección 6, entrada S127).

### 7.2. Lo que ya existe (comprobado en el repositorio en S127)

- `hr_calendar.VacationPeriod`: `person` (FK obligatoria a
  `PersonIdentity`, rediseño de S94, migración 0004), `company`,
  `operator` (FK opcional a `CompanyUser`, solo para la tarea
  automática), `date_start`, `date_end`, `generated_entry_line`,
  `created_by`. Alta, edición, borrado y listado por el supervisor
  (`VacationPeriodListView/CreateView/UpdateView/DeleteView`).
- `hr_calendar.MedicalLeavePeriod`: `person`, `source_document`,
  `date_start`, `date_end` (puede quedar abierta), `contingency_type`.
- Calendario (`VacationCalendarView`,
  `services.compute_calendar_days`) con colores por día: vacaciones,
  trabajado, incompleto, ausencia, festivo. Se calcula por
  `CompanyUser` (operario con cuenta de panel), a partir de los partes
  digitales (`WorkOrderEntryLine`) y de las lagunas justificadas
  (`WorkdayGap` con `AbsenceCategory`, catálogo de `ivr_config`).
- **No existe:** los días de vacaciones que corresponden a cada
  trabajador, ni por tanto disfrutados y pendientes; ninguna consulta
  de saldo por trabajador; ningún código de fichaje (entrada/salida,
  registro de jornada).

### 7.3. Decisiones de Miguel Ángel (S127)

- **Fichaje desde la aplicación web, no app nativa.** En la plantilla
  hay móviles Android y iPhone; la web llega a todos los dispositivos
  y es lo estándar.
- **Sin cobertura (grúa trabajando en la calle):** el GPS no necesita
  internet. El marcaje se toma en el sitio con sus coordenadas y se
  envía cuando vuelva la conexión; con las coordenadas se sitúa en el
  mapa.
- **La app de asistencia con tablets es otra cosa** (específica de
  asistencia, se hará aparte) y no entra en este hito.
- Orden: primero terminar vacaciones, después ausencias, después
  fichajes.

**Reglas de vacaciones (Miguel Ángel, tras hablar con Carolina,
responsable de RRHH):**
- Los días que corresponden son un **dato que introduce la empresa,
  por sección**: 30 naturales o 22 laborables (Huelva, por ejemplo,
  22).
- Quien entra o sale a mitad de año tiene la **parte proporcional**.
- Los días que sobran **pasan al año siguiente, anotados como del año
  anterior**. Esto puede cambiar (que no se acumulen), así que también
  es **variable y por sección**.
- Migrar si hace falta, pero **recogiendo todos los supuestos**.

**Secciones:** son las de `ivr_config.Section` que ya existen (a
16/10/2026: Elevación, Asistencia, Informática,
Administración-Proveedores, Taller Mecánico, Taller Huelva, Guardas).
No se crean secciones nuevas para esto: crear o guardar una `Section`
genera o regenera su flujo de la centralita (señal
`auto_manage_section_call_flow`), así que la regla de vacaciones vive
en un modelo aparte enlazado a la sección y nunca se guarda la
`Section`. Hoy ningún trabajador está unido a una sección (los
`SectionContact` son a quién pasa las llamadas la centralita, no
pertenencia): la sección de cada trabajador se asigna desde el panel;
la lista la verá Miguel Ángel con Carolina.

**Saldo de partida:** lo ya disfrutado en 2026 y lo que sobró de 2025
se cargan **desde un Excel** (Carolina lo tiene en hoja de cálculo).

**Supuestos aceptados por Miguel Ángel (propuestos por el modelo, sin
objeción):** cambio de sección a mitad de año, cada tramo con su
regla; año natural; proporcional = días/año × días de alta en el año
÷ días del año, sumando varias altas, redondeo al medio día hacia
arriba; laborables = lunes a viernes sin festivos; naturales = todos
los días; los del año anterior se gastan primero y, si la sección fija
plazo y vence, se pierden con constancia; los días de baja médica
dentro de unas vacaciones no se gastan (art. 38.3 ET, con
`MedicalLeavePeriod`); medios días; ajustes manuales del supervisor con
motivo obligatorio; saldo negativo avisa pero se permite; el
supervisor gestiona a todos y cada trabajador ve solo lo suyo.

**Datos reales a 16/10/2026:** 75 trabajadores activos, 10 con usuario
del panel, 8 con base (Maqueda), 1 solo `VacationPeriod` registrado.

### 7.4. Contexto legal (consultado en S127, a confirmar antes de diseñar)

- Vigente (art. 34.9 del Estatuto de los Trabajadores): registro diario
  de inicio y fin de jornada de toda la plantilla, conservado 4 años y
  a disposición de los trabajadores, sus representantes y la
  Inspección.
- Real Decreto de registro horario digital: sin aprobar a 5 de octubre
  de 2026 según fuentes del sector; exigirá registro solo digital,
  trazabilidad de cualquier corrección, acceso remoto de la Inspección
  y consulta del propio trabajador. Comprobar en el BOE su estado y su
  texto antes de diseñar el punto 3.

### 7.4bis. Fichajes: prueba real y diseño decidido (S129)

**Prueba sin cobertura (S129).** Página de prueba pública
`/fichaje-prueba/` (`hr_calendar/clockin_test.py`, sin BD, una línea
`# [fichaje_prueba]` por pulsación en el log de errores de la web). Se
abre una vez con cobertura y queda guardada en el móvil (service
worker); en modo avión se pulsa Entrada/Salida, la hora se toma al
pulsar y la ubicación con el GPS, se guarda en el móvil (IndexedDB) y
se envía al volver la conexión.
- **Android (Miguel Ángel, 17/10/2026):** pulsado 09:39:41, recibido
  09:41:40; se conserva la hora de la pulsación. GPS sin datos en 9 s,
  ±20 m. Enviado en segundo plano con la página cerrada. La pulsación
  llegó **dos veces** (segundo plano + la página al volver la red): el
  servidor real debe guardar cada pulsación una sola vez por su id.
- **iPhone: pendiente de probar** (Safari no tiene envío en segundo
  plano; lo pendiente se envía al abrir la página con cobertura, y al
  fichar la salida se envía también la entrada pendiente). En iPhone
  la página debe abrirse desde el icono de la pantalla de inicio.
- La página de prueba se retira al construir el punto 3.

**Alternativa estudiada y descartada como vía principal: fichar
mandando la ubicación al bot de WhatsApp** (idea de Miguel Ángel). El
bot ya recibe ubicaciones (Paso 19), pero sin cobertura WhatsApp envía
el mensaje al volver la conexión y Twilio no da la hora de envío del
móvil: el fichaje quedaría con la hora de llegada.

**Real Decreto de registro horario digital (comprobado S129):** sigue
sin publicarse en el BOE (aplazado sin fecha el 26/09/2026). Vigente el
art. 34.9 ET. El borrador exige que toda corrección deje rastro sin
borrar el original.

**Alta y acceso (revisado el alta por WhatsApp existente, H17 S055).**
El bot ya da de alta en el panel: nombre, apellidos, DNI, sección y
base; rol según `Section.default_role` (hoy solo WORKSHOP o DRIVER);
usuario `nombre.apellido`, contraseña = 4 últimos números del DNI;
ficha enlazada por DNI; dispositivo de confianza (S039) para entrar sin
contraseña desde ese móvil. Corregidos en S129 cuatro fallos de ese
alta (ver commit `5eb16d5`).

**Decisiones de Miguel Ángel (S129), tal cual:**
1. Puestos de la empresa: **taller mecánico, chófer (gruista),
   administrativo (supervisores, administradores, oficinistas y
   comerciales) y guarda nocturno.** Hoy el alta por WhatsApp solo
   asigna WORKSHOP o DRIVER: un guarda o un oficinista que se dé de alta
   entraría como operario de taller o chófer. Los partes de trabajo los
   hacen hoy solo los mecánicos y Carlos Bas (Huelva); otras secciones
   los harán pronto (mismas vistas que los mecánicos y/o partes propios
   de su sección): el alta debe servir de base para dar después a cada
   uno el acceso que le toque.
2. **Los fichajes se hacen desde el dispositivo de confianza.** Miguel
   Ángel, verbatim: *"si siguen quiere hacer trampas, trampas se pueden
   hacer, no vamos a idear un sistema con un nivel de protección
   análogo al de la caja de caudales del banco de España"*.
3. **El móvil con el que se da de alta se guarda en su ficha**
   (cierra el pendiente de H31 S94).
4. **Un fichaje guardado sin cobertura se acepta al llegar aunque la
   sesión del panel haya caducado**, con la llave del dispositivo de
   confianza.

**Construido en S129 (punto 3 de 7.5, sin la página del trabajador):**
Miguel Ángel: *"Lo que queda pendiente de Carolina y las pruebas con
iPhone las haremos la semana que viene. Continuamos con lo que podemos
hacer."*
- Puestos: roles `OFFICE` (Administrativo) y `NIGHTGUARD` (Guarda
  nocturno), `CompanyUser.WORKER_ROLES`; `Section.default_role` admite
  los cuatro puestos y por fin se edita desde el panel (Secciones >
  editar). Producción (migración 0046): "Guardas" -> NIGHTGUARD,
  "Administración-Proveedores" -> OFFICE; el resto sigue en WORKSHOP
  (ninguna sección de chóferes existe todavía; "Informática" sin tocar).
  Commit `f0f8545`.
- Móvil del alta guardado en la ficha (`phone`, o `phone_secondary` si
  `phone` tiene otro; nunca pisa un número). Commit `f0f8545`.
- `hr_calendar.ClockEvent` (migración 0008) y recepción en
  `/fichaje/enviar/` y `/fichaje/estado/` (`hr_calendar/clockin.py`),
  identificada con la cookie del dispositivo de confianza aunque la
  sesión haya caducado; `client_id` único: el doble envío de la prueba
  de Android (segundo plano y página a la vez, 2 ms de diferencia, se
  ve en el log) se guarda una sola vez. Commit `757d93f`.
- Pestaña "Fichajes" de Documentación (solo ADMIN/SUPERVISOR/
  WORKSHOPBOSS): una fila por trabajador con fichajes, horas,
  incidencias y último fichaje; detalle día a día con mapa y retraso
  del envío; Excel (jornadas + pulsaciones). Jornadas: entrada con la
  siguiente salida, también pasada la medianoche; las incompletas no
  suman horas. Commits `a7ad589` + `dee7351`.
- Verificado en producción: migraciones 0045/0046/0008 aplicadas
  (`django_migrations`), secciones cambiadas, log sin errores tras la
  recarga.

- Página de fichaje del trabajador `/fichaje/` (Miguel Ángel: *"si
  hubiese algún problema con iPhone, lo arreglamos sobre la marcha"*):
  hora y GPS al pulsar, guardado en el móvil sin cobertura, envío al
  volver la conexión (segundo plano en Android; en iPhone al abrir la
  página, al volver la red, cada 30 s o con «Enviar pendientes»);
  saluda con el nombre y propone entrada o salida; si el móvil no es de
  confianza, enlace al panel que vuelve a `/fichaje/` tras marcarlo
  (login respeta `next` tras la pregunta de confianza). Enlace «Fichar»
  en Mi perfil. `/fichaje-prueba/` retirada: redirige y su service
  worker se da de baja solo. Commit `f8c2b34`.

- Primer fichaje real de Miguel Ángel (17/10, 12:16): el móvil no podía
  fichar -- un solo token de confianza por usuario; marcar otro aparato
  invalidó el del móvil y el login no volvía a preguntar porque la
  cookie existía. Arreglado de raíz: `ivr_config.TrustedDevice` (varios
  por usuario) y `panel/trusted_devices.py` como único punto de la
  cookie; login pregunta si la cookie no vale; perfil fiel; botón
  directo "Usar este móvil para fichar" con sesión abierta. Migración
  0047 aplicada: 20 tokens anteriores -> 20 TrustedDevice. Commit
  `d2f3e3f`.

- Partes y fichajes (Miguel Ángel, 17/10, reglas literales en
  `hr_calendar/clock_parts.py`). Corregido el mismo día: nada se manda
  al supervisor (*"que supervisor va a ir detrás de los operarios [...]
  Multiplicamos los gastos"*). Reglas vigentes:
  - Fichar entrada no toca partes.
  - *"un parte no se puede cerrar si no está fichada la salida, las
    tareas si, el parte no"*: "Cerrar parte" bloqueado sin la salida
    fichada; "Guardar tareas" libre. Solo para quien ya ficha (desde su
    primer fichaje).
  - Al fichar salida: copia del parte al log ([PARTE-BACKUP]), la
    última tarea del tramo termina a la hora fichada, pausa = hueco
    entre tramos, y el parte se cierra solo si cuadra con lo fichado;
    en jornada partida, solo con la salida del segundo periodo. Si no
    cuadra, sigue abierto y lo arregla el operario.
  - Parte hecho después: horas fichadas fijas, tareas dentro de lo
    fichado, última del tramo no empieza después de media hora antes de
    la salida, al cerrar todo lo fichado cubierto sin huecos; sin mínimo
    de 8 h con fichajes. Formulario: banner, horas rellenas y
    bloqueadas, tarea automática hasta la salida.
  - Arreglado: supervisor que corrige el parte de otro dejaba su nombre
    y comprobaba con sus datos.
  Commits `e353204` y `056aa48` (este quita la nota de supervisor,
  migración 0033).
  - Redondeo (sustituye a la tolerancia de ±5 del commit `04b4124`).
    Miguel Ángel: *"las horas y medias horas de los partes, son fijas.
    Los fichajes son exactos, entonces, tenemos que guardar la hora real
    de fichaje y la hora de redondeo"*. Regla
    (`hr_calendar/clock_rounding.py`): a ±5 min o menos de una hora o
    media, esa (x:25 y x:55 dentro, x:24 y x:54 fuera); más lejos, la
    ENTRADA a la media hora siguiente y la SALIDA a la anterior (8:20 ->
    8:30, 13:50 -> 13:30). `ClockEvent.rounded_at` (migración 0009,
    rellenada); el parte coincide exactamente con la redondeada. Commit
    `e055601`.
  - Quién ve qué (Miguel Ángel, 17/10): *"El tema de las 2 horas es
    para que lo vea administración (supervisores y admin), los
    trabajadores ven fichajes `en punto` y `a y media`"*. En el
    formulario de partes la hora real solo llega a ADMIN, SUPERVISOR y
    WORKSHOPBOSS; los errores del parte ya no citan la hora real. La
    página de fichaje sigue igual (*"no es necesario"*).
  - Visor de fichajes = pestaña Fichajes ampliada (*"pondremos las 2
    horas para que el supervisor pueda ver si un operario llega
    usualmente a su hora o no"*): columna "Llegadas tarde" (N de M
    entradas comparables), detalle con real → parte y, en cada entrada,
    hora del horario y minutos tarde/antes; Excel Jornadas con hora del
    parte, entrada según horario y minutos tarde. Cada entrada se
    compara con la hora de entrada más cercana del horario ACTUAL
    (mañana o, en partida, tarde); un minuto después ya es tarde. Commit
    `f1b999f`.
- Cierre real verificado (17/10): Miguel Ángel guarda tareas a las
  18:27:09 (parte #691 en curso, 12:30–18:30, G12, ticket 139 creado y
  cerrado), ficha la salida a las 18:27:27 (-> 18:30, envío en segundo
  plano) y el parte se cierra solo ("[FICHAJE-PARTE] ... parte cerrado
  al fichar la salida", copia [PARTE-BACKUP] y Excel generados).
- Incidencia del mismo cierre: al volver a abrir el parte desde el
  historial, la tarea preguntaba por su propio ticket como si fuera de
  otro parte ("ya hay un ticket de avería para esa máquina"); el parte
  en curso tampoco contaba como "este mismo parte". Arreglado: la tarea
  manda su ticket y, si es de la misma máquina, se muestra "Ticket de
  esta tarea" y se mantiene (acción keep). Commit `74cea56`.
- Primer fichaje real de Miguel Ángel (17/10, 12:16): el móvil no podía
  fichar -- un solo token de confianza por usuario; marcar otro aparato
  invalidó el del móvil y el login no volvía a preguntar porque la
  cookie existía. Arreglado de raíz: `ivr_config.TrustedDevice` (varios
  por usuario) y `panel/trusted_devices.py` como único punto de la
  cookie; login pregunta si la cookie no vale; perfil fiel; botón
  directo "Usar este móvil para fichar" con sesión abierta. Migración
  0047 aplicada: 20 tokens anteriores -> 20 TrustedDevice. Commit
  `d2f3e3f`.

- Partes y fichajes (Miguel Ángel, 17/10, reglas literales en
  `hr_calendar/clock_parts.py`). Corregido el mismo día: nada se manda
  al supervisor (*"que supervisor va a ir detrás de los operarios [...]
  Multiplicamos los gastos"*). Reglas vigentes:
  - Fichar entrada no toca partes.
  - *"un parte no se puede cerrar si no está fichada la salida, las
    tareas si, el parte no"*: "Cerrar parte" bloqueado sin la salida
    fichada; "Guardar tareas" libre. Solo para quien ya ficha (desde su
    primer fichaje).
  - Al fichar salida: copia del parte al log ([PARTE-BACKUP]), la
    última tarea del tramo termina a la hora fichada, pausa = hueco
    entre tramos, y el parte se cierra solo si cuadra con lo fichado;
    en jornada partida, solo con la salida del segundo periodo. Si no
    cuadra, sigue abierto y lo arregla el operario.
  - Parte hecho después: horas fichadas fijas, tareas dentro de lo
    fichado, última del tramo no empieza después de media hora antes de
    la salida, al cerrar todo lo fichado cubierto sin huecos; sin mínimo
    de 8 h con fichajes. Formulario: banner, horas rellenas y
    bloqueadas, tarea automática hasta la salida.
  - Arreglado: supervisor que corrige el parte de otro dejaba su nombre
    y comprobaba con sus datos.
  Commits `e353204` y `056aa48` (este quita la nota de supervisor,
  migración 0033).
  - Tolerancia ±5 min entre fichaje y parte (*"la 1 con una tolerancia
    de ±5 minutos. 15 son demasiados minutos"*): el parte usa la media
    hora si el fichaje está a ±5 min de ella (8:04 -> 8:00); al fichar
    salida solo se recorta la última tarea si se aleja más de 5 min. El
    fichaje se guarda exacto. Commit `04b4124`.
- Primer fichaje real de Miguel Ángel (17/10, 12:16): el móvil no podía
  fichar -- un solo token de confianza por usuario; marcar otro aparato
  invalidó el del móvil y el login no volvía a preguntar porque la
  cookie existía. Arreglado de raíz: `ivr_config.TrustedDevice` (varios
  por usuario) y `panel/trusted_devices.py` como único punto de la
  cookie; login pregunta si la cookie no vale; perfil fiel; botón
  directo "Usar este móvil para fichar" con sesión abierta. Migración
  0047 aplicada: 20 tokens anteriores -> 20 TrustedDevice. Commit
  `d2f3e3f`.

- Partes y fichajes (Miguel Ángel, 17/10, reglas literales en
  `hr_calendar/clock_parts.py`): fichar entrada no toca partes; fichar
  salida ajusta el parte ya hecho de ese día (última tarea del tramo a
  la hora fichada; tareas posteriores solo si caen en un tramo fichado
  después; lo no ajustable o un parte revisado queda en
  `WorkOrder.clock_review_note`, migración 0032, insignia "Fichaje" en
  el listado). Parte hecho después: horas fichadas fijas, tareas dentro
  de lo fichado, última del tramo no empieza después de media hora antes
  de la salida, al cerrar todo lo fichado cubierto sin huecos; hueco
  entre tramos = comida; sin mínimo de 8 h con fichajes. Formulario:
  banner, horas rellenas y bloqueadas, tarea automática hasta la salida.
  Arreglado: supervisor que corrige el parte de otro dejaba su nombre y
  comprobaba con sus datos. Commit `e353204`.
- Primer fichaje real de Miguel Ángel: entrada 17/10 12:33 con GPS,
  recibida 160 s después (log de producción).

**Punto 3 cerrado (17/10, comprobado en BD el 19/10):** `ClockEvent`
#1 entrada 2026-10-17 10:33:30 UTC (12:33, parte 12:30) y #3 salida
16:27:27 UTC (18:27, parte 18:30, envío en segundo plano), las dos con
coordenadas y municipio "Loja (Granada)", visibles en la pestaña
Fichajes y en su Excel. Queda solo la prueba en iPhone (hoja de ruta
7.5; lo que falle se arregla sobre la marcha).

### 7.5. Hoja de Ruta para la Siguiente Sesión (escrita al cierre de S129)

Orden de Miguel Ángel: primero la página de fichaje.

1. **Página de fichaje con un solo botón y fichajes manuales por
   olvido.** Miguel Ángel (S129), tal cual: *"Ahora mismo tenemos
   fichar entrada, fichar salida [...] Un botón [...] la primera marca
   del día es la entrada, la segunda marca del día es la salida. Si
   hay una tercera marca sería la entrada de la jornada de la tarde y
   una cuarta sería la de salida. Y tenemos que prever también los
   olvidos [...] la posibilidad de marcar manualmente, quedando marcado
   como incidencia y que ha sido un fichaje manual."*
   - `/fichaje/` (`hr_calendar/templates/hr_calendar/clockin.html`,
     `clockin_sw.js`, `clockin.py`): un único botón "Fichar". El tipo
     lo decide el servidor: si el trabajador tiene una entrada abierta
     (sin salida, dentro de `clock_report.MAX_SHIFT_HOURS`, igual que
     `build_shifts`, para que un turno de noche que cruza la
     medianoche cierre bien) es SALIDA; si no, ENTRADA. Sin cobertura,
     el móvil decide con sus propias pulsaciones guardadas y la última
     conocida del servidor (`/fichaje/estado/`), y el servidor respeta
     la pulsación tal cual llega (idempotente por `client_id`). La
     pantalla dice qué se va a registrar ("Fichar entrada"/"Fichar
     salida") antes de pulsar y, tras pulsar, cuál fue.
   - Fichaje manual por olvido en la misma página: el trabajador
     indica tipo, día y hora; se guarda con `sent_by=MANUAL` (valor
     que ya existe) y el momento real en que se registró
     (`received_at`); cuenta como incidencia "Fichaje manual" en
     `Shift.incidents` (listado, detalle, ficha y Excel). El parte
     (`clock_parts`) lo usa igual que uno normal.
   **Cierre:** en producción, 4 pulsaciones seguidas del botón de un
   usuario de prueba quedan en BD como ENTRADA, SALIDA, ENTRADA,
   SALIDA (`hr_calendar_clockevent`, consulta por `company_user_id`);
   y un fichaje manual queda en BD con `sent_by='MANUAL'` y aparece
   como incidencia "Fichaje manual" en el detalle de la pestaña
   Fichajes de ese trabajador.
2. **Prueba en iPhone** (7.4bis). Miguel Ángel: lo que falle *"lo
   arreglaremos sobre la marcha"*. **Cierre:** una entrada y una
   salida reales hechas desde un iPhone en `hr_calendar_clockevent`,
   con coordenadas, y `user_agent` de iPhone.
3. **Vacaciones: cargar los datos de Carolina y comprobar el saldo
   (punto 1, construido en S129: `hr_calendar/balance.py`,
   `balance_import.py`, pestaña Vacaciones).** Con las reglas por
   sección, la asignación de sección de cada trabajador y el Excel de
   disfrutados en 2026 y sobrantes de 2025 que trae Carolina.
   **Cierre:** consulta a BD de un trabajador real con sus periodos y
   ajustes, y la pantalla muestra los mismos días que corresponden,
   del año anterior, disfrutados y pendientes; una importación de
   prueba con la plantilla deja los ajustes en BD.
4. **Ausencias** (arrastrado 1.ª sesión sin avanzar). Registrar las
   ausencias que no son vacaciones ni baja (permisos, asuntos
   propios...) por trabajador y con fechas, con el mismo mecanismo
   que vacaciones, y que el calendario y la consulta por trabajador
   las muestren. Tipos: los del catálogo `AbsenceCategory` de la
   empresa. **Cierre:** una ausencia real dada de alta en el panel, en
   BD y en el calendario de ese trabajador.

**Situación de esta hoja de ruta al pausar el hito (S130, la hoja de
ruta no se reescribe):** puntos 1 y 4 hechos y cerrados con datos
reales (ver 7.7). Punto 2: Miguel Ángel lo pospone -- la prueba en
iPhone la hará Pablo en producción cuando empiece el fichaje en el
taller, y lo que falle se arregla sobre la marcha. Punto 3: a la espera
de los datos de Carolina, que llegan esa semana.

### 7.6. COMPLETADAS EN S129 (2026-10-16 → 2026-10-19)

**Punto 1 -- saldo de vacaciones (construido; faltan los datos de
Carolina).** Reglas por sección, secciones de los trabajadores,
ajustes e importación (`18aceb5`); la pestaña Vacaciones rehecha sobre
el formato del hub, una fila por trabajador con fecha de inicio y fin
(`5edca9d`, `f30e22a`); sin medios días, la empresa no los da
(`b607b26`).

**Punto 3 -- fichaje (construido y cerrado con el fichaje real, falta
el iPhone).** Detalle completo en 7.4bis:
- Prueba sin cobertura en Android (`8d16cf7`, `fb0ccbc`); alta por
  WhatsApp corregida, cuatro fallos reales (`5eb16d5`, H17); puestos
  Administrativo y Guarda nocturno y móvil del alta en la ficha
  (`f0f8545`).
- Registro con dispositivo de confianza (`757d93f`), pestaña Fichajes
  de supervisores (`a7ad589`, `dee7351`), página del trabajador
  `/fichaje/` y retirada de la prueba (`f8c2b34`).
- Incidencia real: el móvil de Miguel Ángel no podía fichar (un solo
  token de confianza por usuario); arreglado con `TrustedDevice`,
  varios por usuario (`d2f3e3f`).
- Partes y fichajes: las horas del parte las mandan los fichajes, el
  parte se cierra con la salida y no se manda nada al supervisor
  (`e353204`, `056aa48`); redondeo a hora o media (±5 min, si no la
  entrada a la media siguiente y la salida a la anterior), real y
  redondeada guardadas (`e055601`).
- Cierre real del parte con la salida (17/10): tareas guardadas 18:27:09,
  salida 18:27:27, parte #691 cerrado solo con su copia en el log y su
  Excel. En la misma prueba, incidencia real: el parte reabierto
  preguntaba por su propio ticket como si fuera de otro; arreglado,
  "Ticket de esta tarea" (`74cea56`).
- Quién ve qué: la hora real solo la oficina, el trabajador ve la del
  parte (`f1b999f`). Enlace "Volver al panel" en `/fichaje/` si se
  entra desde el menú (`7c74f21`).
- Pestaña Fichajes, según lo pedido por Miguel Ángel el 19/10:
  municipio de cada fichaje por geocodificación inversa con la clave de
  Google Maps de los presupuestos (`hr_calendar/clock_geocode.py`,
  migración `hr_calendar 0010`, comprobado en real: "Loja (Granada)")
  y mapa dentro del panel (`panel/static/panel/js/clock_map.js`)
  (`9270614`, `b0c1105`); listado con nombre, fichajes, incidencias y
  último día con entrada, salida y municipio, sin DNI ni horas
  (`790f967`, `f7c94a0`, `97a6089`); incidencias = llegada tarde,
  salida antes de hora, fichaje sin su pareja y fichaje a más de 3 h
  de su horario ("Fuera de horario"), todas en rojo y explicadas
  (`bc78a99`, `97a6089`); detalle con columna Incidencias y casilla
  "Ver solo incidencias"; filtro "Solo con incidencias" que también
  vale para exportar (`2f7f56f`); Excel con la fecha una vez por fila
  y salida según horario y minutos antes (`f7c94a0`); fichajes en la
  ficha del trabajador, Personal > Laboral > Fichajes (`f7c94a0`).

**Fuera de H24 en esta sesión:**
- H31: exportar el listado de Personal a Excel con plantillas (modal,
  plantillas propias y globales de empresa), `document_explorer 0186`
  (`36a9a33`).
- Botón "Exportar a Excel" con el mismo formato en todo el panel:
  verde de contorno, icono y texto iguales (`d64aa0d`).

**Migraciones aplicadas en producción (comprobado en
`django_migrations`):** `ivr_config` 0045-0047, `hr_calendar`
0008-0010, `work_order_processor` 0032-0033, `document_explorer` 0186.

### 7.7. COMPLETADAS EN S130 (2026-10-19 → 2026-10-20)

Sesión iniciada en `6b8e11a` (cierre de S129). 23 commits de trabajo,
40 archivos, todos desplegados por `deploy.yml` y comprobados.

**Punto 1 -- fichaje con un solo botón y fichaje manual por olvido
(CERRADO).**
- `dbed1a5`: `/fichaje/` con un único botón "Fichar". Con cobertura y
  sin pulsaciones pendientes decide el servidor (`clockin._decide_kind`,
  `select_for_update` sobre el `CompanyUser` y el último evento hasta
  `pressed_at`: SALIDA si hay una ENTRADA abierta dentro de
  `MAX_SHIFT_HOURS`, si no ENTRADA); sin cobertura decide el móvil
  (`decideKind` con lo guardado y lo último conocido del servidor) y el
  servidor respeta la pulsación (idempotente por `client_id`).
  `status()` devuelve `next_kind`. Fichaje manual en la misma página
  (`<details id="manual">`: tipo, día, hora), `sent_by=MANUAL` sin GPS
  ("Fichaje manual"), rechazado si es más de 2 min futuro
  (`MANUAL_FUTURE_MARGIN`). Incidencia "Fichaje manual: entrada HH:MM,
  registrada el dd/mm a las HH:MM" (`clock_report._manual_label`) en
  listado, detalle, ficha y Excel; en el detalle de Fichajes, "fichaje
  manual, apuntado dd/mm H:i" y nunca cuenta como retraso. Migración
  `hr_calendar 0011` (etiquetas de `sent_by`). Service worker
  `fichaje-v2`.
- `2ed0997`: Miguel Ángel: *"cuando se ficha y tenga un parte [...] sin
  cerrar y coincida con el ticaje manual, cierre el parte"*. Una ENTRADA
  manual apuntada después de su SALIDA vuelve a mirar el parte
  (`clock_parts.on_clock_press` / `closing_out_of`, `build_shifts` en
  ±`MAX_SHIFT_HOURS`).
- **Cierre comprobado en BD:** cuatro pulsaciones seguidas de Miguel
  Ángel (usuario #1) quedaron SALIDA, ENTRADA, SALIDA, ENTRADA (tenía
  una ENTRADA abierta de las 08:10, así que la secuencia es la
  correcta); la entrada manual del 18/10 09:00 quedó con
  `sent_by='MANUAL'` y sin GPS, y sale como incidencia en el detalle
  01/10-19/10 (captura de Miguel Ángel). Los envíos dobles se
  deduplicaron por `client_id`.

**Punto 4 -- ausencias (CERRADO).**
- `914d5dc`: modelo `hr_calendar.AbsencePeriod` (persona, empresa,
  categoría `ivr_config.AbsenceCategory` PROTECT, inicio, fin, nota,
  creado por; restricción fin >= inicio), migración `hr_calendar 0012`.
  `services.absence_categories` (activas, sin VACATION),
  `create_absence_period` (nota obligatoria si la categoría la pide),
  `absence_days_by_date`; el calendario las pinta en naranja
  "Ausencia: <categoría>" tras vacaciones y tarea real. Alta y borrado
  en el desglose de Vacaciones (`AbsencePeriodCreateView` /
  `RemoveView`, rutas `documentacion/vacaciones/<pk>/ausencia/` y
  `.../ausencia/<pk>/borrar/`) y acordeón "Ausencias" en la ficha.
- **Cierre comprobado:** cita médica real de Miguel Ángel (persona 250)
  el 20/10/2026 en BD (log `[ausencias]`), en el calendario (foto con
  el globo) y en su ficha.

**Fichajes sin horario en fin de semana y festivos (decisión de Miguel
Ángel, opción 2).** `45144ef`: `_schedule_times_by_user` devuelve
también qué días se comparan (`_day_rule`): guardas nocturnos todos; el
resto, no en sábado, domingo ni festivo de su base
(`budgets.services._is_holiday` + `Base.labor_calendar`; Maqueda =
festivos de Málaga, Loja 25/04 y 04/09, Huelva 03/08). La base pasa a
editarse en Usuarios (`CompanyUserUpdateView`, limitada a las bases de
la empresa) y en el alta (`6ec7764`, `CompanyUserCreateForm.base`).
Foto de Miguel Ángel: el 12/10 sale festivo.

**Desvíos de H24 dentro de la sesión (todos cerrados):**
- `47471df`: cambiar la contraseña desde Mi perfil (vuelve a Mi
  perfil; el cambio obligatorio sigue yendo a /panel/).
- `ba15722`: editar la propia cuenta en Usuarios (para ponerse la
  base) con rol y activo bloqueados; "Tu cuenta" en el listado.
- Carlos Carlín (`carlos.carlin`, CompanyUser 43, ya ADMIN): ficha
  enlazada a su usuario (Comando S `EnterpriseBot_001`); alta hecha
  desde el panel por alvarez_admin el 19/10 08:45.
- Manuel Alonso: preregistro inactivo del 23/07/2026 (onboarding
  pendiente). Documento "Alta de trabajadores" en Claude Docs con el
  flujo de alta (panel y WhatsApp).
- Veloso Sampaio "133 días": correcto (alta 21/08 a 31/12), sale "sin
  regla" porque no hay `VacationRule`; las reglas se quedan en la
  pestaña Vacaciones (Miguel Ángel: *"lo podemos dejar tal como
  está"*).

**Desvíos a H30/H31 (Documentación), todos desplegados:**
- `1b0af8b`: quitar el requisito a varias personas en Personal (el JS
  bloqueaba la opción vacía).
- Dosieres por correo: `b02a822` el .eml sale como BORRADOR de Outlook
  (`X-Unsent: 1`), sin destinatario ni From, con cuerpo por defecto y
  sin exigir correo del trabajador (antes el ZIP masivo salía vacío);
  `a26fa79` + `e807346` un solo correo con trabajadores y máquinas
  juntos (`panel/views_dossier_bundle.py`, `DossierBundleEmailView`:
  un PDF con todo / un PDF por cada uno / ZIP; mismo endpoint para
  descargar), bloque Dosieres igual en Personal y en Centros de gasto
  con plantilla y formato compartidos (`hub.html`, estado en window,
  modal solo si falta una plantilla), aviso > 20 MB. Retirada
  `PersonalDossierMassGenerateView`.
- `46c285c` + `1215459`: ámbito Personal/Maquinaria en requisitos,
  REVERTIDO (Miguel Ángel se refería a dosieres, que ya estaban bien);
  migraciones `document_explorer 0187` (añade) y `0188` (retira),
  aplicadas.
- `9511a5b`: la selección de Personal se guarda en
  `PanelNavigationState` ("personal_selection") como la de Centros de
  gasto.
- `57cb454`: "+ Subir" ofrece todos los tipos de la familia aunque el
  sujeto ya tenga uno (la X12 no dejaba elegir "Recibo del seguro").
- `f751b8c`, `c37cbab`: `document_explorer/document_check_service.py`.
  Al subir desde la ficha o desde Avisos, Gemini comprueba el tipo
  (aviso con botón "Cambiar a ...", nunca bloquea) y, en máquinas,
  rellena solo campos VACÍOS con los datos que acredita cada tipo
  (`MACHINE_FACTS_BY_TYPE`: permiso, ficha técnica, ITV y autorización
  provisional dan matrícula, bastidor y marca/modelo; los de seguro,
  matrícula y aseguradora/póliza). "Cambiar tipo" ahora renombra al
  nombre canónico, deshace la sustitución del tipo viejo y aplica la
  del nuevo (`subject_upload_service.change_document_type`,
  `apply_substitution`). X12: `X12_SEGURO_20271002.pdf` vigente,
  aseguradora MAPFRE (`EnterpriseBot_003`).
- Matrículas (`fill_machine_facts_s130`, `EnterpriseBot_002`, 004,
  005, 006 y 007): de 79 centros sin matrícula quedan 53 (26
  rellenadas; R3, R4 y A68 a mano tras ver los documentos: SE01978R,
  MA01520R y P9876BDS, esta temporal hasta 24-11-2026). Los que quedan
  no tienen documento que la acredite (EMPRESA_*, Z135-Z140, S16/S17/
  S20...), A70 solo tiene matrícula alemana de fábrica y BARCA es una
  embarcación. Incidencias: el comando nació mudo (Miguel Ángel lo
  señaló; corregido en `0a46503` según com-standards 0bis/0ter) y
  Gemini daba 504 con PDF escaneados (`3af4d3e`, `250af40`: 3
  primeras páginas como JPEG 150 ppp y un reintento); el patrón de
  matrícula admite temporales y remolques antiguos (`fb481ef`).
- `1893812`: `Section.onboarding_enabled` (migración `ivr_config
  0048`): Informática ya no se ofrece en el alta por WhatsApp; Taller
  Mecánico activada (`is_active` es operativa general; el IVR tiene
  `ivr_transfer_enabled`, que sigue apagado en Taller Mecánico) --
  Comando S `EnterpriseBot_008`.

**Migraciones aplicadas en producción (comprobado en
`django_migrations`):** `hr_calendar` 0011-0012, `document_explorer`
0187-0188, `ivr_config` 0048.

**Hallazgo para la siguiente sesión (dicho por Miguel Ángel al
cierre):** los kilómetros y horas se meten hoy por el parte de trabajo
y los trabajadores no siempre lo hacen; donde de verdad se apuntan es
al repostar. Habrá que tomar kilómetros y horas del programa de
repostaje, pero ese enlace NO se hace todavía (decisión de Miguel
Ángel).

