# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V05.md

# Anexo de Hito V05 — Arquitectura Omnicanal IVR ↔ WhatsApp
# Proyecto: EnterpriseBot
# Estado: EN PROGRESO
# Fecha de inicio: 2026-04-20

---

## 1. Visión General del Hito

El Hito 5 cierra el ciclo omnicanal completo de EnterpriseBot, conectando los
dos canales operativos (IVR de voz y WhatsApp) en un flujo de información
unificado y coherente. La experiencia del usuario final mejora cualitativamente:
el agente humano receptor de una transferencia de llamada recibe, antes de
atenderla, un resumen estructurado vía WhatsApp con los datos capturados por
el IVR durante la conversación.

El hito se articula en tres líneas de trabajo independientes pero convergentes:

- **Línea A — Panel:** Visibilidad de sesiones WhatsApp activas en el sidebar
  del panel de gestión `/panel/`.
- **Línea B — Persistencia IVR:** Nuevo modelo `CallDataCapture` que persiste
  en base de datos los datos recogidos por los `DataCaptureSet` durante una
  llamada. Cierre del bucle de captura iniciado en el Hito 3.
- **Línea C — Puente IVR ↔ WhatsApp:** Orquestación del flujo completo:
  IVR captura datos → persiste en BD → WhatsApp notifica al agente interno
  → transfer de llamada ejecutado. Línea de mayor complejidad técnica del hito.

---

## 2. Arquitectura Técnica

### 2.1. Modelo CallDataCapture (Línea B)

Nuevo modelo Django en la app `ivr_config`. Registra cada conjunto de datos
capturados durante una sesión de llamada activa.

Campos previstos:

- `call_sid` — CharField: SID de la llamada Twilio (FK lógica, no relacional).
- `call_flow` — ForeignKey → `CallFlow`: flujo IVR que originó la captura.
- `section` — ForeignKey → `Section`: sección en la que se produjo la captura.
- `contact` — ForeignKey → `Contact`, null=True: contacto referente de la
  sección en el momento de la llamada (snapshot).
- `captured_data` — JSONField: diccionario clave→valor con los datos capturados
  por el `DataCaptureSet` activo (nombre, teléfono, motivo, etc.).
- `captured_at` — DateTimeField(auto_now_add=True): timestamp de la captura.
- `notified_via_whatsapp` — BooleanField(default=False): flag que indica si
  la notificación WhatsApp fue enviada correctamente.
- `whatsapp_sent_at` — DateTimeField(null=True, blank=True): timestamp del
  envío WhatsApp exitoso.

### 2.2. Flujo de Notificación IVR → WhatsApp (Línea C)

Secuencia de ejecución dentro de `vox_bridge/services.py` al completarse
la captura de datos del `DataCaptureSet`:

1. El motor IVR detecta que todos los campos del `DataCaptureSet` activo
   han sido completados.
2. Se instancia y persiste un `CallDataCapture` con los datos recogidos
   (`notified_via_whatsapp=False`).
3. Se recupera el `Contact` referente de la `Section` activa.
4. Si el contacto tiene número de teléfono registrado, se invoca
   `whatsapp/services.py::send_capture_notification()` de forma asíncrona.
5. La función construye el mensaje de notificación con los datos capturados
   y lo envía vía Twilio WhatsApp al número del contacto.
6. Tras envío exitoso, se actualiza `CallDataCapture.notified_via_whatsapp=True`
   y `whatsapp_sent_at=now()`.
7. El motor IVR continúa con el transfer de llamada previsto.

### 2.3. Entrada WhatsApp en el Panel (Línea A)

Extensión del panel `/panel/` existente:

- Nueva entrada en el sidebar: **"WhatsApp Activo"**.
- Vista que lista las `WhatsAppSession` con `status='active'` de la empresa
  del usuario autenticado, ordenadas por `updated_at` descendente.
- Cada fila muestra: número de origen, fecha de inicio, último mensaje recibido
  (extracto), y enlace al historial completo de la sesión.
- Sin nueva app Django — se implementa dentro de la app `panel` existente.

---

## 3. Hoja de Ruta

### Línea A — Panel: Sesiones WhatsApp Activas

