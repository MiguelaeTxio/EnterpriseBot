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

## 5. Hoja de Ruta para la Siguiente Sesion

### ESTADO AL CIERRE DE S003

- **Paso 1 — COMPLETADO** (sin cambios desde S001).
- **Paso 2 — COMPLETADO.** `GeminiVisionExtractionService` integrado en
  `DeliveryNoteUploadView`. Probado por Miguel Ángel con un albarán real
  de Grupo Álvarez en producción — la extracción funciona bien.
- **Paso 3 — puntos 1-3 COMPLETADOS, punto 4 PARCIAL.**
  `DeliveryNoteUploadView`, `DeliveryNoteDetailView` y
  `DeliveryNoteConfirmView` creadas y desplegadas (spare_parts/views.py,
  spare_parts/urls.py). Campo `machine_code_raw` añadido a
  `DeliveryNoteLine` (migración 0002). `resolve_line_assignment()` y
  `confirm_delivery_note()` en `spare_parts/services.py` implementan el
  circuito completo de la sección 3.1. Sidebar: sección "Operarios"
  renombrada a "Mecánicos", con nuevo ítem "Subir albarán". Captura por
  cámara integrada en `delivery_note_upload.html` (adaptada de
  `PAIRS/delivery_note_processor/camera_capture.js`). Punto 4 (test
  end-to-end): la extracción se ha probado con un albarán real y
  funciona, pero Miguel Ángel ha detectado que el modelo de datos actual
  no recoge dos cosas necesarias — ver TAREA INMEDIATA. No se ha llegado
  a probar la revisión ni la confirmación con ese albarán real.
- **Pasos 4 a 7 — sin iniciar** (sin cambios).

### TAREA INMEDIATA — Multiempresa del grupo + centro de gasto por línea (BLOQUEANTE del cierre del Paso 3)

Al probar con un albarán real ("Grúas Adolfo Álvarez, SL"), Miguel Ángel
ha detectado dos datos que el circuito actual NO recoge. Miguel Ángel
traerá la especificación exacta al inicio de la próxima sesión —
**NO implementar nada de este punto hasta recibirla**, para no construir
sobre una suposición equivocada de la estructura de datos existente.

1. **Empresa del grupo destinataria del albarán.** Grupo Álvarez no es
   una única empresa — el albarán de prueba iba dirigido a "Grúas Adolfo
   Álvarez, SL", una entre varias empresas del grupo. Antes de tocar
   nada, hacer un PVR completo de `ivr_config/models.py` (o donde
   corresponda) para verificar si esa estructura multiempresa ya existe
   en el sistema (¿es un desglose dentro de `Company`, o hay que
   modelarlo?) — no asumir, comprobar empíricamente. Después decidir
   junto con Miguel Ángel dónde y cómo capturar ese dato en `DeliveryNote`
   (posiblemente extraíble por Gemini Vision si la razón social aparece
   impresa en el propio albarán, a confirmar).
2. **Centro de gasto por línea de repuesto.** Miguel Ángel indica que en
   el albarán físico se anota, junto a cada línea de repuesto, el centro
   de gasto de destino — dato adicional a (o quizás relacionado con) el
   `machine_code_raw` ya capturado. Miguel Ángel necesita cotejar varios
   datos antes de dar la especificación exacta.

**Al inicio de la próxima sesión:** preguntar a Miguel Ángel por estos dos
datos antes de retomar cualquier otro punto del Paso 3. Una vez
incorporados, repetir la prueba de extremo a extremo completa (subida →
revisión → confirmación → verificación en admin) con el mismo albarán u
otro nuevo de Grupo Álvarez.

### Paso 4 — StockAssignmentService y circuito en parte de trabajo
- Implementar `StockAssignmentService.assign_to_work_order()` con
  los 3 casos del circuito (A, B, C) de la sección 3.5, más el
  listado automático de pre-asignados (3.3) al seleccionar máquina
  o ticket en `WorkOrderEntry`.
- Auto-relleno del parte desde el ticket de avería (centro de gasto,
  familia/tipo de avería) cuando existe ticket abierto, excepto
  variables propias del parte (horas, pausas de comida).
- Añadir selector de repuesto en `form_entry.html`, con sección
  separada para repuestos pre-asignados (listado automático,
  selección directa) y repuestos no pre-asignados (búsqueda manual,
  Caso A/C).
- Modal de registro de nuevo repuesto (Caso C) con selector
  contable/incontable y captura de stock inicial.
- Lógica de cierre de parte (3.4): transición PRE_ASSIGNED→CONSUMED,
  `consumed_at`, `StockMovement OUT`.

### Paso 5 — Vista de almacén y movimientos
- `SparePartListView`: listado de repuestos con filtros por máquina,
  almacén, status (WAREHOUSE/PRE_ASSIGNED/CONSUMED), nivel
  (LOW/EMPTY destacados visualmente).
- Vista específica del limbo (filtro `status=PRE_ASSIGNED`,
  ordenado por `pre_assigned_at` ascendente) con código de colores
  por antigüedad: verde (&lt;2 semanas), amarillo (1 mes), naranja
  (3 meses), rojo (6 meses+). Acción "Devolver a almacén" que
  ejecuta la transición descrita en 3.2 y genera
  `StockMovement RETURN_TO_WAREHOUSE`.
- `StockMovementCreateView`: ajuste manual de stock.

### Paso 6 — Sidebar y permisos
- Añadir sección Almacén/Repuestos al sidebar.
- Permisos: ADMIN/SUPERVISOR gestionan albaranes; WORKSHOP puede
  registrar repuestos desde el parte de trabajo.

