# Anexo de Hito V10 — Albaranes de Proveedores y Gestión de Almacén de Repuestos
# Proyecto: EnterpriseBot
# Fecha de inicio: pendiente

---

## 1. Visión General del Hito

Este hito implementa el circuito completo de gestión de repuestos:
desde la entrada de material vía albarán de proveedor (foto o PDF)
hasta su asignación a una máquina, una orden de reparación activa
o el almacén digital. El almacén se digitaliza de forma orgánica —
sin inventario masivo inicial — a medida que los repuestos se van
usando en los partes de trabajo.

Principios rectores:

1. **Cero inventario inicial.** El stock real emerge del uso cotidiano.
   Los repuestos no digitalizados entran al sistema la primera vez que
   alguien los utiliza, no antes.
2. **Circuito cerrado.** Todo uso de repuesto termina vinculado a una
   máquina o centro de gasto. Nada queda sin asignar.
3. **Dos tipos de stock.** Contable (cantidad numérica) e incontable
   (nivel cualitativo: FULL / MEDIUM / LOW / EMPTY). Los consumibles
   como tornillos, líquidos o juntas son incontables.
4. **Gemini Vision para albaranes.** La extracción de datos de foto o
   PDF se delega a Gemini 3.5 Flash (vía el helper compartido
   `ai_services.gemini_client`, Directriz 4.1) — no hay OCR manual
   ni formularios de entrada de datos de proveedor.
5. **Asignación automática a orden de reparación.** Si el repuesto se
   vincula a una máquina y esa máquina tiene un BreakdownTicket abierto
   (OPEN o IN_PROGRESS), el repuesto se asocia automáticamente a ese
   ticket.
6. **Limbo de pre-asignación.** Cuando un albarán asigna un repuesto a
   una máquina concreta (vía código de máquina normalizado), el
   repuesto queda reservado para esa máquina/ticket sin sumar a stock
   de almacén — evitando doble asignación — hasta que se consume
   realmente en el cierre de un parte de trabajo. Mientras está en
   este limbo es totalmente trazable y reversible (devolución manual
   a almacén). Ver sección 3.2.

---

## 2. Arquitectura del Módulo

### 2.1. Django Apps

Nueva app de dominio: `spare_parts`

```
spare_parts/
    __init__.py
    apps.py
    admin.py
    models.py       — DeliveryNote, DeliveryNoteLine,
                      SparePartEntry, StockMovement
    views.py        — DeliveryNoteUploadView, DeliveryNoteDetailView,
                      SparePartListView, StockMovementCreateView
    services.py     — GeminiVisionExtractionService,
                      StockAssignmentService
    urls.py
    migrations/
    templates/
        spare_parts/
            delivery_note_upload.html
            delivery_note_detail.html
            spare_part_list.html
            stock_movement_form.html
```

Nueva app compartida (S001-H10, principio DRY): `ai_services`. No es
específica de este hito — aloja el helper de inicialización del
cliente Gemini para que cualquier app del proyecto que necesite
llamadas de texto/visión Gemini (no Live API) lo reutilice en vez de
duplicar la lógica. `work_order_processor.services` se migró a este
helper en S001-H10.

```
ai_services/
    __init__.py
    apps.py
    gemini_client.py — get_gemini_client(), get_request_config(),
                        DEFAULT_MODEL = "gemini-3.5-flash"
    migrations/        (vacía — app sin modelos)
```

### 2.2. Modelos de Datos

#### DeliveryNote — Albarán de proveedor

| Campo | Tipo | Descripción |
|---|---|---|
| `company` | FK Company | Empresa |
| `source_type` | CharField | PHOTO / PDF |
| `image` | ImageField null | Foto del albarán (source_type=PHOTO) |
| `pdf_file` | FileField null | PDF del albarán (source_type=PDF) |
| `supplier_name` | CharField | Nombre proveedor (extraído por Gemini) |
| `supplier_tax_id` | CharField blank | NIF/CIF proveedor (extraído, opcional) |
| `delivery_number` | CharField blank | Número de albarán (extraído) |
| `delivery_date` | DateField null | Fecha del albarán (extraída) |
| `extraction_raw` | JSONField | Respuesta raw de Gemini Vision |
| `status` | CharField | PENDING / PROCESSED / ASSIGNED |
| `processed_by` | FK CompanyUser null | Usuario que revisó la extracción |
| `created_at` | DateTimeField auto | |
| `updated_at` | DateTimeField auto | |

#### DeliveryNoteLine — Línea de albarán

| Campo | Tipo | Descripción |
|---|---|---|
| `delivery_note` | FK DeliveryNote | Albarán al que pertenece |
| `line_number` | PositiveIntegerField | Orden en el albarán |
| `reference` | CharField blank | Referencia del artículo (opcional) |
| `description` | CharField | Descripción del artículo |
| `quantity` | DecimalField | Cantidad (0 si incontable) |
| `unit_price` | DecimalField null | Precio unitario (opcional) |
| `total_price` | DecimalField null | Precio total línea (opcional) |
| `assignment_type` | CharField | MACHINE / WAREHOUSE / UNASSIGNED |
| `machine` | FK MachineAsset null | Máquina asignada (si MACHINE) |
| `work_order_line` | FK WorkOrderEntryLine null | Línea de parte vinculada |
| `spare_part_entry` | FK SparePartEntry null | Entrada en stock resultante |

#### SparePartEntry — Repuesto en almacén digital / limbo de pre-asignación

Rediseñado en S001 para soportar el circuito de pre-asignación con limbo
(ver sección 3 — Circuito de Repuestos). El campo `status` es el eje
central del modelo; sustituye al booleano `warehouse` de la versión
original del anexo.

| Campo | Tipo | Descripción |
|---|---|---|
| `company` | FK Company | Empresa |
| `reference` | CharField blank | Referencia del artículo (opcional) |
| `description` | CharField | Descripción (obligatorio) |
| `is_uncountable` | BooleanField | True si es incontable |
| `stock_quantity` | DecimalField default=0 | Stock actual (solo contables, solo si status=WAREHOUSE) |
| `stock_level` | CharField blank | FULL/MEDIUM/LOW/EMPTY (solo incontables, solo si status=WAREHOUSE) |
| `status` | CharField choices | WAREHOUSE / PRE_ASSIGNED / CONSUMED |
| `machine` | FK MachineAsset null | Máquina destino (PRE_ASSIGNED sin ticket, o CONSUMED) |
| `breakdown_ticket` | FK BreakdownTicket null | Ticket de avería destino (PRE_ASSIGNED con ticket abierto) |
| `pre_assigned_at` | DateTimeField null | Timestamp de entrada en el limbo — base del código de colores por antigüedad en el CRUD |
| `consumed_at` | DateTimeField null | Timestamp de consumo real (cierre de parte) |
| `origin_type` | CharField choices | SUPPLIER / SALVAGED — procedencia del repuesto, ver sección 3.6 |
| `supplier_name` | CharField blank | Proveedor — replicado del albarán origen. Solo si origin_type=SUPPLIER |
| `supplier_tax_id` | CharField blank | NIF/CIF proveedor — replicado. Solo si origin_type=SUPPLIER |
| `supplier_address` | CharField blank | Dirección proveedor — replicado. Solo si origin_type=SUPPLIER |
| `purchase_unit_price` | DecimalField null | Precio unitario de compra — replicado. Solo si origin_type=SUPPLIER |
| `purchase_discount_percent` | DecimalField null | Descuento aplicado por proveedor — replicado. Solo si origin_type=SUPPLIER |
| `purchase_total_price` | DecimalField null | Precio total de compra — replicado. Solo si origin_type=SUPPLIER |
| `source_delivery_note_line` | FK DeliveryNoteLine null | Línea de albarán de origen — solo trazabilidad/auditoría. Solo si origin_type=SUPPLIER |
| `origin_machine` | FK MachineAsset null | Máquina donante de la que se canibalizó la pieza. Solo si origin_type=SALVAGED |
| `origin_work_order_entry_line` | FK WorkOrderEntryLine null | Línea de parte donde se documentó la retirada, si existe. Opcional incluso con origin_type=SALVAGED — puede no haber parte asociado (pieza ya retirada de antiguo) |
| `created_at` | DateTimeField auto | |
| `updated_at` | DateTimeField auto | |

**Regla de origen:** `origin_type` determina de un vistazo qué bloque
de campos está poblado. Con `SUPPLIER`, los campos de máquina donante
quedan vacíos. Con `SALVAGED`, los campos de proveedor/precio quedan
vacíos — la "compra" de la pieza fue la de la máquina origen en su
día, dato que no es relevante para el análisis de coste de esta
unidad reciclada. Ver sección 3.6 para el flujo completo de alta por
canibalización.

#### StockMovement — Movimiento de stock

| Campo | Tipo | Descripción |
|---|---|---|
| `spare_part_entry` | FK SparePartEntry | Repuesto afectado |
| `movement_type` | CharField | IN / OUT / ADJUST / RETURN_TO_WAREHOUSE / SALVAGE |
| `quantity` | DecimalField default=0 | Cantidad movida (0 si incontable) |
| `level_before` | CharField blank | Nivel antes (solo incontables) |
| `level_after` | CharField blank | Nivel después (solo incontables) |
| `machine` | FK MachineAsset null | Máquina destino (si OUT) |
| `breakdown_ticket` | FK BreakdownTicket null | Ticket de avería vinculado |
| `work_order_entry_line` | FK WorkOrderEntryLine null | Línea de parte vinculada — uso histórico/auditoría general |
| `spare_part_line` | FK SparePartLine null | Línea de repuesto concreta (work_order_processor.SparePartLine) creada o rellenada al consumir este movimiento. Ver sección 3.4 |
| `delivery_note_line` | FK DeliveryNoteLine null | Línea de albarán origen (si IN) |
| `notes` | TextField blank | Notas del movimiento |
| `created_by` | FK CompanyUser | Usuario que registró el movimiento |
| `created_at` | DateTimeField auto | |

`RETURN_TO_WAREHOUSE` registra la devolución manual de un repuesto
desde el limbo (PRE_ASSIGNED) a almacén (WAREHOUSE) cuando la máquina
destino ya no va a usarlo (p. ej. siniestro de la máquina).

`SALVAGE` registra la entrada de un repuesto canibalizado de una
máquina donante (origin_type=SALVAGED en SparePartEntry). Ver
sección 3.6.

---

## 3. Circuito de Repuestos — Flujo Completo