#### Paso 1 — Vista y URL `whatsapp_sessions` en `panel`
- Añadir vista `WhatsAppSessionListView` en `panel/views.py`.
- Registrar URL `/panel/whatsapp/sessions/` en `panel/urls.py`.
- Estado: PENDIENTE

#### Paso 2 — Template `whatsapp_session_list.html`
- Crear template con tabla de sesiones activas.
- Integrar entrada en sidebar de `base.html`.
- Estado: PENDIENTE

### Línea B — Persistencia IVR: Modelo CallDataCapture

#### Paso 3 — Modelo `CallDataCapture` en `ivr_config/models.py`
- Definir modelo con los campos descritos en §2.1.
- Estado: PENDIENTE

#### Paso 4 — Migración de base de datos
- Generar y aplicar migración Django para `CallDataCapture`.
- Estado: PENDIENTE

#### Paso 5 — Registro en admin Django
- Añadir `CallDataCaptureAdmin` en `ivr_config/admin.py` para supervisión
  interna (superusuario).
- Estado: PENDIENTE

### Línea C — Puente IVR ↔ WhatsApp

#### Paso 6-bis — Template Meta para notificación de captura IVR
- Crear template de notificación en Twilio Content Template Builder.
- Contenido: resumen estructurado de datos capturados por el IVR
  (nombre, teléfono, motivo) dirigido al agente interno receptor.
- Registrar el template en BD vía `seed_whatsapp_templates` para
  la empresa Grupo Álvarez.
- El template debe ser de categoría UTILITY para garantizar entrega
  fuera de la ventana de sesión Meta de 24 horas.
- SID: `HX1a301d32db3acaedf6b13d83fd7579ac` — registrado en BD 2026-04-21.
- Estado: COMPLETADO

#### Paso 6 — Función `send_capture_notification()` en `whatsapp/services.py`
- Implementar función de notificación con construcción de mensaje y envío
  Twilio WhatsApp usando el template registrado en Paso 6-bis.
- Estado: PENDIENTE

#### Paso 7 — Tool `submit_captured_data` y integración en `vox_bridge/services.py`
- Añadir tool `submit_captured_data` al `LiveConnectConfig` de Gemini Live.
  Gemini la invoca cuando tiene todos los campos requeridos del `DataCaptureSet`
  activo, con los valores inferidos del contexto natural de la conversación
  o recogidos mediante preguntas. Nunca vuelve a preguntar datos ya mencionados.
- Flujo de ejecución al recibir el `tool_call`:
  1. Extraer los argumentos del `tool_call` (campos capturados).
  2. Instanciar y persistir `CallDataCapture` con esos datos.
  3. Invocar `send_capture_notification()` vía `asyncio.create_task(
     asyncio.to_thread(...))` para no bloquear el pipeline de audio.
  4. Responder a Gemini con `tool_response` confirmando la captura.
  5. El transfer (`transfer_to_section_contact`) se produce en un
     `tool_call` posterior, una vez Gemini ha confirmado la captura
     y pronunciado la frase de despedida/transferencia.
- Estado: PENDIENTE

#### Paso 8-pre — Gestión de DataCaptureSet en el panel
Desbloqueador del Paso 8. Sin esta funcionalidad ninguna empresa puede
definir los campos de captura de sus secciones, lo que impide la validación
E2E de la Línea C.

Alcance:
- Vista `DataCaptureSetListView` en `panel/views.py` — listado de conjuntos
  de captura de la empresa, accesible solo a rol ADMIN.
- Vista `DataCaptureSetCreateView` / `DataCaptureSetUpdateView` — formulario
  con interfaz de filas añadibles dinámicamente (JS) para definir los campos:
  `key` (identificador interno), `label` (texto que verá el agente IVR),
  `type` (text / phone / location / reference / date / free_text),
  `required` (booleano).
- URL: `/panel/datacapturesets/`
- Entrada en sidebar bajo la sección Configuración: "Captura de datos".
- Constructor de filas JS inline integrado también en el formulario de sección
  (`panel/templates/panel/sections/form.html`): permite crear o vincular un
  `DataCaptureSet` directamente desde la edición de sección sin salir de ella.
- Vinculación a sección: `SectionForm` incluye `data_capture_set` como campo
  opcional con queryset restringido a la empresa.
