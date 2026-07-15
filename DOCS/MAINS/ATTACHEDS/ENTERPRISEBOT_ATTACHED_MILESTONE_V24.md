# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V24.md

# Anexo de Hito V24 — Vacaciones y Calendario
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

### Hoja de Ruta para la Siguiente Sesión

**Tarea principal — rediseño de `WorkPeriodGroup` (fuera de H24, pero
retomar antes o junto con H24 según decida Miguel Ángel al abrir la
sesión):**

1. **Cálculo de periodo por fecha, sin precrear filas.** Cada periodo
   va del día 21 de un mes al día 20 del mes siguiente (regla exacta,
   confirmada por Miguel Ángel, sin ambigüedad: 21/07–20/08,
   21/08–20/09, 21/09–20/10...). Dado cualquier día, debe poder
   calcularse matemáticamente a qué periodo pertenece, sin tabla de
   periodos futuros precreados ("al vuelo", decisión explícita de
   Miguel Ángel frente a la alternativa de generación por adelantado).
   La fila de `WorkPeriodGroup` correspondiente se asegura/crea la
   primera vez que hace falta, nunca antes.
2. **Un periodo pasa a "activo" solo al liquidar explícitamente el
   anterior** — nunca por fecha, nunca por crearlo. Mientras no se
   liquide, pueden convivir varios periodos sin liquidar a la vez (el
   que ya venció por fecha y el que ya ha empezado) — estado normal,
   no bug, cuando la liquidación se retrasa.
3. **Cómputo de horas extra "acumuladas pendientes":** propuesta
   planteada a Miguel Ángel y pendiente de su confirmación explícita al
   abrir la sesión (no cerrada del todo en esta sesión, no dar por
   buena sin más): sumar TODOS los periodos sin liquidar que tengan
   partes reales (no solo el nominal "activo"), como saldo de lo
   todavía no pagado. Al liquidar un periodo, sus horas dejan de contar
   en ese acumulado pendiente y pasan a ser solo consultables como
   histórico.
4. **Visor de horas extra por periodo (nuevo, no existe hoy):**
   supervisor elige cualquier operario + cualquier periodo (liquidado o
   no) y ve el total de horas extra de ese periodo; el propio operario
   puede consultar sus propios periodos pasados igual.
5. Impacto conocido a revisar en el propio código de esta sesión:
   `hr_calendar.services.resolve_period_group_for_calendar` (calendario,
   H24 paso 3) usa "el `WorkPeriodGroup` más reciente con
   `is_closed=False`" — hay que decidir si sigue teniendo sentido tal
   cual una vez exista el nuevo mecanismo de cálculo al vuelo, o si debe
   consultar directamente la función de cálculo por fecha en lugar de
   filtrar por `is_closed`.

**Cuando se retome H24 (o en paralelo, a decidir con Miguel Ángel):**
6. Confirmar con Miguel Ángel si el CRUD de vacaciones
   (`hr_calendar/views.py`, vía secundaria) sigue vivo tal cual o si
   hay que ajustarlo tras el rediseño de `WorkPeriodGroup`.
7. Una vez cerrado lo anterior, retomar H23 (Documentación de Centros
   de Gasto) — orden ya confirmado en S018, sigue vigente.

**No abordado, sin fecha decidida:** migración de Google Drive a Google
Cloud Storage (ver "COMPLETADAS EN S019" arriba) — reescritura de
`spare_parts/gdrive_service.py`.

---

## 6. Registro de Sesiones

| Sesión | Fecha | Trabajo realizado |
|---|---|---|
| S018 | 2026-07-14 | Hito creado (desvío desde H23). App `hr_calendar`, modelo `VacationPeriod`, campo `CompanyUser.base`, comando `assign_operator_bases` ejecutado en producción (14 operarios/chóferes, bases Maqueda/Huelva), onboarding WhatsApp ampliado, y las 7 preguntas de la sección 4 resueltas. Ver "COMPLETADAS EN S018" arriba para el detalle completo. Siguiente sesión: construir la generación automática de la tarea, el formulario de alta y la vista de calendario (hoja de ruta arriba). |
| S019 | 2026-07-15 | Pasos 1-3 de la hoja de ruta construidos, con corrección de flujo a mitad de sesión (directriz 4.8): la generación automática se deriva de la tarea real del operario, no de un CRUD de supervisor. Calendario con código de colores y agrupación por `WorkPeriodGroup` construido y desplegado. Ocho incidencias reales encontradas y corregidas en producción (dos `ImportError` que tumbaron el despliegue, `FieldError`, sidebar rota, dos bugs de validación que bloqueaban el flujo real, autorrelleno de H.C./H.F., patrón de errores en crudo en 17 sitios fuera de H24). Vista de detalle de solo lectura para Partes Digitales añadida (fuera de H24). Diagnosticados con datos reales dos casos de "parte no encontrado" sin causa técnica. Decidida la migración futura de Google Drive a Google Cloud Storage (sin implementar). Detectado al cierre un bug real en `WorkPeriodGroup` (activación automática sin control) que Miguel Ángel decide abordar en sesión nueva junto con un rediseño más amplio (cálculo de periodo 21-20 al vuelo, horas extra acumuladas, visor por periodo) — ver "COMPLETADAS EN S019" y la hoja de ruta arriba para el detalle completo. |