### 3.1. Entrada vía Albarán (foto o PDF)

1. El operario de logística sube la foto o PDF desde el panel.
2. `GeminiVisionExtractionService` extrae: datos del proveedor,
   número y fecha del albarán, y líneas de artículo (referencia,
   descripción, cantidad, precio unitario, precio total).
3. El resultado se presenta al usuario para revisión y corrección
   antes de confirmar. Todos los campos son editables.
4. Por cada línea, el sistema lee el código de máquina o almacén
   anotado por el operario en el albarán físico, normalizado con
   el mismo normalizador de código de máquina ya validado en el
   lector de PDF histórico de partes de trabajo (H08). El usuario
   puede corregir la asignación detectada antes de confirmar.
5. Al confirmar, según el código detectado:

   **Código de almacén** (ALM / AL / ALMACEN / variantes normalizadas):
   - Se crea o actualiza `SparePartEntry` con `status=WAREHOUSE`.
   - Suma a `stock_quantity` (contable) o actualiza `stock_level`
     (incontable) con `StockMovement IN`.
   - Se replican los campos de proveedor/precio del albarán en el
     `SparePartEntry` (supplier_name, supplier_tax_id, etc.).

   **Código de máquina:**
   - Se busca esa `MachineAsset`.
   - Si tiene `BreakdownTicket` con status OPEN o IN_PROGRESS:
     se crea `SparePartEntry` con `status=PRE_ASSIGNED`,
     `breakdown_ticket=ticket`, `pre_assigned_at=now()`.
   - Si NO tiene ticket abierto: se crea `SparePartEntry` con
     `status=PRE_ASSIGNED`, `machine=machine`, `pre_assigned_at=now()`.
   - En ambos casos se replican los campos de proveedor/precio del
     albarán. El repuesto queda en el **limbo**: no suma a ningún
     stock de almacén, evitando doble asignación del mismo artículo.

6. El `DeliveryNote` pasa a status ASSIGNED.

### 3.2. El Limbo de Pre-Asignación

Un `SparePartEntry` con `status=PRE_ASSIGNED` está reservado para una
máquina o ticket concreto, pero todavía no se ha consumido en ningún
parte de trabajo. Mientras permanece en este estado:

- No cuenta como stock disponible de almacén.
- Es visible en el CRUD del limbo (`SparePartListView`, filtro
  PRE_ASSIGNED), ordenado por `pre_assigned_at` ascendente con
  código de colores por antigüedad: verde (&lt;2 semanas), amarillo
  (1 mes), naranja (3 meses), rojo (6 meses o más).