- Estado: COMPLETADO 2026-04-21

#### Paso 8 — Validación E2E
- Llamada real a número Grupo Álvarez.
- Verificar: captura de datos → persistencia en BD → notificación WhatsApp
  recibida en teléfono del contacto → transfer ejecutado.
- Estado: PENDIENTE

### Línea D — Circulares y Notificaciones Internas WhatsApp

#### Paso 9 — Modelo `InternalBroadcast` en `whatsapp/models.py`
- Nuevo modelo que registra cada circular enviada a contactos internos.
- Campos previstos:
  - `company` — ForeignKey → `Company`.
  - `subject` — CharField: asunto de la circular.
  - `body` — TextField: cuerpo del mensaje.
  - `recipients` — ManyToManyField → `Contact` a través de
    `InternalBroadcastRecipient`: registra destinatario, estado de
    entrega individual y timestamp de envío por contacto.
  - `sent_at` — DateTimeField(null=True): timestamp de envío efectivo.
  - `status` — CharField: DRAFT / SENT / PARTIAL (algún envío falló).
  - `created_at` / `updated_at` — timestamps de auditoría.
- Estado: PENDIENTE

#### Paso 10 — Template Meta UTILITY para circulares internas
- Crear template de circular en Twilio Content Template Builder.
- Estructura: asunto como cabecera, cuerpo libre del mensaje.
- Categoría UTILITY para garantizar entrega fuera de ventana 24h.
- Registrar en BD vía `seed_whatsapp_templates` para Grupo Álvarez.
- Estado: PENDIENTE

#### Paso 11 — Vista de gestión de circulares en `/panel/`
- Nueva vista `InternalBroadcastView` en `panel/views.py`.
- Formulario superior: selector multiselect de contactos de la empresa,
  campo asunto, campo cuerpo (textarea), botón Enviar.
- Listado inferior: circulares enviadas ordenadas por `sent_at` desc.
  Cada fila muestra: asunto, destinatarios, fecha de envío, estado.
  Botonera por fila: Reenviar (crea nueva circular con mismo contenido),
  Editar (solo si status=DRAFT), Suprimir.
- URL: `/panel/whatsapp/broadcasts/`
- Entrada en sidebar bajo la sección WhatsApp: "Circulares".
- Estado: PENDIENTE

#### Paso 12 — Función `send_broadcast()` en `whatsapp/services.py`
- Implementar envío masivo iterando sobre `recipients`.
- Usar template registrado en Paso 10.
- Actualizar `InternalBroadcastRecipient` por cada envío individual
  con estado de entrega y timestamp.
- Actualizar `InternalBroadcast.status` a SENT o PARTIAL según resultado.
- Estado: PENDIENTE

#### Paso 13 — Validación E2E Línea D
- Crear circular desde el panel, seleccionar contactos, enviar.
- Verificar recepción en teléfonos de contactos seleccionados.
- Verificar actualización de estado en listado del panel.
- Estado: PENDIENTE

---

### Línea E — Generador Automático de Flujos IVR por Sección

#### Visión
El `system_instruction` del `CallFlow` vinculado a una sección se genera
automáticamente al pulsar **Guardar** en la vista de edición de sección,
eliminando la edición manual del flujo IVR. El campo permanece editable
exclusivamente para retoques puntuales posteriores. La edición humana del
flujo IVR queda así restringida a excepciones, no a la norma.

El generador construye el `system_instruction` a partir de los datos
declarativos de la sección:
- **Horario** (`SectionSchedule` / `is_24h`): disponibilidad y mensaje
  de fuera de horario.
- **Contactos** (`SectionContact` con prioridad): contacto principal,
  secundario y modo de guardia activo.
- **Datos a capturar** (`DataCaptureSet.fields`): qué recoge el IVR
  (nombre, teléfono, ubicación, referencia, etc.).
- **Template WhatsApp**: derivado de los campos del `DataCaptureSet`.
  Si se requiere ubicación → template con ubicación.
  Si solo datos de contacto → template simple.

#### Sistema de Guardia — Tres Modos

