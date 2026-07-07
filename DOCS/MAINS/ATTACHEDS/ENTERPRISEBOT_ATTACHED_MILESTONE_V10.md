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

## 5. Hoja de Ruta para la Siguiente Sesión

### ESTADO AL CIERRE DE S007 (2026-07-07)

- **Paso 1 — COMPLETADO** (sin cambios desde S001).
- **Paso 2 — COMPLETADO** (sin cambios desde S003).
- **Paso 3 — COMPLETADO**, validado end-to-end en producción desde S004.
- **Paso 4 — COMPLETADO.** App `workorder_spare_parts` (CRUD de
  catálogo, `internal_reference`, modelo `Supplier`), endpoints HTMX
  de los 3 casos de consumo (S006), y en S007 la integración real en
  el formulario de parte (bloques A y B, ver Paso 4-bis abajo).
- **Paso 4-bis — puntos 1, 2 y 11 COMPLETADOS e INTEGRADOS EN
  PRODUCCIÓN (S007).** Diseño cerrado en S006 (12 puntos), de los
  cuales esta sesión implementó y conectó:
  - **Puntos 1-2 (resolución de ticket + mutex):**
    `chat/ticket_resolution.py` (módulo propio, ver más abajo) --
    `resolve_ticket_for_machine()` (solo lectura) y
    `get_or_create_ticket_for_machine()` (atómico,
    `select_for_update()` sobre `MachineAsset`). Revisado sobre la
    marcha a petición de Miguel Ángel: `PAUSED` cuenta como candidato
    abierto (no solo `OPEN`/`IN_PROGRESS`), y con 1+ candidatos
    **siempre** hay que confirmar con el mecánico (ya no hay enganche
    silencioso con un único candidato) -- acción unificada `CHOOSE`.
  - **Bloque A (integración en el formulario):** sustituye el
    desplegable manual `ticket_pk` de H17 por resolución automática al
    fijar la máquina de la tarea. Nuevo endpoint HTMX
    `TaskTicketResolutionView` (`workorder_spare_parts`), nuevo
    fragmento `_ticket_resolution.html`. **Bug real encontrado y
    corregido durante la propia sesión:** el "Tarea 1" de un parte
    nuevo desde cero se renderiza desde un fragmento aparte
    (`_schedule_fields_fragment.html`), no desde el bucle de
    `form_entry.html` -- había que añadir el bloque en los dos sitios.
  - **Bloque B (confirmación de repuestos al guardar):** nueva
    `WorkOrderEntryPartsReviewView` -- pantalla posterior al guardado
    que reutiliza el widget de consumo ya construido en S006 (Caso B),
    ampliada para cubrir también repuestos pre-asignados solo a
    máquina (sin ticket).
  - **Ampliación en directo, a petición de Miguel Ángel:** además de
    la pregunta del ticket, el mismo formulario de parte muestra ahora
    una tabla con checkbox por cada repuesto ya pre-asignado a esa
    máquina, para marcar cuáles se consumen de verdad en la tarea
    (`entrada_{idx}_consume_part_{pk}`, procesado al guardar vía
    `StockAssignmentService.consume_pre_assigned()`).
  - **Punto 12 (bis) — REVERTIDO deliberadamente.** Se implementó y
    luego se deshizo en la misma sesión: `confirm_delivery_note()`
    vuelve al planteamiento diferido de S001-S005 (pre-asignación
    directa a la máquina si no hay ticket, nunca crea uno nuevo al
    confirmar el albarán) -- Miguel Ángel confirmó que generar un
    ticket ya al recibir material (antes de que exista ninguna avería
    real) crea riesgo de tickets huérfanos.
  - **Puntos 3-10 (sin implementar todavía):** `tipo_tarea` con
    clasificación libre para lo que no sea avería; transición de
    estado completa al grabar/editar la tarea (el checkbox
    `ticket_closed` de H17 ya cubre el cierre, falta el matiz de
    reapertura); el bug cruzado de "revisar/editar" que bloqueaba la
    reapertura **ya se diagnosticó y se corrigió en esta sesión** (ver
    más abajo), así que el punto 9 ya no tiene nada por delante.
