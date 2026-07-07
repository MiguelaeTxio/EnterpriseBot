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

### ESTADO AL CIERRE DE S004

- **Paso 1 — COMPLETADO** (sin cambios desde S001).
- **Paso 2 — COMPLETADO** (sin cambios desde S003).
- **Paso 3 — COMPLETADO, incluido el punto 4.** La TAREA INMEDIATA
  que bloqueaba el punto 4 quedó resuelta en S004 con la
  especificación que trajo Miguel Ángel, implementada y **validada
  end-to-end en producción**:
  - **Empresa destinataria del albarán:** `DeliveryNote` gana
    `recipient_name`/`recipient_tax_id`/`recipient_company_code`.
    Gemini Vision extrae ahora también el bloque destinatario
    (distinto del proveedor). `resolve_recipient_company_code()`
    (`spare_parts/services.py`) resuelve por CIF contra las tres
    empresas confirmadas por Miguel Ángel: GRA=B29405040 (Grúas
    Adolfo Álvarez), TRA=B92493022 (Transgrual), GRG=B93261824
    (Asistencia y Grúas Granada) — reutilizando el mismo catálogo
    corto `company_code` que ya usa `fleet.MachineAsset`, sin tabla
    nueva. Campo libre (no choices): nuevas empresas del grupo se
    añaden al diccionario a medida que aparezcan.
  - **Centro de gasto general por línea:** `resolve_line_assignment()`
    gana un paso intermedio (`_resolve_company_cost_center`) que
    resuelve anotaciones de texto libre tipo "TALLER MECANICO" o
    "Almacén Huelva" contra los `MachineAsset` con prefijo `EMPRESA_`
    ya existentes en el catálogo (9 centros de gasto generales
    confirmados empíricamente por PVR en S004: almacén/taller ×
    dependencias/Huelva/logística/mecánico/elevación), comparación
    insensible a acentos/mayúsculas en ambos lados. El prompt de
    extracción reconoce la convención física de anotación entre
    almohadillas (`#TALLER MECANICO#`) definida por Miguel Ángel.
  - **VALIDACIÓN E2E — COMPLETADA.** Probado en producción con un
    albarán real (BA/2604254, LUIS MOLEÓN RECAMBIOS → GRUAS ADOLFO
    ALVAREZ, S.L., 3 líneas anotadas `#S06#`/`#V02#`/`#S02#`):
    destinatario resuelto automáticamente a `GRA` por CIF, las tres
    líneas resueltas correctamente a `assignment_type=MACHINE` contra
    los códigos de máquina S06/V02/S02, confirmado dato a dato contra
    la foto del albarán físico por Miguel Ángel. El registro de
    prueba (`DeliveryNote` id=2) se borró a petición de Miguel Ángel
    tras la validación — no queda en BD, era solo de prueba.
- **Pasos 4 a 7 — sin iniciar** (sin cambios).

### Envío por correo del albarán (S004) — pendiente de un paso externo

Implementado con la API nativa **Twilio Email**
(`https://comms.twilio.com/v1/Emails`, NO Twilio SendGrid clásico —
corregido a mitad de S004 tras verificación online, ver Registro de
Sesiones). Reutiliza `TWILIO_API_KEY_SID`/`TWILIO_API_KEY_SECRET` ya
existentes, sin secreto nuevo. Remitente y destinatario:
`administracion@gruasalvarez.com` (mismo buzón real, confirmado por
Miguel Ángel).

**Bloqueante restante — fuera del control del modelo:** Twilio exige
autenticación de dominio (DNS) para `gruasalvarez.com`. Miguel Ángel
no tiene acceso al DNS del dominio; al cierre de S004 ha delegado el
paso vía la función nativa de Twilio "Forward instructions to a
colleague" (Manual setup → 4 registros CNAME) a la persona que sí
gestiona el DNS. Pendiente de que esa persona complete los registros
(Twilio puede tardar hasta 48h en verificar). Ninguna acción de
código pendiente por parte del modelo — en cuanto el dominio quede
verificado, el envío debería funcionar sin más despliegues.

### Trabajo realizado en S004 fuera de la hoja de ruta de H10

Cinco incidencias de mantenimiento cross-cutting, sin anexo de hito
propio, resueltas en el mismo bloque de sesión (H10 se mantuvo EN
PROGRESO todo el tiempo, sin PCH):

1. **Bug de alta por WhatsApp:** `OnboardingService._create_user()`
   (`whatsapp/services.py`) ignoraba `Section.default_role` y
   asignaba el rol mediante una heurística de palabras clave sobre el
   nombre de sección (`_is_elevation_section`), cayendo en `DRIVER`
   para cualquier sección sin esas palabras (p.ej. "Taller Mecánico").
   Corregido: `role = section.default_role`. Código huérfano
   eliminado.