**Modo 1 — Ad-hoc:**
Campo `duty_contact` (FK → `Contact`, null=True) en `Section`. El ADMIN
lo actualiza manualmente en la vista de edición cuando hay relevo. El
generador usa este contacto como contacto de guardia activo.

**Modo 2 — Cuadrante:**
Nuevo modelo `DutyRoster` vinculado a `Section`. Define qué contacto está
de guardia por día de la semana y franja horaria. En tiempo de llamada,
el generador consulta el cuadrante para determinar el contacto activo.
Estructura prevista:
- `section` → FK a `Section`.
- `contact` → FK a `Contact`.
- `weekday` → IntegerField (0=lunes … 6=domingo).
- `time_from` / `time_to` → TimeField: franja de guardia.

**Modo 3 — Teléfono de relevo (testigo):**
Campo `duty_phone` (CharField, null=True) en `Section`. Número fijo
asociado a la guardia cuyo dispositivo físico rota entre personas según
el turno. El IVR llama siempre a ese número sin identificar al portador.
No hay contacto nominal — hay un número de guardia.

#### Campo selector de modo de guardia
Campo `duty_mode` en `Section` con choices:
- `NONE` — sin guardia (secciones sin servicio fuera de horario).
- `ADHOC` — contacto ad-hoc manual.
- `ROSTER` — cuadrante semanal.
- `RELAY` — teléfono de relevo.

La vista de edición de sección muestra u oculta los campos relevantes
según el `duty_mode` seleccionado (lógica JS en el formulario).

#### Renombrado del botón Guardar
El botón **"Editar"** en todos los formularios del panel pasa a llamarse
**"Guardar"** para evitar la confusión actual (el botón guarda cambios,
no entra en modo edición). Afecta a todos los templates de formulario
de la app `panel`.

#### DataCaptureSet.fields — Estructura a definir
El campo `fields` (JSONField) del modelo `DataCaptureSet` requiere una
estructura normalizada para que el generador pueda construir el
`system_instruction` de forma determinista. Estructura propuesta:
````json
[
  {
    "key": "nombre",
    "label": "Nombre del llamante",
    "type": "text",
    "required": true
  },
  {
    "key": "telefono",
    "label": "Teléfono de contacto",
    "type": "phone",
    "required": true
  },
  {
    "key": "ubicacion",
    "label": "Ubicación del vehículo",
    "type": "location",
    "required": false
  }
]
````
Tipos soportados previstos: `text`, `phone`, `location`, `reference`,
`date`, `free_text`. La definición final se acordará con Grupo Álvarez.

#### Pasos de implementación

#### Paso 14 — Renombrado del botón Guardar en templates del panel
- Sustituir el literal "Editar" por "Guardar" en todos los templates
  de formulario de la app `panel`.
- Estado: COMPLETADO PARCIAL 2026-04-21 — Aplicado en `SectionUpdateView`
  (`context["action"] = "Guardar"`). Pendiente revisar resto de formularios
  en sesiones de Línea E.

#### Paso 15 — Campos de guardia en modelo `Section`
- Añadir `duty_mode` (CharField, choices NONE/ADHOC/ROSTER/RELAY).
- Añadir `duty_contact` (FK → Contact, null=True): modo ADHOC.
- Añadir `duty_phone` (CharField, null=True): modo RELAY.
- Migración correspondiente.
- Estado: PENDIENTE

#### Paso 16 — Modelo `DutyRoster`
- Nuevo modelo en `ivr_config/models.py` para el cuadrante semanal.
- Campos: `section`, `contact`, `weekday`, `time_from`, `time_to`.
- Migración correspondiente.
- Registro en admin Django.
- Estado: PENDIENTE

#### Paso 17 — Estructura normalizada de `DataCaptureSet.fields`
- Definir y documentar la estructura JSON estándar de campos.
- Actualizar el `help_text` del campo en el modelo.
- Actualizar el docstring de `DataCaptureSet`.
- Estado: PENDIENTE

#### Paso 18 — Generador de `system_instruction` (`ivr_config/services.py`)
- Implementar función `generate_section_system_instruction(section)`.
- Inputs: horario, contactos, modo de guardia, DataCaptureSet, template.
- Output: string `system_instruction` listo para persistir en `CallFlow`.
- Estado: PENDIENTE