### Paso 7 — Alta de repuestos por canibalización (reciclado interno)
- Vista o modal de alta manual de `SparePartEntry` con
  `origin_type=SALVAGED` desde `SparePartListView` (sección 3.6):
  selector de `origin_machine` (máquina donante), selector opcional
  de `origin_work_order_entry_line` (búsqueda de partes recientes de
  esa máquina, opcional/libre), y selección de destino igual que el
  resto del circuito (WAREHOUSE o PRE_ASSIGNED con
  máquina/ticket receptor).
- Genera `StockMovement SALVAGE` al confirmar el alta.
- Sin disparo automático desde `form_entry.html` — el parte de
  trabajo nunca crea `SparePartEntry` por canibalización
  automáticamente, solo documenta la tarea en texto libre. Ver
  principio rector de separación en 3.6.

---

## 6. Registro de Sesiones

| Sesion | Fecha | Pasos trabajados | Resumen |
|--------|-------|-----------------|---------|
| S001 | 2026-06-30 | Paso 1 completo, Paso 2 parcial | App `spare_parts` creada: modelos `DeliveryNote`/`DeliveryNoteLine`/`SparePartEntry`/`StockMovement` con limbo de pre-asignación (status WAREHOUSE/PRE_ASSIGNED/CONSUMED), procedencia dual (origin_type SUPPLIER/SALVAGED para canibalización interna), relación con `work_order_processor.SparePartLine` (FK `spare_part_entry` nueva). Migración cruzada aplicada, admin registrado, reload OK. `GeminiVisionExtractionService` construido con `gemini-3.5-flash` (no 2.5, deuda técnica documentada en doc-master-enterprisebot 4.1.1). App compartida `ai_services` creada por principio DRY — `work_order_processor.services` migrado al mismo helper. Desvío completo a H18 por incidencia crítica de regresión del planificador de ruta (autocompletado roto): diagnosticado y resuelto sustituyendo `PlaceAutocompleteElement` por implementación propia — ver anexo H18 S018 para el detalle técnico completo. Paso 2 de H10 queda pendiente de integrar `GeminiVisionExtractionService.extract()` en `DeliveryNoteUploadView` (Paso 3) y testar con albaranes reales. |
| S002 | 2026-07-02 | NOTA DE DESVÍO — sin trabajo directo en H10 | H10 se mantuvo EN PROGRESO durante toda la sesión sin recibir ningún avance directo. Sesión desviada por completo a H16 (motor de presupuestos: importación de tarifas por PDF, modo manual del wizard, control de acceso granular, mapa de ruta en desglose — ver anexo H16 S055) y a H18 (bug de peajes ida/vuelta y tramos AP-7, fechas pasadas en planificación de ruta, fix drag-and-drop del planificador — ver anexo H18 S019). Al cierre de sesión se ejecutó PCH: `eb-annex-router` mueve `← EN PROGRESO` de H10 a H07 (incidencia de pausa de comida en jornada partida, partes digitales). La hoja de ruta de H10 (Sección 5) queda intacta, con el Paso 3 pendiente exactamente como estaba, para cuando `eb-annex-router` vuelva a marcar H10 EN PROGRESO. |
| S003 | 2026-07-02 | Paso 2 completo, Paso 3 puntos 1-3 completos, punto 4 iniciado | Añadido campo `machine_code_raw` a `DeliveryNoteLine` (migración `0002_deliverynoteline_machine_code_raw`, aplicada OK). Añadidas a `spare_parts/services.py`: `resolve_line_assignment()` (detecta WAREHOUSE vía alias ALM/AL/ALMACEN/ALMACÉN/WAREHOUSE, o MACHINE reutilizando `_normalise_machine_code()`/`_resolve_machine_asset()` de `work_order_processor.services` por DRY) y `confirm_delivery_note()` (ejecuta el circuito completo de la sección 3.1: SparePartEntry WAREHOUSE con suma de stock, o PRE_ASSIGNED en el limbo con búsqueda de BreakdownTicket OPEN/IN_PROGRESS, y StockMovement IN en ambos casos). Creadas `DeliveryNoteUploadView`, `DeliveryNoteDetailView`, `DeliveryNoteConfirmView` (spare_parts/views.py, protegidas con `CompanyUserRequiredMixin`), `spare_parts/urls.py` (namespace `spare_parts`), y las plantillas `delivery_note_upload.html`/`delivery_note_detail.html` (extienden `panel/base.html`). Añadido include en `enterprise_core/urls.py` (`panel/spare-parts/`). Renombrada la sección del sidebar "Operarios" → "Mecánicos" (`panel/_nav_items.html`) y añadido el ítem "Subir albarán" (WORKSHOP/ADMIN). Reescrita `delivery_note_upload.html` con captura directa por cámara, adaptada del prototipo `PAIRS/delivery_note_processor/camera_capture.js` (getUserMedia + canvas.toBlob), pero inyectando el archivo capturado vía `DataTransfer` en el `<input>` existente y reutilizando el submit normal del formulario en vez del endpoint AJAX/JSON del original — cero cambios en la vista Python para esa parte. Todos los despliegues vía `com-install-files` y `put` directo, con reload 200 OK confirmado en cada bloque. Miguel Ángel ha probado la extracción con un albarán real de Grupo Álvarez ("Grúas Adolfo Álvarez, SL") en producción — la extracción Gemini Vision funciona bien — pero ha detectado dos carencias de modelo de datos (empresa del grupo destinataria del albarán, y centro de gasto por línea de repuesto anotado en el albarán físico) que impiden dar el punto 4 (test end-to-end) por completado. Ver Sección 5 para el detalle y el plan de la siguiente sesión. |