2. **Sección "Guardas" dada de alta** (`ivr_config.Section`, id=15,
   `default_role=WORKSHOP`, sin flujo IVR: `ivr_transfer_enabled=False`,
   `ivr_breakdown_enabled=False`) vía Comando S directo en BD de
   producción. Se detectó que la señal `auto_manage_section_call_flow`
   (`ivr_config/signals.py`) genera un `CallFlow` para toda `Section`
   nueva sin excepción; se desactivó (`is_active=False`, no se borró —
   borrar habría causado su regeneración automática en la siguiente
   edición de la sección, según la propia lógica de la señal) para
   dejarla efectivamente fuera del IVR.
3. **Botón "Guardar tareas" del formulario de partes (H07) — tres
   bugs encadenados, todos confirmados empíricamente (dos de ellos
   verificando directamente en BD, no solo leyendo código):**
   - `btn-save-blocks` (`panel/templates/panel/operator/form_entry.html`)
     no tenía NINGÚN listener de clic en todo el proyecto — botón
     muerto. Fix: nuevo listener en `form_entry_modal.js` que fija
     `form-action-input=save_blocks` y llama a `form.submit()` (mismo
     patrón que "Cerrar parte").
   - **Trampa de proceso propia:** el primer intento de este fix se
     aplicó a `static/panel/js/form_entry_modal.js`, que resultó ser
     literalmente `STATIC_ROOT` (`settings.py`), no la fuente — el
     siguiente `collectstatic --clear` lo borró sin avisar. La fuente
     real es `panel/static/panel/js/form_entry_modal.js`
     (`AppDirectoriesFinder`, único finder activo — `STATICFILES_DIRS`
     no está definido). **Nota para toda sesión futura: cualquier
     estático del app `panel` se edita SIEMPRE en
     `panel/static/panel/js|css/...`, nunca en `static/panel/...`.**
   - `WorkOrderEntryFormView.post()` (`panel/views_operator.py`) tenía
     dos gates de confirmación (`save_confirmed`, `meter_warnings`) y
     un gate de cobertura de jornada (8h mínimas) sin la excepción
     `and _form_action != "save_blocks"` que sí tiene correctamente
     `WorkOrderEntryConfirmView` (vista hermana, mismo patrón
     duplicado entre ambas). Efecto: cualquier guardado parcial
     (jornada sin completar) se re-renderizaba sin persistir nada en
     BD, sin mostrar ningún error visible — parecía funcionar porque
     los datos seguían en pantalla. Confirmado con consulta directa a
     BD (cero `WorkOrder IN_PROGRESS`) antes y después de cada fix.
   - **Confirmado en real por Miguel Ángel:** guardado parcial
     persiste, "Mis partes" lo muestra "En curso", y "Nuevo parte"
     recupera el parte pendiente para seguir editándolo.

### Para la próxima sesión — nuevo tema, sin diagnosticar todavía

Miguel Ángel ha detectado al cierre de S004 que **las familias y
tipos de avería aparecen en inglés en el laboratorio de análisis**
(sección Analítica), usando los identificadores internos en vez de
su traducción al castellano — la interfaz debe estar siempre en
castellano. Miguel Ángel indica que podría no ser el único lugar
donde ocurra. Sin investigar en S004 — empezar la próxima sesión
haciendo un PVR completo (grep de los identificadores de
familia/tipo de avería en inglés, plantillas y vistas que los
consuman) antes de proponer ningún fix, en vez de asumir que es un
único punto aislado.

### Próxima sesión — orden de trabajo (actualizado al cierre de S005)

Los tres puntos que quedaron pendientes al cierre de S004 se resolvieron
en S005:
1. ~~Familias/tipos de avería en inglés~~ — **RESUELTO S005.** Bug real
   encontrado en `chat/breakdown_ticket_detail.html`
   (`BreakdownTicket.fault_category` sin `choices=`, a diferencia de
   `WorkOrderEntryLine`) — corregido resolviendo el label en la vista.
   `admin_history.html` se investigó y **no tenía el bug** (ya
   traducido correctamente vía `_dominant_fault_category`).
2. ~~Confirmar dominio Twilio~~ — **RESUELTO S005**, con cambio de
   planteamiento: Miguel Ángel usó su propio dominio ya autenticado
   (`campustudionline.com`) en vez de esperar a `gruasalvarez.com`
   (seguía bloqueado). Envío real validado E2E. Ver Paso 8 (arriba)
   para el bloqueante nuevo detectado (cuarentena de Microsoft 365
   Defender) y la solución puente temporal.
3. **Paso 4 de H10 — backend completado en S005, UI pendiente.** Ver
   detalle actualizado abajo.

### Paso 4 — StockAssignmentService y circuito en parte de trabajo