#### Paso 19 — Integración del generador en la vista de edición de sección
- Al pulsar Guardar en `SectionUpdateView`, si la sección tiene un
  `CallFlow` vinculado, invocar el generador y persistir el resultado
  en `CallFlow.system_instruction`.
- Mostrar confirmación en el panel: "Flujo IVR actualizado automáticamente".
- Estado: PENDIENTE

#### Paso 20 — Actualización de la vista de edición de sección
- Añadir campos `duty_mode`, `duty_contact`, `duty_phone` al formulario.
- Lógica JS para mostrar/ocultar campos según `duty_mode` seleccionado.
- Integrar gestión del cuadrante `DutyRoster` como formset inline.
- Estado: PENDIENTE

---

## 4. Registro de Sesiones

| Sesión | Fecha | Pasos trabajados | Resumen |
|--------|-------|-----------------|---------|
| 001 | 2026-04-20 | — | Creación del anexo. Inicio formal del hito. |
| 002 | 2026-04-21 | 1, 2, 3, 4, 5, 6-bis, 6, 7 | Líneas A y B completadas. Línea C en curso: template ivr_capture_notification aprobado, send_capture_notification() implementado, tool submit_captured_data integrada en vox_bridge/services.py. Líneas D y E documentadas. Paso 8-pre identificado como desbloqueador del E2E. Incidencia must_change_password resuelta para alejandro_sergio. |
| 003 | 2026-04-21 | 8-pre, 14 (parcial) | Paso 8-pre completado: CRUD de DataCaptureSet en panel con constructor JS de filas dinámicas, entrada en sidebar, integración inline en formulario de sección. Renombrado botón Guardar en SectionUpdateView (Paso 14 parcial). Decisión de diseño: modo de flujo IVR por sección (sin flujo / automático / manual) a implementar en Línea E junto con Paso 19. Nombre del agente actualizado de Alia a María. Validación E2E (Paso 8) pendiente hasta implementar generador automático de flujos IVR. |
| 004 | 2026-04-21 | — | Sesión interrumpida sin trabajo efectivo. Inciso: creación del Hito V06 (Procesador de Partes de Trabajo PDF → Excel + BBDD). Hito V05 pasa a PAUSADO. La hoja de ruta queda intacta para su reanudación en sesiones futuras. |

---

## 5. Hoja de Ruta para la Siguiente Sesión

### Objetivo principal
Implementar el **selector de modo de flujo IVR por sección** (Paso 19 ampliado)
y ejecutar la **validación E2E del Paso 8** (llamada real con captura de datos,
persistencia en BD y notificación WhatsApp al agente receptor).

### Secuencia de trabajo

**1. Solicitar al inicio de sesión:**
- `panel/views.py`, `panel/forms.py`, `panel/urls.py`
- `panel/templates/panel/sections/form.html`
- `ivr_config/models.py`
- `ivr_config/services.py` (para auditar si existe o crear `generate_section_system_instruction()`)

**2. Selector de modo de flujo IVR en el formulario de sección (Paso 19 ampliado):**

El campo `call_flow` actual (selector de flujo existente) se sustituye por
un **selector de modo** con tres opciones mutuamente excluyentes:

- `NONE` — sin flujo IVR asignado. La sección no participa en el enrutamiento.
- `AUTO` — al pulsar Guardar, el generador construye el `system_instruction`
  a partir de los datos declarativos de la sección (contactos, horario,
  `DataCaptureSet`) y lo persiste en un `CallFlow` vinculado.
  Si la sección ya tiene un `CallFlow` vinculado, lo actualiza en su lugar.
  Si no tiene ninguno, crea uno nuevo con nombre `"Flujo — {section.name}"`.
- `MANUAL` — desplegable con los `CallFlow` existentes de la empresa
  para vincular directamente. El `system_instruction` no se toca.

Implementación:
- Añadir campo `flow_mode` como campo no persistido (`ChoiceField` en el
  formulario, no en el modelo) con choices `NONE` / `AUTO` / `MANUAL`.
  Se inicializa en `NONE` si `section.call_flow` es nulo, en `MANUAL` si
  tiene un `CallFlow` vinculado, y en `AUTO` si el `CallFlow` vinculado
  tiene `system_instruction` generado automáticamente (detectar por
  presencia de marcador en el texto, ver nota técnica).