- **Paso 5 — COMPLETADO (S007).** Vista de almacén
  (`SparePartWarehouseListView`) con filtro por máquina/estado y limbo
  de pre-asignación integrado (código de color por antigüedad --
  verde &lt;2 semanas, azul-info 1 mes, naranja 3 meses, rojo 6+ meses;
  asunción declarada en el propio código: el anexo describe 4 colores
  para 3 umbrales explícitos, interpretado como que "rojo" cubre todo
  lo que pase de 3 meses, a confirmar si Miguel Ángel quería un cuarto
  umbral real), con acción "Devolver a almacén"
  (`SparePartReturnToWarehouseView`, transición literal de la sección
  3.2). `StockMovementCreateView` no se construyó como vista aparte --
  ya cubierto por el ajuste automático de `SparePartEntryUpdateView`.
  **Corrección importante en la misma sesión:** el Catálogo
  (Administración) y el Almacén (Mecánicos) se habían dejado como la
  misma vista con dos etiquetas -- Miguel Ángel señaló que son dos
  entidades distintas y se separaron por completo (ver "Corrección
  Catálogo/Almacén" más abajo).
- **Paso 6 (sidebar y permisos) — COMPLETADO**, resultado directo de
  la corrección Catálogo/Almacén de esta misma sesión.
- **Paso 7 — Alta de repuestos por canibalización. SIN EMPEZAR.**
  Siguiente paso natural para la próxima sesión -- modal de alta
  manual con `origin_type=SALVAGED`, selector de máquina donante y de
  parte de origen (opcional, búsqueda libre de partes recientes de esa
  máquina), destino igual que el resto del circuito (WAREHOUSE o
  PRE_ASSIGNED con máquina/ticket receptor), genera `StockMovement
  SALVAGE`. Sin disparo automático desde `form_entry.html` -- el parte
  de trabajo nunca crea `SparePartEntry` por canibalización
  automáticamente, solo documenta la tarea en texto libre (principio
  rector de separación, sección 3.6, sin cambios).
- **Paso 8 — Persistencia real en la nube M365. BLOQUEADO**, sin
  cambios desde S006 -- pendiente de que Miguel Ángel resuelva el
  acceso (SharePoint, permiso `Sites.Selected`) con el administrador
  de M365 de Grupo Álvarez.

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

### PENDIENTE SIN RESOLVER, SEÑALADO A MIGUEL ÁNGEL EN S007

- **`WORKSHOPBOSS` y el acceso "Editar/Revisar":** se dejó con el
  mismo comportamiento restrictivo que `WORKSHOP` (solo sus propios
  partes) al ampliar el acceso a `SUPERVISOR`, siguiendo literalmente
  el docstring ya existente de `WorkOrderFormAccessMixin` -- Miguel
  Ángel no lo confirmó explícitamente. Si un jefe de taller también
  necesita editar partes de otros operarios, ampliar
  `_resolve_editable_work_order()` igual que se hizo para
  `SUPERVISOR`.

### PRÓXIMA SESIÓN — ORDEN DE TRABAJO

1. **Paso 7 de H10** (alta de repuestos por canibalización) --
   siguiente paso natural del roadmap, confirmado por Miguel Ángel al
   cierre de S007.
2. Si hay tiempo/energía: puntos 3-10 del diseño de Paso 4-bis
   (`tipo_tarea`, transición de estado completa al grabar/editar la
   tarea) -- el bug que bloqueaba el punto 9 ya está resuelto.
3. Pendiente sin resolver de S007: confirmar el alcance de
   `WORKSHOPBOSS` en "Editar/Revisar" (ver arriba).
4. Paso 8 (M365) sigue bloqueado hasta que Miguel Ángel resuelva el
   acceso con el administrador de Grupo Álvarez -- no es una tarea de
   sesión de código, revisar solo si hay novedades por su parte.

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