**Backend — COMPLETADO en S005.** `StockAssignmentService` en
`spare_parts/services.py`: `list_pre_assigned()` (sección 3.3),
`search_warehouse()` (paso 1 de 3.5), y los 3 casos de consumo —
`consume_from_warehouse()` (Caso A), `consume_pre_assigned()` (Caso
B), `register_new_and_consume()` (Caso C) — con materialización
compartida (`_materialize_consumption()`, sección 3.4) hacia
`SparePartLine` (FK `spare_part_entry` ya existía y ya migrada,
`work_order_processor/migrations/0027_...`) + `StockMovement OUT`.

**Bloques 1/4, 2/4 y 3/4 — COMPLETADOS en S006.** Nueva app Django
independiente `workorder_spare_parts` (confirmado por Miguel Ángel:
modularización real, no un archivo más dentro de `panel`):

- **Bloque 1/4:** CRUD del catálogo `SparePartEntry` fuera del
  circuito de albaranes (condición sine qua non). Lectura para
  ADMIN/SUPERVISOR/WORKSHOP/WORKSHOPBOSS (`CatalogReadAccessMixin`,
  local a `workorder_spare_parts/views.py`), edición solo ADMIN/
  SUPERVISOR (`SupervisorAccessMixin`).
- **Bloque 2/4:** endpoints HTMX del Caso A (`SparePartWarehouseSearchView`,
  `SparePartConsumeFromWarehouseView`) — `machine`/`breakdown_ticket`
  resueltos siempre desde la `WorkOrderEntryLine` real, nunca desde el
  cliente.
- **Bloque 3/4:** endpoints HTMX de los Casos B (`SparePartPreAssignedListView`,
  `SparePartConsumePreAssignedView`) y C (`SparePartRegisterNewAndConsumeView`).
  Widget compartido `_consumption_widget.html` con los 3 casos
  integrados (Caso B autocargado, Caso A con buscador, Caso C bajo
  desplegable) — sigue siendo el mismo include pensado para
  `WorkOrderEntryFormView`/`WorkOrderEntryConfirmView`, arquitectura
  confirmada por Miguel Ángel: vistas separadas con la lógica, una
  única plantilla compartida para la presentación.

Estos tres bloques **siguen siendo válidos tal cual** bajo el nuevo
diseño de anclaje a ticket (ver más abajo) — los endpoints y el widget
no cambian, lo que cambia es **cuándo y contra qué se les permite
actuar** (ver Paso 4-bis).

**Referencia interna estable (S006, aditivo, fuera del alcance
original del Paso 4 pero directamente relacionado):** confirmado por
Miguel Ángel — la referencia de catálogo debe ser propia de la
empresa, nunca la del proveedor (que puede cambiar si se cambia de
proveedor para la misma pieza física). `SparePartEntry.internal_reference`
(nuevo campo, formato `REP-000001`, generado por
`generate_internal_reference()`) es ahora el identificador principal
en catálogo, búsqueda de almacén y widget de consumo. El campo
`reference` existente queda como "referencia proveedor", informativo,
sin tocar. **Incidencia señalada, sin resolver:** `confirm_delivery_note()`
sigue emparejando líneas WAREHOUSE con un `SparePartEntry` existente
por `reference` (del proveedor) — si se cambia de proveedor para la
misma pieza física, seguiría creando una entrada de catálogo duplicada
en vez de sumar stock a la existente. Pendiente de decidir: matching
manual asistido al confirmar el albarán, o fuera de alcance por ahora.

**Modelo `Supplier` (S006, aditivo):** confirmado por Miguel Ángel —
el reciclado interno se modela como otro `Supplier`
(`supplier_type=SALVAGE`), no como un mecanismo aparte; la
trazabilidad de un repuesto (proveedor externo vs. reciclado, CIF...)
la da el `Supplier` al que referencia, no un flag `origin_type`
aparte. CRUD completo (`spare_parts/views.py`: List/Create/Update/
Deactivate/Reactivate/Delete guardado). `SparePartEntry.supplier` es
un FK **nullable, aditivo** — `supplier_name`/`supplier_tax_id`/
`supplier_address` (texto libre) siguen intactos. **Pendiente, sin
resolver:** conectar `confirm_delivery_note()` y el alta por
canibalización para que resuelvan/creen un `Supplier` real en vez de
escribir texto libre — ambos son flujos ya validados en producción
(S001-S005) y falta decidir la estrategia de resolución (¿por CIF
exacto? ¿auto-creación si no existe?).

### Paso 4-bis — PIVOTE DE DISEÑO (S006): repuestos anclados al ticket de avería, no a la línea del parte