- El selector `call_flow` existente se muestra/oculta con JS según el
  modo seleccionado: visible solo en `MANUAL`.
- En `SectionCreateView._form_valid()` y `SectionUpdateView._form_valid()`:
  leer `flow_mode` del POST y actuar en consecuencia:
  - `NONE`: `form.instance.call_flow = None`.
  - `AUTO`: invocar `generate_section_system_instruction(section)` de
    `ivr_config/services.py`, crear o actualizar el `CallFlow` vinculado
    y persistir el `system_instruction` generado.
  - `MANUAL`: vincular el `CallFlow` seleccionado sin modificar su contenido.

**3. Generador `generate_section_system_instruction()` en `ivr_config/services.py`:**
- Inputs: instancia de `Section` ya guardada (con `DataCaptureSet`,
  `SectionContact`, `SectionSchedule` e `is_24h` disponibles).
- Output: string `system_instruction` listo para persistir en `CallFlow`.
- El generador construye el prompt con:
  - Identidad del agente (nombre María, empresa).
  - Descripción de la sección.
  - Disponibilidad: 24h o franjas horarias de `SectionSchedule`.
  - Contactos de la sección ordenados por prioridad (`SectionContact`).
  - Definición de la tool `submit_captured_data` con los campos del
    `DataCaptureSet` activo (key, label, type, required).
  - Tool `transfer_to_section_contact` para la transferencia posterior.
- Marcador obligatorio al final del `system_instruction` generado:
  `# [AUTO-GENERATED]` — permite detectar en futuras sesiones si el
  flujo fue generado automáticamente o editado manualmente.

**4. Validación E2E — Paso 8:**
- Crear `DataCaptureSet` para la sección "Asistencia" de Grupo Álvarez
  con campos: `nombre` (text, required), `telefono` (phone, required),
  `motivo` (free_text, required).
- Generar el flujo IVR automático para esa sección.
- Ejecutar llamada real al número de Grupo Álvarez.
- Verificar secuencia: captura de datos por María → `CallDataCapture`
  persistido en BD → notificación WhatsApp recibida en teléfono del
  contacto referente → transfer de llamada ejecutado.

### Notas técnicas
- `TWILIO_WHATSAPP_SENDER=+34607961650` configurado en `.env`. ✓
- Template `ivr_capture_notification` (SID: `HX1a301d32db3acaedf6b13d83fd7579ac`)
  aprobado por Meta y registrado en BD para Grupo Álvarez. ✓
- La tool `submit_captured_data` ya está integrada en `vox_bridge/services.py`. ✓
- El marcador `# [AUTO-GENERATED]` en `system_instruction` es la fuente
  de verdad para determinar el modo de flujo al cargar el formulario de sección.

## 6. Decisiones de Diseño y Notas Técnicas

- **Sin nueva app Django:** Las tres líneas de trabajo se implementan sobre
  apps existentes (`ivr_config`, `panel`, `whatsapp`, `vox_bridge`). No se
  crea ninguna app nueva en este hito.
- **Asincronía en Línea C:** La llamada a `send_capture_notification()` desde
  el contexto async de `vox_bridge/services.py` debe gestionarse con
  `asyncio.create_task()` para no bloquear el flujo de audio. El transfer
  no espera confirmación de entrega WhatsApp.
- **Modelo texto para WhatsApp:** Confirmado desde Hito 4 — el canal WhatsApp
  usa `gemini-2.5-flash` (texto), no el modelo Live. La notificación de Línea C
  es un mensaje de texto plano, no conversacional.
- **Template WhatsApp para notificación:** Evaluar en Paso 6 si la notificación
  al agente interno requiere template Meta aprobado (si el número destino no ha
  iniciado conversación en las últimas 24h) o puede enviarse como mensaje libre
  dentro de ventana activa.
- **Documentos satélite:** El directorio `DOCS_ATTACHED_2_ANNEX_V05/` queda
  creado y versionado. Se poblará si en Línea C la complejidad del flujo
  asíncrono IVR ↔ WhatsApp requiere documentación técnica dedicada.