- Puede devolverse manualmente a almacén (acción "Devolver a
  almacén" en el CRUD) si la máquina destino ya no lo va a usar
  (p. ej. siniestro de la máquina). Esto cambia `status=WAREHOUSE`,
  limpia `machine`/`breakdown_ticket`/`pre_assigned_at`, y genera
  `StockMovement RETURN_TO_WAREHOUSE`.

### 3.3. Consumo en el Parte de Trabajo Digital

Al abrir una orden de reparación (`WorkOrderEntry`) sobre una máquina:

**Si la máquina tiene `BreakdownTicket` abierto:** al seleccionar el
ticket, el parte se auto-rellena con los datos que ya define el
ticket (centro de gasto, familia/tipo de avería, etc.) — excepto
variables propias del parte (horas, pausas de comida). Los
`SparePartEntry` con `status=PRE_ASSIGNED` y `breakdown_ticket=ticket`
aparecen automáticamente listados en la sección de repuestos del
parte.

**Si no hay ticket abierto:** al seleccionar la máquina/centro de
gasto, aparecen automáticamente los `SparePartEntry` con
`status=PRE_ASSIGNED` y `machine=machine`.

**Repuesto no pre-asignado (Caso C, ver 3.4):** el mecánico puede
registrar en el momento un repuesto que no estaba en el limbo ni en
almacén, igual que en la versión original del circuito.

### 3.4. Cierre del Parte — Consumo Real

Solo al cerrar el parte (definitivo o provisional por bloques) el
repuesto sale del limbo o del almacén y se materializa como consumo
documental en el propio parte:

1. `status` del `SparePartEntry` pasa a `CONSUMED`, `consumed_at=now()`.
2. Se crea o rellena una `SparePartLine`
   (`work_order_processor.SparePartLine`) dentro del
   `WorkOrderEntryLine` correspondiente, con los datos tomados del
   `SparePartEntry`: `reference`, `material` (desde `description`),
   `quantity`, `unit_price` (desde `purchase_unit_price` si
   origin_type=SUPPLIER, o vacío si origin_type=SALVAGED), y
   `source` = `SUPPLIER` o `WAREHOUSE` según corresponda. Esta
   `SparePartLine` recibe una FK nueva `spare_part_entry` apuntando
   al `SparePartEntry` de origen — campo añadido a `SparePartLine`
   en este hito, `null=True` para no romper los registros históricos
   ya poblados por OCR sin pasar por este circuito.
3. Se crea `StockMovement OUT` apuntando a esa `SparePartLine`
   concreta (FK `spare_part_line`), no directamente a
   `WorkOrderEntryLine` — un bloque de parte puede tener varios
   repuestos, cada uno con su propia `SparePartLine` y su propio
   `StockMovement`.
4. Si el repuesto venía de almacén (`status=WAREHOUSE`, Caso A/C del
   punto 3.5) en vez del limbo, el descuento de `stock_quantity` o
   actualización de `stock_level` ocurre en el momento de añadir la
   línea al parte, no en el cierre — el cierre solo materializa la
   `SparePartLine` y el `StockMovement`.

### 3.5. Uso de Repuesto en un Parte de Trabajo — Casos Generales

Al añadir un repuesto en una línea de parte (`WorkOrderEntryLine`)
que NO proviene del listado automático de pre-asignados (3.3):

**Paso 1 — Búsqueda:** el sistema busca por referencia o descripción
en `SparePartEntry status=WAREHOUSE` de la empresa.

**Caso A — Existe en almacén digital (status=WAREHOUSE, stock > 0):**
- Contable: descuenta `stock_quantity`, crea `StockMovement OUT`,
  vincula a la línea del parte y a la máquina/ticket, `status` pasa
  a `CONSUMED`, `consumed_at=now()`.
- Incontable: muestra nivel actual, el mecánico indica el nuevo nivel
  tras el uso, actualiza `stock_level`, crea `StockMovement OUT`.

**Caso B — Existe pre-asignado a esta máquina/ticket (ver 3.3):**
- Selección directa del listado automático. Se aplica el cierre
  descrito en 3.4.

**Caso C — No existe en almacén digital ni en el limbo (no
digitalizado aún):**
- El mecánico registra el repuesto en el momento:
  - Descripción (obligatorio), referencia (opcional).
  - ¿Es contable o incontable?
  - Si contable: ¿cuántos quedan en el almacén físico tras este uso?
    → ese número es el `stock_quantity` inicial del `SparePartEntry`.
  - Si incontable: ¿qué nivel queda? (FULL / MEDIUM / LOW / EMPTY)
    → ese es el `stock_level` inicial.
- Se crea `SparePartEntry` con `status=CONSUMED` directamente
  (digitalización orgánica retroactiva) y los datos de stock
  indicados. Se crea `StockMovement OUT` vinculado al parte y la
  máquina/ticket correspondiente.

### 3.6. Procedencia por Canibalización (Reciclado Interno)

A veces un repuesto no viene de un proveedor sino de otra máquina de
la propia flota, activa o de baja, de la que se retira una pieza
todavía aprovechable (ej. caja de cambios, bomba de agua).

**Principio rector: separación total entre parte de trabajo y
gestión de almacén.** El parte de trabajo (`WorkOrderEntry` /
`WorkOrderEntryLine`) documenta en texto libre la tarea realizada
(p. ej. "quitar bomba de agua de la máquina B14") sin disparar
automáticamente ningún movimiento de `SparePartEntry`. La retirada
NO genera por sí sola un repuesto en el sistema de almacén.

**Alta manual posterior, siempre desde `spare_parts`:** es el
responsable de almacén/logística quien, después y por separado, da
de alta el `SparePartEntry` recuperado:

1. Selecciona `origin_type=SALVAGED`.
2. Indica `origin_machine` (la máquina donante).
3. Opcionalmente vincula `origin_work_order_entry_line` al bloque de
   parte donde se documentó la retirada, si lo hay y si lo conoce —
   queda `null` para piezas ya retiradas de antiguo sin parte
   asociado en el sistema.
4. Decide el destino igual que con una pieza de proveedor: si se
   queda en almacén hasta rectificar/reutilizar → `status=WAREHOUSE`,
   genera `StockMovement SALVAGE`; si ya se sabe que va para otra
   máquina/ticket → `status=PRE_ASSIGNED` directamente, mismo
   tratamiento de limbo que el resto (sección 3.2).

Los dos casos descritos por Miguel Ángel ("quitar y poner en el
mismo paso" vs. "quitar, almacenar y poner más tarde") se resuelven
con el mismo flujo de alta: en el primer caso, el alta en
`spare_parts` se hace con destino `PRE_ASSIGNED` apuntando
directamente a la máquina receptora; en el segundo, con destino
`WAREHOUSE` y una pre-asignación posterior independiente cuando se
decide el destino.

### 3.7. Niveles de Stock Incontable

| Código | Etiqueta UI | Descripción |
|---|---|---|
| FULL | Lleno | Bien provisto, sin urgencia de reposición |
| MEDIUM | Medio | Queda aproximadamente la mitad |
| LOW | Poco | Quedan pocas unidades, conviene reponer |
| EMPTY | Vacío | Sin stock — hay que pedir al proveedor |

---

## 4. Integración con Módulos Existentes

- **fleet.MachineAsset:** FK desde `SparePartEntry` (`machine`,
  `origin_machine`) y `StockMovement`.
- **chat.BreakdownTicket:** FK desde `SparePartEntry` y
  `StockMovement` para asociar repuestos a tickets de avería activos.
- **work_order_processor.WorkOrderEntryLine:** FK desde
  `SparePartEntry` (`origin_work_order_entry_line`) y
  `StockMovement` para vincular repuestos a líneas de parte digital.
- **work_order_processor.SparePartLine:** modelo ya existente,
  ampliado en este hito con FK nueva `spare_part_entry` (null=True).
  Es el punto de unión entre el almacén digital (`spare_parts`) y el
  registro documental del parte de trabajo (`work_order_processor`).
  Ver sección 3.4.
- **ivr_config.CompanyUser:** FK `created_by` en `StockMovement`.

---

## 4-bis. Diseño de Paso 4-bis — CERRADO COMPLETO EN S009 (2026-07-08)

**Estado final: los 12 puntos del diseño de S006 están resueltos.**
Resumen de cómo se cerró cada uno (detalle de la discusión original más
abajo, conservado por trazabilidad):

- **Puntos 1-2** (resolución de ticket por CdG + mutex
  `select_for_update`): implementados en S007
  (`chat/ticket_resolution.py`), con el refinamiento de que PAUSED
  cuenta como candidato abierto y la confirmación es obligatoria con
  1+ candidatos.
- **Punto 3** (pre-asignación de repuestos sin cambios, requisito de
  ticket solo en materialización final): ya era así desde antes de
  S006, sin código nuevo necesario.
- **Punto 4** (`tipo_tarea` + clasificación unificada async): **cerrado
  en S009.** `BreakdownTicket.tipo_tarea`/`task_category_free`
  (migración `chat.0010`), `classify_task()` en
  `work_order_processor/services.py` (una sola llamada Gemini decide
  tipo_tarea y, según cuál sea, clasifica avería o rellena
  categorización libre), `classify_fault_line` bifurca según si la
  línea tiene `breakdown_ticket` asociado, idempotente a nivel de
  ticket (no de línea).
- **Punto 5** (el modelo sigue llamándose `BreakdownTicket`): decisión
  sin código, vigente.
- **Punto 6** (origen del ticket como metadato informativo, nunca
  bloqueante): ya cierto desde `ORIGIN_AUTO` (S007), ninguna lógica
  condiciona el flujo al origen.
- **Punto 7** (ticket pregenerado es una fila real desde el primer
  instante): ya cierto desde `get_or_create_ticket_for_machine()`
  (S007) — crea el `BreakdownTicket` inmediatamente en rama CREATE.
- **Puntos 8-9** (transición de estado al grabar/editar la tarea,
  reapertura como efecto natural de editar): **cerrado en S009.** La
  casilla "finalizar" (`ticket_closed`) y el cierre a `CLOSED` ya
  existían desde S007, pero faltaba la rama contraria: cuando la
  casilla no está marcada, el ticket pasa a (o vuelve a) `IN_PROGRESS`
  -- cubre tanto un ticket recién creado (`OPEN`→`IN_PROGRESS`) como la
  reapertura de uno `CLOSED` al editar la tarea y destocar la casilla,
  sin acción administrativa aparte. El bloqueante que este punto tenía
  pendiente ("revisar/editar" debe entrar en modo edición real para
  cualquier rol autorizado) quedó resuelto para ADMIN/SUPERVISOR en
  S007 y para WORKSHOPBOSS en esta misma sesión S009.
- **Punto 10** (ticket `CLOSED` fuera de ventana 72h → siempre ticket
  nuevo): ya cierto desde S007 (`REOPEN_WINDOW_HOURS = 72` en
  `chat/ticket_resolution.py`).
- **Punto 11** (transacción atómica única por tarea): verificado en
  S009 -- el `with transaction.atomic()` de
  `WorkOrderEntryFormView.post()` (líneas 3746-4104) cubre la creación
  de líneas, la resolución/cierre de ticket y el consumo de repuestos
  pre-asignados, todo en el mismo bloque.
- **Punto 12** (`confirm_delivery_note()` deja de asignar directo a
  máquina sin ticket): implementado y **revertido** en la misma
  sesión S007 -- Miguel Ángel confirmó que generar el ticket ya al
  confirmar el albarán crea riesgo de tickets huérfanos.
  `confirm_delivery_note()` se queda con el planteamiento diferido de
  S001-S005. Decisión vigente, no pendiente.

**Alcance no cubierto, señalado para referencia futura:** la
resolución de ticket (bloque A/puntos 1-2) y el gate de caché de
clasificación (punto 4) solo están integrados en
`WorkOrderEntryFormView` (Vía A, creación directa de parte). Vía B/C
(STT/Upload confirm, `WorkOrderEntryConfirmView`) nunca vincula
`breakdown_ticket` a sus líneas -- alcance declarado desde S007, no
una limitación nueva de S009.

---

### Discusión original de S006 (conservada por trazabilidad — ver arriba el estado final de cada punto)



3. La pre-asignación de repuestos a máquina sigue exactamente como
   hoy (Caso B, sin cambios) — el requisito de ticket entra solo en
   el momento de la **materialización final** (cuando el mecánico
   cierra la tarea y el repuesto pasa de "reservado" a "gastado",
   sale del limbo).
4. **Clasificación de tarea, no solo de avería.** Se unifica con la
   llamada a Gemini que ya existía para familia/tipo de avería, pero
   se amplía: nuevo campo `tipo_tarea` en `BreakdownTicket` (AVERÍA /
   MEJORA / MANTENIMIENTO / FABRICACIÓN / ... — nomenclatura exacta a
   definir en la sesión de implementación). Familia/subcategoría de
   avería (ya existente) queda condicional a `tipo_tarea=AVERÍA`; para
   el resto, una **categorización libre** (texto que da Gemini, sin
   taxonomía rígida) — una mejora de dependencias o la fabricación de
   una escalera de acceso no encajan en "familia de avería". Disparo
   único, al grabar la tarea, **asíncrono (Celery)**, para no añadirle
   latencia al guardado del operario.
5. El modelo se sigue llamando `BreakdownTicket` — decidido no
   renombrarlo (alto riesgo, poco beneficio) aunque ahora cubra más
   que averías.
6. Origen del ticket (IVR/WhatsApp/panel-manual/auto-generado) es
   metadato informativo, nunca bloqueante — un ticket auto-generado a
   mitad de un parte carece de "reportante" externo y eso está bien,
   los campos quedan vacíos sin más.
7. **Qué es un "ticket pregenerado".** Es una fila real desde el
   primer instante (con operario ya asignado) — no hace falta un
   estado intermedio nuevo. Se "formaliza" (clasificación completa vía
   Gemini) al grabar la tarea concreta que lo originó, no al cerrar
   todo el parte.
8. **Transición de estado**, disparada al grabar/editar la tarea (no
   el parte completo): casilla "finalizar avería" marcada → `CLOSED`;
   desmarcada → `IN_PROGRESS`. Si la tarea no finaliza, el ticket
   queda `IN_PROGRESS`, listo para que el mismo operario u otro la
   retome (caso real: se deja una máquina por otra más urgente).
9. **Reapertura por error de cierre — NO es una acción administrativa
   aparte.** Es efecto natural de **editar la propia tarea**: si al
   grabarla se marcó "finalizar avería" por error, quien tenga permiso
   de edición sobre esa tarea la edita, destoca la casilla, y el
   ticket vuelve a `IN_PROGRESS` como consecuencia de esa edición —
   sin rol especial, sin motivo obligatorio aparte del rastro
   automático (quién editó, cuándo, qué tarea disparó la reapertura).
   Distinto del punto 1 (reapertura tras aviso de "¿es la misma
   avería?", que sí es una decisión nueva del mecánico sobre una tarea
   nueva). **Bloqueante original resuelto:** este punto dependía de
   que "revisar/editar" entrara en modo edición real para cualquier
   rol autorizado -- confirmado corregido para ADMIN/SUPERVISOR en
   S007 y para WORKSHOPBOSS en S009 (ver Sección 5), así que este
   punto ya no tiene bloqueante pendiente.
10. **Trabajo nuevo sobre un ticket ya `CLOSED` fuera de la ventana de
    72h** → siempre ticket nuevo, nunca se reutiliza el cerrado.

**Estado de los puntos 1-2 y 11-12 (para contexto, ya resueltos):**
puntos 1-2 integrados en producción en S007 (bloques A y B), con un
refinamiento en vivo sobre el punto 1: PAUSED cuenta también como
candidato abierto, y la confirmación al mecánico es obligatoria en
cuanto hay 1 o más candidatos (ya no hay enganche silencioso con 1
único candidato, a diferencia de como se cerró originalmente en
S006). Punto 12 implementado y **revertido** en la misma sesión S007
-- `confirm_delivery_note()` vuelve al planteamiento diferido de
S001-S005, la rama MACHINE sin ticket abierto sigue sin generar
ticket automáticamente. Punto 11 (transacción atómica única por
tarea) sin confirmación explícita de que se haya verificado tal cual
-- a comprobar cuando se implementen los puntos 4/8/9 (creación de
tarea + tipo_tarea + transición de estado en la misma operación).

---

## 5. Hoja de Ruta para la Siguiente Sesión

### ⚠️ PRIMER PUNTO OBLIGATORIO DE LA PRÓXIMA SESIÓN (S015) — Salvaguarda: un albarán = una máquina, código SIEMPRE en observaciones

**Pedido por Miguel Ángel en S014 (2026-07-13), sin implementar
todavía a petición suya explícita** ("dejarlo como primer punto del
orden del día de la siguiente sesión"). Especificación completa, en
sus propias palabras, sin resumir ni reinterpretar:

1. **Un albarán solo puede llevar líneas de una única máquina.**
   Queda prohibido un albarán con líneas para máquinas distintas — si
   el proveedor trae en un mismo albarán repuestos para 3 máquinas
   diferentes, tienen que ser 3 albaranes distintos (responsabilidad
   del proveedor al emitirlo, el sistema debe detectarlo y
   rechazarlo, no dividirlo automáticamente).
2. **El código de máquina (o departamento genérico) es obligatorio**
   en todo albarán — no puede faltar.
3. **Tiene que venir impreso/escrito por el proveedor en el campo
   "Observaciones" del propio albarán físico.** Se elimina por
   completo la tolerancia a anotaciones a mano (bolígrafo/lápiz)
   sobre la foto — ya no es un mecanismo válido de anotación.
4. **Nunca como artículo/línea de producto.** Si el código de máquina
   aparece extraído como si fuera un artículo (línea de la tabla de
   repuestos) en vez de en observaciones, el albarán se **rechaza**
   igualmente — no se acepta ni se reinterpreta.
5. **Excepción tolerada, pero también obligatoria por escrito en
   observaciones (nunca a mano):** cuando el repuesto es genérico y
   no va a una máquina concreta, se permite que observaciones diga
   "almacén", "almacén mecánico" o "taller mecánico" — pero tiene que
   estar ahí escrito por el proveedor, igual que un código de
   máquina real. Vacío no es válido bajo ningún concepto.
6. **Detección automática + modal de rechazo.** Cuando el sistema
   detecte un albarán que no cumple esta norma (código de máquina
   ausente de observaciones, código solo presente como artículo, o
   varias máquinas distintas entre las líneas de un mismo albarán),
   debe saltar automáticamente un modal indicando que falta el código
   de máquina/departamento del repuesto -- no se debe permitir
   confirmar el albarán en ese estado.

**Impacto técnico a valorar en S015 (no decidido todavía, ver punto
de partida de la sesión):** esto es un cambio de modelo de negocio
respecto al diseño actual, donde `DeliveryNote.general_machine_code_raw`
es opcional y cada `DeliveryNoteLine.machine_code_raw` puede apuntar a
una máquina distinta línea a línea. La nueva norma exige lo contrario:
una única máquina (o departamento genérico) por albarán completo,
obligatoria, leída específicamente del campo de observaciones del
documento -- probablemente implica cambios en el prompt de extracción
de `GeminiVisionExtractionService` (para que Gemini distinga
observaciones de la tabla de artículos y devuelva explícitamente si
encontró o no una anotación válida), en `resolve_line_assignment()`/
`confirm_delivery_note()` (para rechazar en vez de resolver
silenciosamente cuando no hay código o hay varios distintos), y en
`DeliveryNoteDetailView`/su plantilla (modal de rechazo). Empezar
S015 leyendo el prompt real de extracción actual y el flujo de
resolución real antes de diseñar nada -- no asumir la implementación
a partir de esta sola descripción.

---

### ESTADO AL CIERRE DE S008 (2026-07-07)

- **Pasos 1-6 — COMPLETADOS**, sin cambios desde S007.
- **Paso 7 — Alta de repuestos por canibalización. COMPLETADO
  (S008).** Página dedicada `SparePartSalvageCreateView`
  (`workorder_spare_parts`), accesible desde el botón "Alta por
  canibalización" en Almacén: descripción, contable/incontable +
  cantidad o nivel, máquina donante, parte de origen opcional
  (búsqueda libre HTMX entre partes recientes de esa máquina,
  `SparePartSalvageOriginLinesView`), destino (Almacén general, o
  directo a otra máquina con resolución automática de ticket abierto,
  igual que en los albaranes). Servicio
  `register_salvaged_entry()` en `spare_parts/services.py`. Sin
  migraciones -- el modelo ya soportaba `origin_type=SALVAGED` desde
  S001. **Asunción declarada, no bloqueante:** el anexo describía esto
  como "modal", implementado como página dedicada siguiendo el patrón
  del resto del módulo -- cambio solo de plantilla si Miguel Ángel
  prefiere un modal real.
- **Paso 8 — Persistencia real en la nube M365. BLOQUEADO**, sin
  cambios desde S006.
- **Niveles de stock incontable en castellano (S008, señalado por
  Miguel Ángel con captura de pantalla).** Nuevo filtro de plantilla
  `workorder_spare_parts/templatetags/spare_parts_extras.py`
  (`level_label`: FULL→Lleno, MEDIUM→Medio, LOW→Bajo, EMPTY→Vacío).
  Los códigos internos (valor de `<option>`, valor almacenado en
  `SparePartEntry.stock_level`, `StockAssignmentService.LEVEL_CHOICES`)
  se mantienen sin cambios -- solo la etiqueta visible. Aplicado en
  los 7 sitios donde aparecía el nivel (catálogo, almacén, alta
  rápida, canibalización, y los 3 fragmentos HTMX de consumo).
- **Resolución/alta automática de `Supplier` real por CIF (S008,
  confirmado por Miguel Ángel).** Nueva
  `resolve_or_create_supplier(company, raw_tax_id, name)` en
  `spare_parts/services.py` -- mismo principio que
  `resolve_recipient_company_code()`: siempre por CIF normalizado
  (`_normalise_tax_id`), nunca por nombre. Si no hay CIF extraído no
  resuelve ni crea nada (`supplier=None`, igual que antes). Si hay CIF
  y no coincide ningún `Supplier` existente, crea uno nuevo tipo
  `EXTERNAL` automáticamente. `confirm_delivery_note()` la invoca una
  vez por albarán y asigna el proveedor resuelto/creado en los 3
  puntos donde se crea/actualiza una `SparePartEntry`. Sin aplicación
  retroactiva a entradas ya existentes (confirmado por Miguel Ángel --
  los datos de prueba actuales se borrarán al final de las pruebas).
- **Alta rápida en almacén sin proveedor conocido + emparejamiento por
  descripción (S008, gap señalado por Miguel Ángel).** Nueva
  `register_uninventoried_warehouse_stock()`: alta directa en
  `status=WAREHOUSE`, `origin_type=SUPPLIER`, `supplier=None`,
  `reference=''`, para repuestos que un mecánico coge del almacén
  físico sin inventariar. Botón "Alta rápida" en Almacén
  (`SparePartQuickIntakeCreateView`). `confirm_delivery_note()` (rama
  WAREHOUSE) hace un segundo intento de emparejamiento por descripción
  normalizada a minúsculas (`_normalise_description`) cuando no hay
  coincidencia por referencia, buscando solo entre entradas sin
  referencia ni proveedor -- si empareja, aprende la referencia real
  del proveedor y le asigna el `Supplier` resuelto.
- **Modal de selección/alta rápida de repuesto en el propio parte de
  trabajo, Vía A (S008, gap señalado por Miguel Ángel).** En el bloque
  "Repuestos utilizados" de `form_entry.html`, cada campo Material
  tiene un botón que abre un modal único (autocompletado con
  debounce, búsqueda en `status=WAREHOUSE`, alta rápida inline sin
  salir del modal ni guardar la tarea) -- nuevo
  `panel/static/panel/js/material_picker.js`, dos endpoints JSON
  nuevos (`SparePartMaterialSearchView`,
  `SparePartMaterialQuickCreateView`, este formulario usa `fetch()`
  vanilla, no HTMX). `panel/views_operator.py`:
  `_parse_spare_parts_from_post()` resuelve
  `repuesto_N_spare_part_entry_pk` a un `SparePartEntry` real (None si
  se escribió a mano, compatibilidad retroactiva total); los dos
  `SparePartLine.objects.create()` (confirmación y creación directa)
  reciben `spare_part_entry`. **Alcance declarado, no bloqueante:**
  (1) solo Vía A -- STT/Upload confirm quedan fuera; (2) elegir un
  repuesto del almacén por esta vía solo vincula la línea al
  `SparePartEntry` real, no descuenta stock ni genera `StockMovement`
  todavía (integración distinta y mayor, no solicitada esta vez).

### DESVÍO A H07 EN S008 -- RESUELTO EL MISMO DÍA, VER ANEXO H07 PARA EL DETALLE COMPLETO

Incidente de producción (`TemplateDoesNotExist` en
`/panel/work-orders/digital/`) atendido por desvío durante S008.
Quedó sin resolver satisfactoriamente en el primer bloque de la
sesión, pero se retomó y **se resolvió por completo en un bloque
posterior de la misma sesión** (H10 no recibió ningún commit
adicional en ese bloque -- íntegramente desvío a H07). Causa raíz
confirmada por Miguel Ángel: la exportación Excel, el cómputo de
horas y el indicador de dieta que recordaba pertenecían realmente a
`admin_history.html` (`WorkOrderAdminHistoryView`), no a
`digital_list.html` -- la hipótesis principal dejada pendiente sí era
la correcta. Replicado en `digital_list.html`: columnas horas/dietas +
fila de totales, modal de exportación por plantilla (sustituyendo el
de 3 modos restaurado por error desde el histórico de Git), celdas de
precio ordinaria/extra en el Excel, y un nuevo filtro multi-operario
para ver la suma de horas extra/dietas de un subconjunto de operarios
sin exportar nada. Ver `ENTERPRISEBOT_ATTACHED_MILESTONE_V07.md`,
fila `S_H07_08`, para el detalle técnico completo. H10 permaneció EN
PROGRESO durante todo este desvío -- ningún paso de H10 quedó
bloqueado ni retrasado por él.

### ESTADO AL CIERRE DE S009 (2026-07-08) — SESIÓN DE CIERRE DE H10

1. **WORKSHOPBOSS en "Editar/Revisar" — RESUELTO.** Mismo alcance que
   SUPERVISOR/ADMIN, confirmado por Miguel Ángel e implementado
   (`_resolve_editable_work_order()`, redirección post-guardado,
   docstrings de `WorkOrderFormAccessMixin`).
2. **Paso 4-bis — DISEÑO COMPLETO CERRADO (12/12 puntos).** Diseño de
   S006 recuperado del historial de git tras detectarse que se había
   perdido del anexo (ver Sección 4-bis arriba). Puntos 4/8/9
   implementados en S009: `BreakdownTicket.tipo_tarea`/
   `task_category_free` (migración `chat.0010`), `classify_task()`
   unifica en una sola llamada Gemini la clasificación de tipo de
   tarea con avería (categoría/subcategoría) o categorización libre;
   `classify_fault_line` bifurca según si la línea tiene ticket
   asociado; corregido el hueco de transición a `IN_PROGRESS` cuando
   la casilla "finalizar" no está marcada (cubre tanto ticket
   recién creado como reapertura por edición). Resto de puntos (1-3,
   5-7, 10-11) verificados ya resueltos por S007 sin necesitar cambio
   de código; punto 12 confirmado revertido por decisión.
3. **Nueva app `delivery_notes`** — CRUD de administración de
   albaranes (listado filtrable, detalle de solo lectura para
   `ASSIGNED`, borrado seguro solo para no confirmados), visible en
   `Administración → Albaranes` (ahora dentro de "Taller Mecánico" /
   Almacén, ver punto 8) para ADMIN/SUPERVISOR/WORKSHOPBOSS. Sin
   modelos propios, reutiliza `DeliveryNote`/`DeliveryNoteLine` de
   `spare_parts`.
4. **`DeliveryNote.supplier` (FK nuevo, migración `spare_parts.0007`)**
   — gap señalado por Miguel Ángel: dos albaranes del mismo proveedor
   real (mismo CIF) mostraban nombres distintos porque cada uno solo
   guardaba el texto libre impreso en su propio documento.
   `confirm_delivery_note()` ahora asigna también el `Supplier` ya
   resuelto por CIF al propio `DeliveryNote`, no solo a cada
   `SparePartEntry`. Backfill aplicado a los 2 albaranes reales ya
   confirmados antes del fix.
5. **Prompt de extracción de albaranes ampliado** — Gemini Vision
   ahora busca el código de máquina/centro de gasto en tres fuentes
   (anotación suelta tipo `#CÓDIGO#`, campo impreso "Observaciones",
   línea-nota tipo "TEXTO" con precio 0 que algunos proveedores usan
   en vez de anotar junto al artículo), en vez de solo la primera.
   Decisión explícita de Miguel Ángel: no se puede anticipar la
   convención de cada proveedor, así que se ensancha la red para los
   patrones conocidos y se deja en blanco (revisión manual o alta
   rápida) cuando no aparece en ninguna -- nunca se inventa un código.
6. **Reestructuración completa de la sidebar** (`_nav_items.html`),
   dos iteraciones a petición de Miguel Ángel:
   - 1ª iteración: de 8 secciones acordeón a 5 grupos temáticos
     (Administración / Taller / Centro de gasto / Almacén /
     Mecánicos), sin tocar permisos por ítem.
   - 2ª iteración ("simplificar al máximo"): Taller + Centro de
     gasto + Almacén + Mecánicos fusionados en una única sección
     "Taller Mecánico" con 4 subgrupos visuales internos (encabezados
     sin colapsar). Sidebar final: Inicio, Mi perfil, Telefonía,
     Administración, Taller Mecánico, Asistencia, Django Admin.
   - Verificación automática en ambas iteraciones (comparación de
     conjuntos de `active_nav` y de `{% url %}` contra el archivo
     previo) de que ningún ítem cambió de rol efectivo, solo de
     ubicación visual.
   - Además: tabla de detalle de "Secciones activas" quitada del
     dashboard de Inicio (se queda solo la tarjeta resumen);
     "Configuración empresa" eliminada de la sidebar (vista/URL
     siguen vivas, no se borraron) -- su único campo editable real
     (franja horaria nocturna) se cubre ahora con `NightSchedule`
     (`is_default=True`), que ya tenía prioridad sobre
     `Company.night_start`/`night_end` en el motor de presupuestos
     pero no tenía enlace en ningún sitio del panel -- ahora vive en
     Asistencia como "Franja nocturna".
   - Fix de contraste: las etiquetas de los 4 subgrupos usaban
     `text-muted` de Bootstrap (gris para fondos claros), casi
     ilegibles sobre el fondo oscuro del sidebar -- nueva clase
     `.sidebar-subgroup-label` (`rgba(255,255,255,0.6)`) en
     `panel.css`.
7. **Desvíos a H07 resueltos el mismo día** (columna Dieta + total en
   `admin_history.html`, y exclusión de partes de periodos liquidados
   de la pestaña Revisados) -- ver nota de desvío más abajo y el
   detalle técnico completo en `ENTERPRISEBOT_ATTACHED_MILESTONE_V07.md`.
8. **Base de datos de pruebas limpiada** (`delete_all_spare_parts_data
   --apply`) a petición de Miguel Ángel para empezar a operar con
   albaranes reales -- 1 `DeliveryNote` de prueba (`ASSIGNED`) + 3
   `SparePartEntry` (limbo) borrados. `Supplier` y partes de trabajo
   no se tocaron.
9. Además, se detectó y corrigió una desincronización real entre
   servidor y GitHub heredada de sesiones anteriores: 3 migraciones de
   `spare_parts` (S004-S006) y 2 archivos JS (`form_entry_assets.js`,
   H10; `wizard.js`, H18) que ya estaban aplicados/en producción en el
   servidor pero nunca se habían commiteado. Persistidos desde el
   propio servidor.
10. Paso 8 (M365) sigue bloqueado -- sin novedades de Miguel Ángel con
    el administrador de Grupo Álvarez en toda la sesión.

### NOTA DE DESVÍO A H17 (S011)

Durante S011 (2026-07-09), sesión centrada en H17, se atendió por
desvío una petición puntual de Miguel Ángel sobre `form_entry.html`
(Vía A, campo `WorkOrderEntryLine.ticket_closed` del Paso 4-bis de
este mismo hito): modal de aviso cuando un bloque con ticket de
avería asociado se guarda sin marcar «Avería resuelta — cerrar
ticket». Detalle técnico completo, commit y decisiones en
`ENTERPRISEBOT_ATTACHED_MILESTONE_V17.md`, fila S011 del Registro de
Sesiones de ese anexo. Archivos nuevos/tocados:
`panel/templates/panel/_ticket_close_warning_modal.html` (nuevo),
`panel/templates/panel/operator/form_entry.html`,
`panel/static/panel/js/form_entry_modal.js`. No reabre la hoja de
ruta de H10 — sigue íntegramente pendiente solo el Paso 8 (M365).

### NOTA DE DESVÍO A H07 (S009)

Dos incidencias de producción sobre `admin_history.html`/
`WorkOrderAdminHistoryView` atendidas por desvío durante S009, sin
bloquear ni retrasar H10: columna "Dieta" (por parte + total en la
pestaña Revisados) y exclusión de partes de periodos ya liquidados de
esa misma pestaña. Detalle técnico completo, commits y decisiones en
`ENTERPRISEBOT_ATTACHED_MILESTONE_V07.md`, filas S009 (registradas en
este mismo cierre).

### CIERRE DE HITO — H10 PASA A PAUSADO (PCH EN S009)

A petición explícita de Miguel Ángel, H10 se pausa al cierre de S009
y H20 (Laboratorio de Análisis Unificado) pasa a EN PROGRESO -- ver
`ENTERPRISEBOT_ANNEX_ROUTER.md`. Motivo: la hoja de ruta propia de
H10 está completa salvo el Paso 8 (M365), bloqueado por un tercero
externo sin fecha prevista.

**Pendiente para cuando se retome H10:** el Paso 8 original (persistencia
en la nube vía M365/SharePoint) queda **superado, no completado por
esa vía** -- en S014 se pivotó a Google Drive en su lugar (ver fila
S014 abajo), que ya cubre el objetivo de fondo del Paso 8 (fotos de
albarán fuera del servidor, en la nube). El bloqueo original de M365
(consentimiento de administrador de Grupo Álvarez) queda sin resolver
y sin necesidad de resolverse -- no hay ninguna acción pendiente sobre
M365 salvo que Miguel Ángel quiera retomarlo por otro motivo. **Bloque
B (fecha DD/MM/AAAA, unicidad `delivery_number`, subida
síncrono→asíncrono) -- CERRADO COMPLETO en S014, ver fila S014
abajo.** Nada pendiente de la hoja de ruta original de H10 salvo lo
anotado en la fila S014 (limpieza de `static/` versionado, ver nota
en esa fila).

---



| Sesion | Fecha | Pasos trabajados | Resumen |
|--------|-------|-----------------|---------|
| S014 | 2026-07-13 | Bloque B CERRADO completo (fecha ES, unicidad delivery_number, subida async); persistencia Google Drive (sustituye email, nuevo objetivo fuera de la hoja de ruta original); nuevo flujo de migraciones de la plataforma; fix critico de deploy.yml; reinicio condicional de Always-on Tasks | **Sesion desviada por completo desde H17 (EN PROGRESO) -- Caso A, sin PCH, marcador sin mover -- ver nota de desvio en `ENTERPRISEBOT_ATTACHED_MILESTONE_V17.md`.** A peticion expresa de Miguel Angel: "terminar con el tema de los albaranes". **Bloque B cerrado (commits `40efbac`/`9bb32ee`):** formato de fecha DD/MM/AAAA en `spare_parts/tasks.py` (antes ISO por defecto); `UniqueConstraint('company','delivery_number')` condicional a no vacio en `DeliveryNote` (migracion 0008, mismo patron que `Supplier.tax_id`); subida sincrono->asincrono -- `DeliveryNoteUploadView.post()` ahora solo guarda el archivo (status PENDING) y encola `extract_delivery_note_data()` (Celery), la extraccion Gemini corre en segundo plano; nuevo estado `ERROR` en `DeliveryNote.STATUS_CHOICES` (extraccion fallida, archivo no se borra, reintento manual via `DeliveryNoteRetryExtractionView`); plantillas actualizadas para los 4 estados reales (PENDING con spinner + auto-refresh, ERROR con boton reintentar, PROCESSED/ASSIGNED con formulario). **Persistencia en Google Drive (commit `ea70dcd`), sustituye por completo el envio por correo (Twilio Email, S004-S005):** decision tecnica clave, verificada en linea -- OAuth 2.0 delegado a la cuenta de Google de Grupo Alvarez (billing account "Grupo Alvarez", mismo proyecto GCP `gen-lang-client-0961484137` que Vertex AI), NUNCA Service Account (confirmado empiricamente: un Service Account no tiene cuota de almacenamiento propia fuera de una Shared Drive de Workspace, y esta cuenta es personal, sin Workspace -- solo "Mi unidad"). Scope minimo `drive.file`; carpeta raiz "EnterpriseBot - Albaranes" creada por el propio flujo de autorizacion (nunca a mano por un humano, quedaria fuera del scope). Pantalla de consentimiento OAuth puesta en "In production" (no "Testing") -- verificado que en Testing el refresh_token caduca a los 7 dias sin aviso. Nuevo modulo `spare_parts/gdrive_service.py`, nuevas vistas de autorizacion de un solo uso `panel/views_gdrive_setup.py` (`/panel/gdrive/authorize/` + `/panel/gdrive/oauth-callback/`, rol ADMIN), campos `DeliveryNote.drive_file_id`/`drive_web_link` (migracion 0009), nueva tarea `upload_delivery_note_photo_to_drive()` sustituye a `send_delivery_note_photo_email()` (eliminada, codigo muerto). Estructura: carpeta raiz + subcarpetas AAAA-MM; acceso "cualquiera con el enlace puede ver" en cada archivo (mismo acceso que ya tiene cualquiera que vea el listado de albaranes). Autorizacion completada en produccion por Miguel Angel al cierre de esta sesion. **Nuevo flujo de migraciones de toda la plataforma (cambio de alcance mayor a H10, afecta a todos los proyectos):** tras una discusion larga sobre el ciclo historico del proyecto, Miguel Angel decidio de forma explicita y final que el modelo escriba el archivo de migracion directamente (antes: siempre manual en servidor via `makemigrations`). Documento maestro 4.5 reescrito (elimina la prohibicion absoluta de generar migraciones); skill `com-migrations` reescrita de raiz (nueva seccion 1/2, guia de estilo y casos de atencion especial -- renombrados, campos `null=False` sin default sobre tablas con datos, migraciones candidatas multiples; seccion 3 con las excepciones que siguen siendo manuales: `--fake`, squash, reparacion de historial). **Incidente critico de despliegue, diagnosticado y corregido en la misma sesion:** `deploy.yml` tenia un bug real (`ssh ... \| tee archivo` sin `set -o pipefail` en el shell exterior de la Action) que hacia que un `git pull` fallido en el servidor se reportara en verde -- verificado contra issues abiertos de `actions/runner` (nº 1955, 1212, 4459), no de memoria. Consecuencia real: dos despliegues seguidos (`9bb32ee`, `ea70dcd`) nunca llegaron a produccion pese al "exito" reportado, hasta que un sintoma indirecto (paquetes ausentes en `requirements.txt` regenerado) lo destapo -- causa raiz: archivo de migracion huerfano sin comitear en el servidor, dejado por un `makemigrations` manual de una sesion anterior, chocando con el `git pull`. Corregido con `set -o pipefail` explicito (commit `54d6d1b`); recuperacion manual completa (limpieza del archivo huerfano, pull, migrate, collectstatic, `pip-compile`/`pip-sync` de las dependencias nuevas de Drive) verificada con datos reales en las tres puntas (GitHub, workspace del modelo, servidor) tras el incidente. **Ampliacion del despliegue automatico (commit `8f8164e`), a peticion de Miguel Angel:** reinicio condicional de las Always-on Tasks de EnterpriseBot (bridge de voz id `234987`, worker Celery id `242133`, confirmados via API en esta sesion) segun el `git diff` real del push -- nunca incondicional, para no cortar llamadas IVR en curso por cambios que no afectan al bridge. **Skills de sistema actualizadas** (fuera de este repo): `com-migrations` (reescrita de raiz), `nfs-enterprisebot-edit` (nueva regla: nunca dar por bueno un despliegue con migracion solo por el "exito" de la API de GitHub Actions, verificar siempre con datos reales), `com-bash-commands` (prohibicion de placeholders sin rellenar en cajas de codigo; los estandares de sesion no se suspenden en incidencias), `nfs-enterprisebot-pcs` (PASO 9 reescrito, ya no es aviso manual). **Pendiente, sin urgencia:** `static/panel/css/panel.css` y otros artefactos de `collectstatic` aparecen versionados en git en el servidor (deberian estar en `.gitignore`) -- detectado en el `working tree` del servidor durante la recuperacion del incidente, sin investigar todavia, no bloquea nada. **Verificación real post-despliegue del reinicio condicional (commit `f1c620e`):** disparado deliberadamente con un cambio real en `spare_parts/tasks.py` -- confirmado en dos puntas a la vez: `curl -sf` del Action en verde (paso "Reiniciar Always-on Tasks" del run `29241965652`) y, más importante, Miguel Ángel confirmó en su propio dashboard de PythonAnywhere el cambio de estado real del worker Celery (id `242133`): `Running` → `Starting` → `Running` de nuevo (~4 minutos). Reinicio condicional funcional al 100%, verificado con datos reales de ambas fuentes, no solo con el status de la API de GitHub Actions. |
| S013 | 2026-07-13 | Bloque B punto 1 (incidencia real resuelta, salvaguarda general aún pendiente) + punto 3 (CRUD con progreso de asignación) | **Sesión desviada por completo desde H17 (EN PROGRESO) — Caso A, sin PCH, marcador sin mover — ver nota de desvío en `ENTERPRISEBOT_ATTACHED_MILESTONE_V17.md`.** **Incidencia real de duplicado (Bloque B punto 1):** albarán `BA/2606201` procesado dos veces (subida duplicada, 13s de diferencia) — id=14 (extracción defectuosa, fecha imposible, línea mal anotada a máquina P14 leída como R14 por Gemini a causa de un guión manuscrito de José Antonio Vargas, nunca confirmado, sin `SparePartEntry` ni stock) borrado; id=15 (confirmado, pero con sus 2 líneas mal asignadas a R14 por el mismo motivo del guión) corregido a P14 y sus 2 `SparePartEntry` (`REP-000003`/`REP-000004`) consumidas contra la línea real de Pablo Cañamero del 09/07 ("Grupo averiado / Montar grupo en eje") vía `StockAssignmentService.consume_pre_assigned()` -- las 10 unidades de cada repuesto se pasaron íntegras al parte a petición de Miguel Ángel (inventario a 0), pendiente de que hable con Pablo para decidir el criterio de unidades parciales en el futuro (repuestos incontables entrando en cantidades variables). Diagnóstico y corrección íntegramente vía Django shell con scripts no interactivos, verificando cada paso contra la salida real antes de la siguiente escritura. **Bloque B punto 3 -- CRUD con ciclo de vida:** diseñado `DeliveryNote.assignment_progress()` (LIMBO/PARTIAL/FULL según cuántas líneas MACHINE de un albarán confirmado ya salieron del limbo de pre-asignación) y enganchado a la vista real **`delivery_notes.views.DeliveryNoteAdminListView`** (app creada en S009, con listado/detalle/borrado ya completos) -- nueva columna "Asignación" en `delivery_notes/templates/delivery_notes/list.html`. **Bloque B puntos 1 (salvaguarda general de fecha DD/MM/AAAA en el correo de confirmación), 1 (constraint de unicidad por `delivery_number`) y 2 (conversión síncrono→asíncrono) quedan sin empezar** -- ver hoja de ruta actualizada abajo. **Error propio corregido en la misma sesión:** se llegó a construir una vista de listado duplicada (`spare_parts.views.DeliveryNoteListView`) y a modificar el sidebar (`_nav_items.html`) creyendo erróneamente, sin haberlo verificado de verdad, que `{% url 'delivery_notes:list' %}` estaba roto -- Miguel Ángel confirmó dos veces que el panel nunca estuvo caído; revisado el propio anexo H10 al final de la sesión, se confirmó que la app `delivery_notes` de S009 sí existía y funcionaba. Revertido por completo (vista, URL y template duplicados eliminados, sidebar restaurado a su estado y gate de rol originales) antes de cerrar, conservando únicamente `assignment_progress()` reubicado en la vista real. **Fuera de H10 -- infraestructura de despliegue de la plataforma (a petición de Miguel Ángel, "automatizamos todo, con migrate incluido"):** `.github/workflows/deploy.yml` nuevo -- cada push a `main` despliega solo en PythonAnywhere vía SSH (clave dedicada `github-actions-deploy@enterprisebot`) + API: `git pull` + `migrate --noinput` + `collectstatic --noinput --clear` + reload, con resumen informativo en cada ejecución. Verificado funcionando de extremo a extremo (`https://github.com/MiguelaeTxio/EnterpriseBot/actions/runs/29228856384` y `.../29229340651`). Skills de sistema actualizadas para reflejarlo: `com-migrations` (ciclo 6/6.1 reescrito, nueva sección 6.2 de excepciones), `com-static`, `nfs-enterprisebot-edit`, `nfs-enterprisebot-pcs` (ya no genera script de despliegue manual). Además, nueva regla vinculante en `com-standards` tras un incidente real de campo de modelo inventado (`CompanyUser.first_name`). |
| S009 | 2026-07-08 | WORKSHOPBOSS en Editar/Revisar; Paso 4-bis 12/12 cerrado; app delivery_notes; DeliveryNote.supplier; prompt de albaranes ampliado; sidebar reestructurada (2 iteraciones); desvíos a H07; limpieza BD; PCH a H20 | Sesión de cierre de H10. Ver detalle completo en "ESTADO AL CIERRE DE S009" arriba. H10 pasa a PAUSADO, H20 pasa a EN PROGRESO. |
| S008 | 2026-07-07 | Paso 7 completo; niveles en castellano; Supplier por CIF; alta rápida + emparejamiento por descripción; modal de material en el parte (Vía A); desvío a H07 (resuelto en bloque posterior el mismo día) | Ver detalle completo en "ESTADO AL CIERRE DE S008" arriba. Ocho commits de código a H10 + desvío de varios commits a H07 (ver anexo H07). Sesión cerrada a petición de Miguel Ángel con el incidente de `digital_list.html` sin resolver -- resuelto ese mismo día en un bloque posterior de la sesión (H10 no recibió ningún commit adicional en ese bloque, íntegramente desvío a H07): causa raíz real era que la exportación/horas/dieta que Miguel Ángel recordaba pertenecía a `admin_history.html`, no a `digital_list.html` -- replicado allí junto con un nuevo filtro multi-operario. Ver anexo H07, fila `S_H07_08`, para el detalle técnico completo. |
| S001 | 2026-06-30 | Paso 1 completo, Paso 2 parcial | App `spare_parts` creada: modelos `DeliveryNote`/`DeliveryNoteLine`/`SparePartEntry`/`StockMovement` con limbo de pre-asignación (status WAREHOUSE/PRE_ASSIGNED/CONSUMED), procedencia dual (origin_type SUPPLIER/SALVAGED para canibalización interna), relación con `work_order_processor.SparePartLine` (FK `spare_part_entry` nueva). Migración cruzada aplicada, admin registrado, reload OK. `GeminiVisionExtractionService` construido con `gemini-3.5-flash` (no 2.5, deuda técnica documentada en doc-master-enterprisebot 4.1.1). App compartida `ai_services` creada por principio DRY — `work_order_processor.services` migrado al mismo helper. Desvío completo a H18 por incidencia crítica de regresión del planificador de ruta (autocompletado roto): diagnosticado y resuelto sustituyendo `PlaceAutocompleteElement` por implementación propia — ver anexo H18 S018 para el detalle técnico completo. Paso 2 de H10 queda pendiente de integrar `GeminiVisionExtractionService.extract()` en `DeliveryNoteUploadView` (Paso 3) y testar con albaranes reales. |

### CORRECCIÓN CATÁLOGO/ALMACÉN (S007, a petición de Miguel Ángel)

Se habían construido como la misma vista (`SparePartEntryListView`,
`catalog_list`) mostrada con dos etiquetas de sidebar distintas. Son
dos entidades diferentes, con datos y usuarios distintos:

- **Catálogo de repuestos (Administración, ADMIN/SUPERVISOR
  únicamente):** registro maestro -- referencia, descripción,
  **proveedor** y **precio de compra** (columnas nuevas en S007, antes
  no se mostraban en ningún sitio). Sin limbo, sin avisos de
  antigüedad, sin gestión de stock físico.
- **Almacén (Mecánicos, ADMIN/SUPERVISOR/WORKSHOP/WORKSHOPBOSS):**
  stock/nivel, limbo de pre-asignación con avisos de antigüedad,
  acción "Devolver a almacén", y **ajuste de stock directo por los
  propios mecánicos** (`SparePartStockAdjustView`, nueva -- "el
  inventario lo van a gestionar los propios mecánicos", cita literal
  de Miguel Ángel) sin pasar por el formulario completo de catálogo.
  Sin proveedor, sin precio.

Sidebar (`panel/_nav_items.html`) y mapeo `NAV_TO_ACC` corregidos en
consecuencia -- el catálogo abre el acordeón de Administración, el
almacén el de Mecánicos (antes ambos abrían Mecánicos por error).

### BUGS ENCONTRADOS Y CORREGIDOS EN S007 (fuera de la hoja de ruta de H10)

1. **"Editar/Revisar" no entraba en modo edición real para ADMIN.**
   `WorkOrderEntryFormView.get()`/`.post()` exigían `uploaded_by=cu,
   reviewed=False` en la consulta del `WorkOrder` -- correcto solo
   para el operario autoeditando lo suyo, no para ADMIN revisando el
   parte de otro operario o uno ya revisado. Nuevo helper
   `_resolve_editable_work_order()` con alcance según rol.
2. **SUPERVISOR (p. ej. Carolina, quien hace el cómputo de horas)
   recibía 403 en el mismo flujo.** Ya existía en el propio código un
   mixin construido para esto (`WorkOrderFormAccessMixin`, en
   `panel/mixins.py`) pero nunca se había conectado a la vista --
   conectado en S007.
3. **`ImportError` real en producción, causa raíz del 500 en
   `/panel/repuestos/resolucion-ticket/`:** `chat/services.py` tenía,
   desde H17, un import roto a nivel de módulo
   (`ChatRoom`/`ChatMessage`, modelos eliminados en esa misma hito) --
   nadie lo había notado porque nada volvía a importar ese archivo
   hasta que el Paso 4-bis lo hizo por primera vez. Verificado
   exhaustivamente que **tres archivos completos** (`chat/services.py`,
   `chat/views.py`, `chat/management/commands/init_chat_rooms.py`)
   quedaron huérfanos e inalcanzables desde H17 sin que nadie lo
   detectara -- retirados a placeholders vacíos (mismo patrón ya
   usado en `chat/tasks.py` cuando se hizo H17). La función compartida
   de resolución de tickets se sacó a su propio módulo limpio,
   `chat/ticket_resolution.py`.
4. **Repuestos pre-asignados solo a máquina (sin ticket) no aparecían
   en ningún sitio del formulario.** `WorkOrderEntryPartsReviewView` y
   la condición de desvío en `WorkOrderEntryFormView.post()` solo
   miraban `breakdown_ticket` -- ampliadas para incluir también
   líneas cuya máquina (sin ticket) tuviera repuestos `PRE_ASSIGNED`
   pendientes.

### OTROS CAMBIOS DE S007 (fuera de H10, mencionados aquí por trazabilidad)

- Destinatario temporal de las fotos de albarán cambiado de
  `nummenor@proton.me` a `nummenor@gmail.com` (sigue sin ser
  `administracion@gruasalvarez.com`, la cuarentena de M365 Defender
  sigue sin resolver).
- Limpieza de datos de prueba: comandos de gestión
  `delete_all_breakdown_tickets` y `delete_all_spare_parts_data`
  (ambos con dry-run por defecto), ejecutados con `--apply` para dejar
  la base de datos limpia antes de la prueba de campo con mecánicos
  (que finalmente no se hizo hoy -- no había nadie en el taller).
- Nuevo campo `DeliveryNote.general_machine_code_raw`: un albarán
  puede llevar una única anotación `#CÓDIGO#` general (fuera de
  cualquier línea concreta) indicando que el albarán ENTERO es para
  una máquina/centro de gasto -- gap real detectado por Miguel Ángel,
  no estaba contemplado hasta ahora. Usado como respaldo solo para las
  líneas sin anotación propia.

### RESUELTO EN S009 (pendiente desde S007)

- **`WORKSHOPBOSS` y el acceso "Editar/Revisar":** confirmado por
  Miguel Ángel en S009 -- mismo alcance que `SUPERVISOR`, ya no
  restringido a lo propio. `_resolve_editable_work_order()` ampliada,
  igual que ya estaba para `SUPERVISOR`. Ver Sección 5,
  "ESTADO AL CIERRE DE S009".

---



| Sesion | Fecha | Pasos trabajados | Resumen |
|--------|-------|-----------------|---------|
| S001 | 2026-06-30 | Paso 1 completo, Paso 2 parcial | App `spare_parts` creada: modelos `DeliveryNote`/`DeliveryNoteLine`/`SparePartEntry`/`StockMovement` con limbo de pre-asignación (status WAREHOUSE/PRE_ASSIGNED/CONSUMED), procedencia dual (origin_type SUPPLIER/SALVAGED para canibalización interna), relación con `work_order_processor.SparePartLine` (FK `spare_part_entry` nueva). Migración cruzada aplicada, admin registrado, reload OK. `GeminiVisionExtractionService` construido con `gemini-3.5-flash` (no 2.5, deuda técnica documentada en doc-master-enterprisebot 4.1.1). App compartida `ai_services` creada por principio DRY — `work_order_processor.services` migrado al mismo helper. Desvío completo a H18 por incidencia crítica de regresión del planificador de ruta (autocompletado roto): diagnosticado y resuelto sustituyendo `PlaceAutocompleteElement` por implementación propia — ver anexo H18 S018 para el detalle técnico completo. Paso 2 de H10 queda pendiente de integrar `GeminiVisionExtractionService.extract()` en `DeliveryNoteUploadView` (Paso 3) y testar con albaranes reales. |
| S002 | 2026-07-02 | NOTA DE DESVÍO — sin trabajo directo en H10 | H10 se mantuvo EN PROGRESO durante toda la sesión sin recibir ningún avance directo. Sesión desviada por completo a H16 (motor de presupuestos: importación de tarifas por PDF, modo manual del wizard, control de acceso granular, mapa de ruta en desglose — ver anexo H16 S055) y a H18 (bug de peajes ida/vuelta y tramos AP-7, fechas pasadas en planificación de ruta, fix drag-and-drop del planificador — ver anexo H18 S019). Al cierre de sesión se ejecutó PCH: `eb-annex-router` mueve `← EN PROGRESO` de H10 a H07 (incidencia de pausa de comida en jornada partida, partes digitales). La hoja de ruta de H10 (Sección 5) queda intacta, con el Paso 3 pendiente exactamente como estaba, para cuando `eb-annex-router` vuelva a marcar H10 EN PROGRESO. |
| S003 | 2026-07-02 | Paso 2 completo, Paso 3 puntos 1-3 completos, punto 4 iniciado | Añadido campo `machine_code_raw` a `DeliveryNoteLine` (migración `0002_deliverynoteline_machine_code_raw`, aplicada OK). Añadidas a `spare_parts/services.py`: `resolve_line_assignment()` (detecta WAREHOUSE vía alias ALM/AL/ALMACEN/ALMACÉN/WAREHOUSE, o MACHINE reutilizando `_normalise_machine_code()`/`_resolve_machine_asset()` de `work_order_processor.services` por DRY) y `confirm_delivery_note()` (ejecuta el circuito completo de la sección 3.1: SparePartEntry WAREHOUSE con suma de stock, o PRE_ASSIGNED en el limbo con búsqueda de BreakdownTicket OPEN/IN_PROGRESS, y StockMovement IN en ambos casos). Creadas `DeliveryNoteUploadView`, `DeliveryNoteDetailView`, `DeliveryNoteConfirmView` (spare_parts/views.py, protegidas con `CompanyUserRequiredMixin`), `spare_parts/urls.py` (namespace `spare_parts`), y las plantillas `delivery_note_upload.html`/`delivery_note_detail.html` (extienden `panel/base.html`). Añadido include en `enterprise_core/urls.py` (`panel/spare-parts/`). Renombrada la sección del sidebar "Operarios" → "Mecánicos" (`panel/_nav_items.html`) y añadido el ítem "Subir albarán" (WORKSHOP/ADMIN). Reescrita `delivery_note_upload.html` con captura directa por cámara, adaptada del prototipo `PAIRS/delivery_note_processor/camera_capture.js` (getUserMedia + canvas.toBlob), pero inyectando el archivo capturado vía `DataTransfer` en el `<input>` existente y reutilizando el submit normal del formulario en vez del endpoint AJAX/JSON del original — cero cambios en la vista Python para esa parte. Todos los despliegues vía `com-install-files` y `put` directo, con reload 200 OK confirmado en cada bloque. Miguel Ángel ha probado la extracción con un albarán real de Grupo Álvarez ("Grúas Adolfo Álvarez, SL") en producción — la extracción Gemini Vision funciona bien — pero ha detectado dos carencias de modelo de datos (empresa del grupo destinataria del albarán, y centro de gasto por línea de repuesto anotado en el albarán físico) que impiden dar el punto 4 (test end-to-end) por completado. Ver Sección 5 para el detalle y el plan de la siguiente sesión. |
| S004 | 2026-07-03 | H10 Paso 3 completado y validado E2E; envío por correo del albarán (pendiente de autenticación de dominio externa); tres fixes encadenados en H07 (botón "Guardar tareas"); fix bug alta WhatsApp; alta sección Guardas | Primera sesión del flujo directo contra GitHub (`nfs-enterprisebot-*`), con token de sesión. **H10:** Miguel Ángel trajo la especificación de los dos datos bloqueantes del Paso 3 punto 4 — empresa destinataria por CIF (GRA/TRA/GRG) y centro de gasto general por línea vía convención de almohadillas contra los 9 `MachineAsset` `EMPRESA_*`. Implementado en `spare_parts/{models,services,views}.py` y `delivery_note_detail.html`, con migración `0003`. Validado end-to-end en producción con un albarán real (BA/2604254): destinatario resuelto a GRA, tres líneas resueltas a S06/V02/S02, confirmado dato a dato por Miguel Ángel contra la foto física; registro de prueba borrado a petición suya tras la validación. **Envío por correo (S004, nuevo):** `spare_parts/tasks.py`, tarea Celery que adjunta el archivo y lo borra del servidor tras confirmar. Primer intento con `sendgrid-python` revertido tras verificación online y captura de Miguel Ángel: el producto correcto es la API nativa **Twilio Email** (`comms.twilio.com/v1/Emails`), reutiliza `TWILIO_API_KEY_SID`/`SECRET` ya existentes. Bloqueado al cierre por autenticación de dominio DNS de `gruasalvarez.com`, que Miguel Ángel no gestiona — delegado a un tercero vía "Forward instructions to a colleague" de Twilio (Manual setup), sin acción de código pendiente. **Fuera de la hoja de ruta de H10:** (1) bug de alta por WhatsApp — `OnboardingService._create_user()` ignoraba `Section.default_role`, corregido; (2) sección `Guardas` dada de alta (`id=15`, `default_role=WORKSHOP`, sin IVR), con desactivación del `CallFlow` auto-generado por la señal `auto_manage_section_call_flow`; (3) H07, botón "Guardar tareas" del formulario de partes — tres bugs encadenados confirmados empíricamente, dos de ellos verificando directamente en BD: botón sin listener de clic (nunca llegaba al servidor); fix aplicado por error a `static/panel/js/...` (que es `STATIC_ROOT`, no la fuente) en vez de `panel/static/panel/js/...` (la fuente real vía `AppDirectoriesFinder`); y dos gates de confirmación (`save_confirmed`, `meter_warnings`) más el gate de 8h de jornada en `WorkOrderEntryFormView.post()` sin la excepción `form_action != "save_blocks"` que sí tenía correctamente la vista hermana `WorkOrderEntryConfirmView` — bloqueaban en silencio (sin error visible) todo guardado parcial. Confirmado en real por Miguel Ángel: persiste, aparece "En curso" en Mis partes, y se recupera al pulsar "Nuevo parte". Ocho commits de código + un commit de cierre de documentación pusheados a GitHub. Nuevo tema para la próxima sesión, sin diagnosticar: familias/tipos de avería en inglés en el laboratorio de análisis (y posiblemente en más sitios). |
| S005 | ¿? | Backend de `StockAssignmentService` completo (Paso 4); fix familias/tipos de avería a español; dominio Twilio resuelto | **Fila reparada a posteriori en S006, sin fecha ni detalle de commits recuperable** — esta sesión ocurrió (confirmado por Miguel Ángel al arrancar S006: family/subcategoría de avería en castellano y dominio Twilio resueltos, ambos vistos en producción) pero nunca se registró aquí en su momento. No se reconstruye el detalle de commits por no tener acceso a ese rango exacto de forma fiable — se deja esta fila mínima para no romper la numeración correlativa de sesiones. |
| S006 | 2026-07-07 | H10 Paso 4 bloques 1/4-3/4 completados (app `workorder_spare_parts`, CRUD catálogo, Casos A/B/C); `internal_reference`; modelo y CRUD `Supplier`; diseño completo (sin implementar) de repuestos anclados a `BreakdownTicket`; desvío completo a H21 (Fases D/E/F/G); 3 fixes de producción fuera de hoja de ruta; preparación de acceso M365 | Sesión larga, 14 commits. **Desvío a H21 (al inicio):** Fases D (descartada — flota ya en app propia), E (`views_ivr.py`), F (`views_auth.py`) y G (limpieza final, `panel/views.py` de 4.033 a 115 líneas) completadas — detalle técnico completo y la incidencia de un re-export de `fleet.views` perdido en la extracción (y su fix) en `ENTERPRISEBOT_ATTACHED_MILESTONE_V21.md`. **H10 Paso 4:** nueva app `workorder_spare_parts` (bloques 1/4-3/4, ver Paso 4 arriba) — CRUD de catálogo con `internal_reference` estable frente a cambios de proveedor, endpoints HTMX de los 3 casos de consumo, modelo `Supplier` (reciclado interno = otro proveedor). El bloque 4/4 original (integrar el widget en `form_entry.html`/`confirm_entry.html` anclado a `entry_line_pk`) quedó **descartado a media sesión** al descubrir que la `WorkOrderEntryLine` no existe en BD durante la creación directa del parte (Vía A) — Miguel Ángel replanteó el anclaje a `BreakdownTicket` en su lugar (más natural: los tickets existen antes que cualquier parte, vía IVR/WhatsApp/panel). Se cerró un diseño completo de 12 puntos tras varias rondas de refinamiento (desambiguación con lista corta si hay >1 ticket candidato, `get_or_create` atómico con `select_for_update` sobre `MachineAsset` como mutex, ventana de 72h para ofrecer reapertura de un ticket cerrado por error, nuevo campo `tipo_tarea` con categorización libre para lo que no sea avería, reapertura por edición de la propia tarea en vez de acción administrativa aparte, cambio de comportamiento de `confirm_delivery_note()`) — **sin una sola línea de código todavía**, íntegro en la sección Paso 4-bis de este anexo para la siguiente sesión. **Fixes de producción fuera de la hoja de ruta de H10/H21** (diagnosticados vía `error.log`, no a ciegas): (1) `TypeError` en el export consolidado de partes (`date_key` mezclaba `datetime.date` y `str` en el `sort()`); (2) `IntegrityError` al insertar una línea de parte en medio de otras (`line_number` shift en bloque chocaba contra la constraint única bajo MySQL, corregido a shift descendente fila a fila); (3) `modal-backdrop` huérfano tras descargar Excel desde el modal de exportación (race entre `hide()` y `submit()`, corregido esperando `hidden.bs.modal`, reforzado con `getOrCreateInstance` y una limpieza defensiva tras persistir el síntoma en un segundo reporte). **Preparación M365 (sin código):** confirmado SharePoint (no OneDrive), permiso `Sites.Selected`, roles a pedir (Application Administrator + SharePoint Administrator, consentimiento final por alguien con Global/Privileged Role Administrator), y pendiente de resolver si hace falta IP fija (QuotaGuard Static, 19 $/mes) o si el administrador de Grúas Álvarez acepta autenticación por certificado en su lugar — pregunta pendiente de respuesta. Bug cruzado sin diagnosticar, ya mencionado en sesiones anteriores y ahora relevante para el punto 9 del diseño de tickets: "revisar/editar" en el listado de partes de operario no entra en modo edición real. |
| S007 | 2026-07-07 | H10 Paso 4-bis puntos 1-2/11 integrados en producción (bloques A y B); Paso 5 completo (almacén + limbo); Paso 6 completo (sidebar/permisos); corrección Catálogo/Almacén; 4 bugs de producción corregidos; código general `#CÓDIGO#` de albarán; limpieza de datos de prueba | Sesión muy larga, empezó con reconciliación de un cierre de S006 que no se había pulled a tiempo al arrancar (sin daño real, commit local erróneo descartado antes de pushear). **Paso 4-bis:** puntos 1-2 revisados en vivo (PAUSED cuenta como candidato abierto, confirmación obligatoria con 1+ candidatos, ya no hay enganche silencioso) e integrados de verdad en el formulario de parte -- bloque A (sustituye el desplegable `ticket_pk` de H17) y bloque B (confirmación de repuestos al guardar, ampliada en vivo a petición de Miguel Ángel para incluir también un checklist de repuestos pre-asignados directamente en el propio formulario, no solo en la pantalla posterior). Punto 12 (bis) implementado y **revertido** en la misma sesión: Miguel Ángel confirmó que generar el ticket ya al confirmar el albarán (antes de que exista ninguna avería real) crea riesgo de tickets huérfanos -- `confirm_delivery_note()` vuelve al planteamiento diferido de S001-S005. **Paso 5:** vista de almacén con limbo de pre-asignación integrado (código de color por antigüedad, acción Devolver a almacén). **Corrección mayor en vivo (Miguel Ángel, tras ver el resultado):** Catálogo (Administración) y Almacén (Mecánicos) se habían construido como la misma vista con dos etiquetas -- son dos entidades distintas (proveedor/precio vs. stock/limbo/ajuste de inventario por los propios mecánicos) y se separaron por completo, con nueva `SparePartStockAdjustView` para que los mecánicos ajusten stock sin pasar por el catálogo administrativo. **4 bugs de producción diagnosticados y corregidos, todos verificados empíricamente antes de tocar código:** (1) "Editar/Revisar" no entraba en modo edición real para ADMIN sobre partes de otros operarios (condición de consulta demasiado restrictiva); (2) SUPERVISOR recibía 403 en el mismo flujo (mixin correcto ya existía en el código, `WorkOrderFormAccessMixin`, pero nunca se había conectado); (3) `ImportError` real en producción (`ChatRoom`/`ChatMessage` eliminados en H17 pero `chat/services.py` seguía importándolos a nivel de módulo) -- verificado exhaustivamente que tres archivos completos (`chat/services.py`, `chat/views.py`, `chat/management/commands/init_chat_rooms.py`) llevaban huérfanos e inalcanzables desde H17, retirados a placeholders vacíos siguiendo el mismo patrón ya usado en `chat/tasks.py`; función de resolución de tickets movida a módulo propio `chat/ticket_resolution.py`; (4) repuestos pre-asignados solo a máquina (sin ticket) no aparecían en la pantalla de revisión posterior al guardado. **Fuera de H10:** nuevo campo `DeliveryNote.general_machine_code_raw` (anotación `#CÓDIGO#` general para todo el albarán, gap real detectado por Miguel Ángel); destinatario temporal de fotos de albarán cambiado a `nummenor@gmail.com`; comandos de gestión `delete_all_breakdown_tickets` y `delete_all_spare_parts_data` (dry-run por defecto) ejecutados con `--apply` para dejar la BD limpia antes de una prueba de campo que finalmente no se hizo (no había mecánicos en el taller). Cuatro migraciones aplicadas en el ciclo completo (pull→makemigrations→migrate→push del archivo de migración desde servidor→pull silencioso en workspace), todas confirmadas sin error. Pendiente sin resolver, señalado a Miguel Ángel: si `WORKSHOPBOSS` también necesita acceso completo a "Editar/Revisar" igual que `SUPERVISOR` (se dejó restringido a lo propio, sin confirmación explícita). Próxima sesión: Paso 7 (alta de repuestos por canibalización), confirmado por Miguel Ángel al cierre. |