**Este paso sustituye por completo la decisión de UI que quedaba
pendiente arriba ("¿archivo aparte o app independiente?", ya resuelta
como app independiente) y el bloque 4/4 original ("meter el widget en
`form_entry.html`/`confirm_entry.html` anclado a `entry_line_pk`").
Ese bloque 4/4 tal como estaba planteado queda OBSOLETO — no
retomarlo, se sustituye por lo de abajo.**

**Hallazgo que motivó el pivote:** en `WorkOrderEntryFormView` (Vía A,
creación directa), `SparePartLine.objects.create()` se ejecuta en el
mismo POST que crea `WorkOrder`→`WorkOrderEntry`→`WorkOrderEntryLine`.
Es decir, **la `WorkOrderEntryLine` no existe en BD mientras el
mecánico rellena el formulario** — se crea todo junto al enviar. Los
endpoints HTMX de los bloques 2/4 y 3/4 necesitan un `entry_line_pk`
real ya guardado, así que no pueden funcionar durante la creación
directa tal como estaba planteado.

**Decisión de Miguel Ángel:** los repuestos no se anclan a la línea
del parte — se anclan al **`BreakdownTicket`**, que existe de forma
independiente (creado por IVR, WhatsApp o directamente desde el
panel) **antes** de que exista ningún parte. Regla de negocio:
**no se pueden añadir repuestos sin ticket asociado a la tarea** (un
parte sí puede no llevar ningún repuesto, eso no cambia). Si al hacer
la tarea el centro de gasto no tiene ticket, el sistema genera uno
sobre la marcha — el ticket nunca debe "robar tiempo" al operario, se
resuelve solo salvo que haga falta desambiguar (ver más abajo).

**Diseño cerrado en S006 (discusión larga, 10 puntos + 6 refinamientos
adicionales — dejar registrado íntegro porque es el punto de partida
obligado de la siguiente sesión):**

1. **Resolución de ticket por centro de gasto** (compartida entre "al
   hacer el parte" y "al confirmar un albarán" — misma función, no dos
   implementaciones):
   - Filtrar solo tickets `OPEN`/`IN_PROGRESS`.
   - 0 candidatos abiertos → mirar si hay alguno **cerrado en las
     últimas 72 horas** para ese mismo CdG (ventana elegida para
     cubrir el caso viernes→lunes de fin de semana/festivo). Si lo
     hay, preguntar en texto plano al mecánico: *"Hay un ticket para
     esta máquina cerrado hace [X] — ¿es la misma avería?"* Sí →
     se reabre (ver punto 7). No → se genera uno nuevo.
   - 0 candidatos abiertos y ninguno cerrado en 72h → se pregenera uno
     nuevo directamente, sin preguntar nada.
   - 1 candidato abierto → se engancha solo, sin preguntar.
   - Más de 1 candidato abierto → lista corta al mecánico para que
     elija (un toque, no un formulario) — nunca dejar que Gemini
     adivine cuál es, mezclaría dos averías reales en una.
2. Todo el paso 1 dentro de un `get_or_create` atómico con
   `select_for_update()` sobre la fila de `MachineAsset` (mutex, ya
   que el ticket todavía no existe cuando se resuelve) — cubre la
   vía parte y la vía albarán como el mismo mecanismo compartido, sin
   condiciones de carrera, y cubre el caso de "ayuda" (dos operarios,
   mismo ticket, cada uno su propio parte).
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
   de edición sobre esa tarea (la vista única de edición/creación
   pendiente, ver bug cruzado abajo) la edita, destoca la casilla, y
   el ticket vuelve a `IN_PROGRESS` como consecuencia de esa edición —
   sin rol especial, sin motivo obligatorio aparte del rastro
   automático (quién editó, cuándo, qué tarea disparó la reapertura).
   Distinto del punto 1 (reapertura tras aviso de "¿es la misma
   avería?", que sí es una decisión nueva del mecánico sobre una tarea
   nueva).
10. **Trabajo nuevo sobre un ticket ya `CLOSED` fuera de la ventana de
    72h** → siempre ticket nuevo, nunca se reutiliza el cerrado.
11. Todo en una única transacción atómica por tarea — si el resto del
    parte falla validación después de resolver/crear el ticket, no
    debe quedar un ticket huérfano sin tarea asociada.
12. `confirm_delivery_note()` cambia de comportamiento: la rama actual
    "línea MACHINE sin ticket abierto → se asigna directo a la
    máquina, sin ticket" **desaparece por completo** — toda línea
    MACHINE pasa por la misma resolución `get_or_create` compartida
    del punto 1/2. Es un cambio de comportamiento sobre un flujo ya
    validado en producción (S001-S005), no una funcionalidad nueva en
    paralelo.

**Bug cruzado, todavía sin diagnosticar (mencionado por Miguel Ángel
en S006, relevante ahora porque el punto 9 depende de él):** en el
listado de partes de operario, "revisar/editar" no entra en modo
edición real — devuelve a la vista tal cual. Confirmado por Miguel
Ángel: quiere una única vista de edición/creación (el mismo formulario
de los partes digitales) para ADMIN/SUPERVISOR/WORKSHOP, nunca dos
vistas divergentes. Sin diagnosticar todavía — necesario antes o
durante la implementación del punto 9 de arriba, porque el mecanismo
de reapertura por edición depende de que exista una vista de edición
real.

**No bloquea nada más de H10** — es un bloque grande pero
independiente del resto de pasos.

### Nota cruzada — Hito 21 (split de panel/views.py)

**COMPLETADO en S006 vía desvío de sesión** — Fases D (descartada:
la flota ya vivía en su propia app `fleet/`), E (`views_ivr.py`), F
(`views_auth.py`) y G (limpieza final, `panel/views.py` reducido a
115 líneas de solo re-exports) completadas. Detalle técnico completo,
incidencia de re-export de `fleet.views` perdido y su fix: ver
`ENTERPRISEBOT_ATTACHED_MILESTONE_V21.md`. H21 queda pendiente solo de
verificación E2E real en producción (fuera del alcance del modelo).

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

### Paso 8 — Persistencia real en la nube M365 (sustituye el correo temporal)

**Confirmado por Miguel Ángel (2026-07-06) — principio arquitectónico
de obligado cumplimiento, no solo para este hito:**

**PythonAnywhere NUNCA es almacén permanente de fotografías.** El
servidor solo las retiene de forma **temporal**, mientras dura el
procesamiento (llamada a Gemini Vision para extracción de datos), y se
borran automáticamente en cuanto se persisten en su destino real — tal
como ya hace `send_delivery_note_photo_email` con el archivo del
albarán tras el envío confirmado (202/DELIVERED). Esto evita que el
almacenamiento en disco de PythonAnywhere crezca sin límite.

**El almacén permanente real es la nube Microsoft 365 (SharePoint/
OneDrive) de Grupo Álvarez.** En cuanto se resuelva el acceso (reunión
prevista esta tarde con el responsable de M365 de Grupo Álvarez), el
paso de envío por correo (actual solución puente, con destinatario
temporal `nummenor@proton.me` mientras dura la cuarentena de Microsoft
365 Defender sobre el remitente Twilio — ver `spare_parts/tasks.py`)
se sustituye por persistencia directa en la carpeta M365 que
corresponda, vía Microsoft Graph API (registro de aplicación en Azure
AD necesario — a diferencia del caso de H15, aquí Django corre en
PythonAnywhere, no en un PC con OneDrive sincronizado localmente, así
que Graph API no es evitable como sí lo fue en H15).

**Decisiones de arquitectura de acceso tomadas en S006 (fuera de
código, preparación de la reunión con el administrador de M365 de
Grupo Álvarez):**
- Confirmado: es **SharePoint** (bibliotecas de documentos
  estructuradas por máquina/empleado — Flota y Chóferes), no OneDrive
  personal.
- Permiso a solicitar: **`Sites.Selected`** (Microsoft Graph,
  Application permission) — acota la app a un único sitio, nunca
  `Sites.ReadWrite.All` sobre todo el tenant.
- Roles a pedir para Miguel Ángel en el tenant de Grúas Álvarez:
  **Application Administrator** (registro de la app) + **SharePoint
  Administrator** (crear el sitio/bibliotecas). El consentimiento
  final de `Sites.Selected` requiere **Global Administrator o
  Privileged Role Administrator** — no lo puede dar Application
  Administrator por sí solo (verificado en documentación de Microsoft,
  2026); pedir que alguien con ese rol lo conceda puntualmente en la
  propia reunión, sin que se lo den a Miguel Ángel de forma permanente.
- **Pendiente sin resolver al cierre de S006:** el administrador de
  M365 preguntó desde qué IP se conectaría la app. PythonAnywhere
  **no tiene IP de salida fija por defecto** (verificado en su propia
  documentación) — la opción es contratar **QuotaGuard Static**
  (proxy de IP fija de salida, desde 19 $/mes) y dársela, o pedirle a
  él si puede evitar la restricción por IP autenticando con
  **certificado** en vez de Client Secret (pregunta que Miguel Ángel
  iba a plantear literalmente así: *"¿Podemos autenticar con
  certificado en vez de restricción por IP?"*). Respuesta de esa
  pregunta pendiente para la siguiente sesión — determina si hace
  falta contratar QuotaGuard Static o no.
- Ngrok **no sirve** para esto (resuelve tráfico de entrada, exponer
  un servidor local; el problema aquí es de salida — dar IP fija a
  las llamadas de EnterpriseBot hacia Microsoft Graph). Anotado para
  no reabrir la misma pregunta.

**En base de datos nunca se guarda la foto — solo la referencia.**
`DeliveryNote` (y cualquier modelo futuro con fotos, ver Pendiente
cruzado abajo) debe tener un campo tipo `cloud_storage_path`
(`CharField`/`URLField`, nombre exacto a decidir en la sesión de
implementación) que guarde la ruta/ID del archivo en M365, para
recuperarlo bajo demanda vía API — nunca el binario en BD ni en disco
de PythonAnywhere de forma permanente.

**Pendiente de implementación** (bloqueado hasta acceso M365):
- Nuevo campo en `DeliveryNote` para la referencia de ruta en la nube.
- Servicio de subida a M365 (Graph API) que sustituye
  `send_delivery_note_photo_email` como paso final del circuito de
  confirmación (o convive con él, a decidir).
- Migración correspondiente (`makemigrations`/`migrate`, flujo NFS
  completo ya establecido en `com-migrations`).

**Pendiente cruzado — Partes de Trabajo (fuera del alcance directo de
H10, anotado aquí porque comparte la misma decisión arquitectónica):**
Miguel Ángel ha identificado una necesidad nueva, no cubierta por
ningún hito existente: permitir que el operario adjunte fotografías a
una `WorkOrderEntryLine` concreta (ejemplo real: foto del cableado de
un motor eléctrico antes de desmontarlo, para referencia futura), y
que esas fotos sean recuperables después desde el historial de partes
del propio operario. Mismo principio: nunca persistir en
PythonAnywhere, subir a M365 vía Graph API, guardar solo la
referencia en BD. Requiere su propio campo/modelo nuevo en
`work_order_processor` (a diseñar) y su propia migración. **No se
implementa en H10** — queda anotado aquí para no perderlo, a la espera
de decidir en qué hito se aborda (posible Caso C de
`nfs-enterprisebot-pch`: hito nuevo, o ampliación de H7/H8 si Miguel
Ángel prefiere agruparlo con los partes digitales existentes).

---



| Sesion | Fecha | Pasos trabajados | Resumen |
|--------|-------|-----------------|---------|
| S001 | 2026-06-30 | Paso 1 completo, Paso 2 parcial | App `spare_parts` creada: modelos `DeliveryNote`/`DeliveryNoteLine`/`SparePartEntry`/`StockMovement` con limbo de pre-asignación (status WAREHOUSE/PRE_ASSIGNED/CONSUMED), procedencia dual (origin_type SUPPLIER/SALVAGED para canibalización interna), relación con `work_order_processor.SparePartLine` (FK `spare_part_entry` nueva). Migración cruzada aplicada, admin registrado, reload OK. `GeminiVisionExtractionService` construido con `gemini-3.5-flash` (no 2.5, deuda técnica documentada en doc-master-enterprisebot 4.1.1). App compartida `ai_services` creada por principio DRY — `work_order_processor.services` migrado al mismo helper. Desvío completo a H18 por incidencia crítica de regresión del planificador de ruta (autocompletado roto): diagnosticado y resuelto sustituyendo `PlaceAutocompleteElement` por implementación propia — ver anexo H18 S018 para el detalle técnico completo. Paso 2 de H10 queda pendiente de integrar `GeminiVisionExtractionService.extract()` en `DeliveryNoteUploadView` (Paso 3) y testar con albaranes reales. |
| S002 | 2026-07-02 | NOTA DE DESVÍO — sin trabajo directo en H10 | H10 se mantuvo EN PROGRESO durante toda la sesión sin recibir ningún avance directo. Sesión desviada por completo a H16 (motor de presupuestos: importación de tarifas por PDF, modo manual del wizard, control de acceso granular, mapa de ruta en desglose — ver anexo H16 S055) y a H18 (bug de peajes ida/vuelta y tramos AP-7, fechas pasadas en planificación de ruta, fix drag-and-drop del planificador — ver anexo H18 S019). Al cierre de sesión se ejecutó PCH: `eb-annex-router` mueve `← EN PROGRESO` de H10 a H07 (incidencia de pausa de comida en jornada partida, partes digitales). La hoja de ruta de H10 (Sección 5) queda intacta, con el Paso 3 pendiente exactamente como estaba, para cuando `eb-annex-router` vuelva a marcar H10 EN PROGRESO. |
| S003 | 2026-07-02 | Paso 2 completo, Paso 3 puntos 1-3 completos, punto 4 iniciado | Añadido campo `machine_code_raw` a `DeliveryNoteLine` (migración `0002_deliverynoteline_machine_code_raw`, aplicada OK). Añadidas a `spare_parts/services.py`: `resolve_line_assignment()` (detecta WAREHOUSE vía alias ALM/AL/ALMACEN/ALMACÉN/WAREHOUSE, o MACHINE reutilizando `_normalise_machine_code()`/`_resolve_machine_asset()` de `work_order_processor.services` por DRY) y `confirm_delivery_note()` (ejecuta el circuito completo de la sección 3.1: SparePartEntry WAREHOUSE con suma de stock, o PRE_ASSIGNED en el limbo con búsqueda de BreakdownTicket OPEN/IN_PROGRESS, y StockMovement IN en ambos casos). Creadas `DeliveryNoteUploadView`, `DeliveryNoteDetailView`, `DeliveryNoteConfirmView` (spare_parts/views.py, protegidas con `CompanyUserRequiredMixin`), `spare_parts/urls.py` (namespace `spare_parts`), y las plantillas `delivery_note_upload.html`/`delivery_note_detail.html` (extienden `panel/base.html`). Añadido include en `enterprise_core/urls.py` (`panel/spare-parts/`). Renombrada la sección del sidebar "Operarios" → "Mecánicos" (`panel/_nav_items.html`) y añadido el ítem "Subir albarán" (WORKSHOP/ADMIN). Reescrita `delivery_note_upload.html` con captura directa por cámara, adaptada del prototipo `PAIRS/delivery_note_processor/camera_capture.js` (getUserMedia + canvas.toBlob), pero inyectando el archivo capturado vía `DataTransfer` en el `<input>` existente y reutilizando el submit normal del formulario en vez del endpoint AJAX/JSON del original — cero cambios en la vista Python para esa parte. Todos los despliegues vía `com-install-files` y `put` directo, con reload 200 OK confirmado en cada bloque. Miguel Ángel ha probado la extracción con un albarán real de Grupo Álvarez ("Grúas Adolfo Álvarez, SL") en producción — la extracción Gemini Vision funciona bien — pero ha detectado dos carencias de modelo de datos (empresa del grupo destinataria del albarán, y centro de gasto por línea de repuesto anotado en el albarán físico) que impiden dar el punto 4 (test end-to-end) por completado. Ver Sección 5 para el detalle y el plan de la siguiente sesión. |
| S004 | 2026-07-03 | H10 Paso 3 completado y validado E2E; envío por correo del albarán (pendiente de autenticación de dominio externa); tres fixes encadenados en H07 (botón "Guardar tareas"); fix bug alta WhatsApp; alta sección Guardas | Primera sesión del flujo directo contra GitHub (`nfs-enterprisebot-*`), con token de sesión. **H10:** Miguel Ángel trajo la especificación de los dos datos bloqueantes del Paso 3 punto 4 — empresa destinataria por CIF (GRA/TRA/GRG) y centro de gasto general por línea vía convención de almohadillas contra los 9 `MachineAsset` `EMPRESA_*`. Implementado en `spare_parts/{models,services,views}.py` y `delivery_note_detail.html`, con migración `0003`. Validado end-to-end en producción con un albarán real (BA/2604254): destinatario resuelto a GRA, tres líneas resueltas a S06/V02/S02, confirmado dato a dato por Miguel Ángel contra la foto física; registro de prueba borrado a petición suya tras la validación. **Envío por correo (S004, nuevo):** `spare_parts/tasks.py`, tarea Celery que adjunta el archivo y lo borra del servidor tras confirmar. Primer intento con `sendgrid-python` revertido tras verificación online y captura de Miguel Ángel: el producto correcto es la API nativa **Twilio Email** (`comms.twilio.com/v1/Emails`), reutiliza `TWILIO_API_KEY_SID`/`SECRET` ya existentes. Bloqueado al cierre por autenticación de dominio DNS de `gruasalvarez.com`, que Miguel Ángel no gestiona — delegado a un tercero vía "Forward instructions to a colleague" de Twilio (Manual setup), sin acción de código pendiente. **Fuera de la hoja de ruta de H10:** (1) bug de alta por WhatsApp — `OnboardingService._create_user()` ignoraba `Section.default_role`, corregido; (2) sección `Guardas` dada de alta (`id=15`, `default_role=WORKSHOP`, sin IVR), con desactivación del `CallFlow` auto-generado por la señal `auto_manage_section_call_flow`; (3) H07, botón "Guardar tareas" del formulario de partes — tres bugs encadenados confirmados empíricamente, dos de ellos verificando directamente en BD: botón sin listener de clic (nunca llegaba al servidor); fix aplicado por error a `static/panel/js/...` (que es `STATIC_ROOT`, no la fuente) en vez de `panel/static/panel/js/...` (la fuente real vía `AppDirectoriesFinder`); y dos gates de confirmación (`save_confirmed`, `meter_warnings`) más el gate de 8h de jornada en `WorkOrderEntryFormView.post()` sin la excepción `form_action != "save_blocks"` que sí tenía correctamente la vista hermana `WorkOrderEntryConfirmView` — bloqueaban en silencio (sin error visible) todo guardado parcial. Confirmado en real por Miguel Ángel: persiste, aparece "En curso" en Mis partes, y se recupera al pulsar "Nuevo parte". Ocho commits de código + un commit de cierre de documentación pusheados a GitHub. Nuevo tema para la próxima sesión, sin diagnosticar: familias/tipos de avería en inglés en el laboratorio de análisis (y posiblemente en más sitios). |
| S005 | ¿? | Backend de `StockAssignmentService` completo (Paso 4); fix familias/tipos de avería a español; dominio Twilio resuelto | **Fila reparada a posteriori en S006, sin fecha ni detalle de commits recuperable** — esta sesión ocurrió (confirmado por Miguel Ángel al arrancar S006: family/subcategoría de avería en castellano y dominio Twilio resueltos, ambos vistos en producción) pero nunca se registró aquí en su momento. No se reconstruye el detalle de commits por no tener acceso a ese rango exacto de forma fiable — se deja esta fila mínima para no romper la numeración correlativa de sesiones. |
| S006 | 2026-07-07 | H10 Paso 4 bloques 1/4-3/4 completados (app `workorder_spare_parts`, CRUD catálogo, Casos A/B/C); `internal_reference`; modelo y CRUD `Supplier`; diseño completo (sin implementar) de repuestos anclados a `BreakdownTicket`; desvío completo a H21 (Fases D/E/F/G); 3 fixes de producción fuera de hoja de ruta; preparación de acceso M365 | Sesión larga, 14 commits. **Desvío a H21 (al inicio):** Fases D (descartada — flota ya en app propia), E (`views_ivr.py`), F (`views_auth.py`) y G (limpieza final, `panel/views.py` de 4.033 a 115 líneas) completadas — detalle técnico completo y la incidencia de un re-export de `fleet.views` perdido en la extracción (y su fix) en `ENTERPRISEBOT_ATTACHED_MILESTONE_V21.md`. **H10 Paso 4:** nueva app `workorder_spare_parts` (bloques 1/4-3/4, ver Paso 4 arriba) — CRUD de catálogo con `internal_reference` estable frente a cambios de proveedor, endpoints HTMX de los 3 casos de consumo, modelo `Supplier` (reciclado interno = otro proveedor). El bloque 4/4 original (integrar el widget en `form_entry.html`/`confirm_entry.html` anclado a `entry_line_pk`) quedó **descartado a media sesión** al descubrir que la `WorkOrderEntryLine` no existe en BD durante la creación directa del parte (Vía A) — Miguel Ángel replanteó el anclaje a `BreakdownTicket` en su lugar (más natural: los tickets existen antes que cualquier parte, vía IVR/WhatsApp/panel). Se cerró un diseño completo de 12 puntos tras varias rondas de refinamiento (desambiguación con lista corta si hay >1 ticket candidato, `get_or_create` atómico con `select_for_update` sobre `MachineAsset` como mutex, ventana de 72h para ofrecer reapertura de un ticket cerrado por error, nuevo campo `tipo_tarea` con categorización libre para lo que no sea avería, reapertura por edición de la propia tarea en vez de acción administrativa aparte, cambio de comportamiento de `confirm_delivery_note()`) — **sin una sola línea de código todavía**, íntegro en la sección Paso 4-bis de este anexo para la siguiente sesión. **Fixes de producción fuera de la hoja de ruta de H10/H21** (diagnosticados vía `error.log`, no a ciegas): (1) `TypeError` en el export consolidado de partes (`date_key` mezclaba `datetime.date` y `str` en el `sort()`); (2) `IntegrityError` al insertar una línea de parte en medio de otras (`line_number` shift en bloque chocaba contra la constraint única bajo MySQL, corregido a shift descendente fila a fila); (3) `modal-backdrop` huérfano tras descargar Excel desde el modal de exportación (race entre `hide()` y `submit()`, corregido esperando `hidden.bs.modal`, reforzado con `getOrCreateInstance` y una limpieza defensiva tras persistir el síntoma en un segundo reporte). **Preparación M365 (sin código):** confirmado SharePoint (no OneDrive), permiso `Sites.Selected`, roles a pedir (Application Administrator + SharePoint Administrator, consentimiento final por alguien con Global/Privileged Role Administrator), y pendiente de resolver si hace falta IP fija (QuotaGuard Static, 19 $/mes) o si el administrador de Grúas Álvarez acepta autenticación por certificado en su lugar — pregunta pendiente de respuesta. Bug cruzado sin diagnosticar, ya mencionado en sesiones anteriores y ahora relevante para el punto 9 del diseño de tickets: "revisar/editar" en el listado de partes de operario no entra en modo edición real. |
