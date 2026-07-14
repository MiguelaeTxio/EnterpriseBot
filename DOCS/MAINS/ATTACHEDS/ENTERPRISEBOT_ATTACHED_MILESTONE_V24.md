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

## 3. Especificación funcional (tal como la dio Miguel Ángel al cierre de S017)

### 3.1. Tarea automática de vacaciones
- Centro de gasto `PERSONAL`, categoría `VACATION` (ambos ya existentes,
  ver sección 2).
- Se añade en la última jornada de trabajo antes de las vacaciones
  (generación automática, no manual).
- Duración automática: 1 hora.
- En el campo de resolución/detalle va el día de fin de vacaciones —
  campo exacto a confirmar (ver sección 2).
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
- Código de colores por día:
  - **Azul** — día trabajado (con parte registrado).
  - **Verde** — día de vacaciones.
  - **Naranja** — día de baja (dentro de "personal" — confirmar catálogo
    exacto de motivos de baja con Miguel Ángel; candidatos en
    `AbsenceCategory`: `SICK_LEAVE`, `WORK_ACCIDENT` — a confirmar si
    "baja" es solo estos dos o un conjunto más amplio).
  - **Rojo** — día laborable sin parte, sin vacaciones, sin festivo y sin
    baja (ausencia no justificada / hueco a revisar).
  - **Amarillo** — festivo (fuente de festivos a definir — ¿modelo nuevo
    `Holiday`/calendario laboral por empresa, o integración externa?
    Pendiente de decidir con Miguel Ángel).

---

## 4. Preguntas Abiertas — Resolver al Empezar la Sesión que Retome Este Hito

1. ~~Dónde se registra el periodo de vacaciones~~ — **RESUELTO en S018**:
   el propio modelo de calendario de `hr_calendar`, ligado al operario/
   chófer (`CompanyUser`), es quien recoge los días. Modelo candidato
   `VacationPeriod`: FK a `CompanyUser` (roles `WORKSHOP`/`DRIVER` —
   confirmar si también `WORKSHOPBOSS`/`OPERATOR` deben poder tener
   vacaciones registradas), `date_start`, `date_end`. La tarea automática
   de la sección 3.1 se dispara al guardar un `VacationPeriod` nuevo,
   calculando la última jornada laboral antes de `date_start`. Los días
   verdes del calendario (sección 3.2) se derivan directamente del rango
   `[date_start, date_end]` de los `VacationPeriod` del usuario — no hace
   falta un registro día a día.
2. **Campo exacto donde va el día de fin de vacaciones** en la tarea
   generada — confirmar si es `repair_notes`, un campo nuevo, o se
   aprovecha `WorkdayGap.note` (ver sección 2).
3. **Catálogo de motivos de "baja"** (color naranja) — qué subconjunto
   exacto de `AbsenceCategory` cuenta como baja frente a otras ausencias
   personales.
4. **Fuente de festivos** (color amarillo) — modelo nuevo por empresa/año
   vs. integración externa.
5. **Puntos de agregación de horas** a excluir para bloques PERSONAL/
   VACATION — inventariar `analytics/` y `work_order_processor` antes de
   tocar nada (principio DRY: puede que ya exista una exclusión genérica
   para PERSONAL que solo haya que confirmar, en vez de crear una nueva).

---

## 5. Hoja de Ruta para la Siguiente Sesión

1. Resolver las 5 preguntas abiertas de la sección 4 con Miguel Ángel
   antes de escribir ningún modelo o migración.
2. Diseñar el modelo de datos mínimo de `hr_calendar` (candidato:
   `VacationPeriod` con FK a `CompanyUser`, fechas inicio/fin — validar si
   hace falta modelo propio de festivos según respuesta a la pregunta 4).
3. Implementar la generación automática de la tarea de vacaciones,
   reutilizando el mecanismo `WorkdayGap`/bloque PERSONAL ya existente
   (sección 2) — no crear un mecanismo de persistencia paralelo.
4. Implementar la vista de calendario con el código de colores, con el
   alcance de datos por rol descrito en 3.2.
5. Verificar la exclusión de horas de bloques PERSONAL/VACATION en todos
   los puntos de agregación localizados en la pregunta 5.

---

## 6. Registro de Sesiones

| Sesión | Fecha | Trabajo realizado |
|---|---|---|
| S018 | 2026-07-14 | Hito creado (desvío desde H23, a petición explícita de Miguel Ángel — confirmó que "cerrar la decisión" significaba implementar el calendario). App dedicada `hr_calendar` decidida. Sin código todavía. Hallazgo clave: la infraestructura de centro de gasto PERSONAL y catálogo AbsenceCategory (incluido el código VACATION) ya existe de H7/H10 — la pieza 1 del hito es automatización, no construcción desde cero. Ver sección 2 y sección 4 (preguntas abiertas) para el punto de partida de la siguiente sesión. |
