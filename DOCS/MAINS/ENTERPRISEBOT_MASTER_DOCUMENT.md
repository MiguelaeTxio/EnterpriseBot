# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ENTERPRISEBOT_MASTER_DOCUMENT.md
# Documento Maestro: Proyecto EnterpriseBot
---
## 1. Visión General del Proyecto
EnterpriseBot es una solución omnicanal de nivel empresarial orientada a la orquestación de inteligencia artificial conversacional en tiempo real. El objetivo es proporcionar una experiencia de usuario fluida, humana y de baja latencia a través de canales de voz y mensajería.

## 2. Arquitectura Técnica (Pivotaje Estratégico a Multimodal Live API)
*   **Entorno Virtual:** EnterpriseBot_venv (Python 3.10)
*   **Framework Base:** Django (Configurado para gestión de WebSockets y tareas asíncronas)
*   **Motor de IA (ESTÁNDAR OBLIGATORIO):** Gemini 3.1 Live (models/gemini-3.1-flash-live-preview).
    - **Naturaleza:** Arquitectura Stateful (Estado persistente) para streaming A2A (Audio-to-Audio) nativo.
    - **Prohibición:** Queda terminantemente prohibido el uso de modelos de la familia "Pro" no-Live para el flujo de voz.
*   **Middleware de Audio (Sidecar):** Capa de transcodificación obligatoria entre Twilio (G.711 mu-law/A-law) y Gemini Live (PCM Linear 16-bit).

## 3. Hoja de Ruta Estratégica
### Hito 1: Validación de Infraestructura de Voz en Tiempo Real (PAUSADO)
(Ver anexo `ENTERPRISEBOT_ATTACHED_MILESTONE_V01.md`)
- Implementación de puente con Twilio Media Streams.
- Estabilización del flujo de transcodificación mu-law/A-law -> PCM.
- Orquestación de audio nativo con Gemini Live 2.5 Flash Native Audio (Vertex AI).
- Validación E2E con llamada real confirmada.

### Hito 2: Validación y Aislamiento de Diagnóstico vía Aplicación test_live (PAUSADO)
(Ver anexo `ENTERPRISEBOT_ATTACHED_MILESTONE_V02.md`)
- Creación de aplicación Django `test_live` para aislamiento de API.
- Implementación de interfaz "Walkie-Talkie" para pruebas directas.
- Auditoría de Handshake de Google GenAI (v1beta) sin dependencias externas.

### Hito 3: IVR Conversacional Configurable desde Producción (PAUSADO)
(Ver anexo `ENTERPRISEBOT_ATTACHED_MILESTONE_V03.md`)
- Diseño del modelo de datos multiempresa (Company, CompanyUser, Contact, Section,
  PhoneNumber, CallFlow, PresenceStatus, CorporateVoiceProfile, DataCaptureSet).
- Sistema de presencia con gestión de ausencias temporales y persistentes.
- Panel de administración personalizado para empresas cliente (sin acceso al admin Django).
- Motor de inyección dinámica de configuración IVR en LiveConnectConfig.

---
## 4. Directrices Técnicas Vinculantes

Estas directrices son de **OBLIGADO CUMPLIMIENTO** en todas las sesiones
de desarrollo del proyecto. El modelo las carga al inicio de sesión desde
este documento y las aplica sin excepción.

### 4.1. Inteligencia Artificial
- **SDK:** `google-genai 1.69.0`
- **Modelo IVR Conversacional:** `gemini-live-2.5-flash-native-audio`
- **Plataforma:** Vertex AI — autenticación via Service Account JSON
- **Variables de entorno:** `GCP_CREDENTIALS_PATH`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`
- **Protocolo de sesión:** Setup-First via `async with client.aio.live.connect(...)`
- **Voice:** `Aoede` — obligatorio en `speech_config` para modelo de audio nativo
- **VAD servidor:** `disabled=True` (obligatorio para puentes de telefonía)
- **Greeting:** `await session.send_client_content(turns=..., turn_complete=True)`
- **Firma audio SDK 1.69.0:** `await session.send_realtime_input(audio=types.Blob(data=..., mime_type='audio/pcm;rate=16000'))`

### 4.2. Telefonía
- **Twilio SDK Python:** `twilio 9.10.4`
- **Autenticación Twilio:** API Key (TWILIO_API_KEY_SID + TWILIO_API_KEY_SECRET)
- **Transcodificación:** mu-law 8kHz ↔ PCM 16kHz ↔ PCM 24kHz via `audioop`
- **streamSid:** OBLIGATORIO en nivel raíz de cada mensaje `media` saliente

### 4.3. Infraestructura y Framework
- **Framework:** Django `5.2.12`
- **Servidor async:** aiohttp `3.13.5` — puerto `8081`
- **Túnel:** ngrok v3 — API local en puerto `4041`
- **Entorno:** PythonAnywhere WSGI — Python `3.10.5`
- **Entorno virtual:** `EnterpriseBot_venv`
- **Base de datos:** MySQL — `MiguelAeTxio$enterprisebot`
- **Gestión de dependencias:** `pip-tools` (requirements.in → requirements.txt)

### 4.5. Gestión de Hitos
Ningún hito se marca como COMPLETADO. Los hitos oscilan únicamente entre
EN PROGRESO y PAUSADO. Solo puede haber UN hito EN PROGRESO en cada momento.
Cuando todos los hitos estén suficientemente maduros, el Hito de Ruegos y
Preguntas (Sistema de Stand-by) pasa a EN PROGRESO para atender incidencias
generales sin alterar la hoja de ruta.

### 4.4. Requisito SINE QUA NON
Antes de entregar o implementar cualquier código que involucre servicios
externos o APIs, el modelo **DEBE** actualizarse en línea obligatoriamente
para usar datos actuales de implementación en lugar de datos obsoletos.

### Hito 4: Canal WhatsApp — Chatbot Conversacional y Sistema de Presencia (PAUSADO)
(Ver anexo `ENTERPRISEBOT_ATTACHED_MILESTONE_V04.md`)
- Integración de WhatsApp como canal bidireccional sobre infraestructura Twilio existente.
- Chatbot conversacional impulsado por Gemini 2.5 Flash (texto) con contexto multiempresa.
- Cierre del bucle de presencia del Hito 3: webhook /api/whatsapp/presence/ y tareas Celery.
- Nueva app Django `whatsapp` con modelos WhatsAppSession, WhatsAppMessage, WhatsAppTemplate.
- Templates Meta gestionados via Content Template Builder (SID prefijo HX).
- Sender +34607961650 registrado y operativo en producción. Validación E2E superada.
- Panel de gestión de templates WhatsApp integrado en /panel/ (Paso 24). COMPLETADO 2026-04-20.

### Hito 5: Arquitectura Omnicanal IVR ↔ WhatsApp (PAUSADO)
(Ver anexo `ENTERPRISEBOT_ATTACHED_MILESTONE_V05.md`)
- Hito híbrido que cierra el ciclo omnicanal completo de EnterpriseBot.
- Línea A — Panel: entrada WhatsApp en sidebar con historial de sesiones activas.
- Línea B — Persistencia IVR: nuevo modelo CallDataCapture vinculado a Section,
  Contact y CallFlow. Los datos capturados por DataCaptureSet persisten en BD.
- Línea C — Puente IVR ↔ WhatsApp: datos capturados por el IVR (nombre, teléfono,
  motivo) se envían vía WhatsApp al contacto referente de la sección antes del
  transfer de llamada. Flujo: IVR captura → persiste en BD → WhatsApp notifica
  al agente interno → transfer ejecutado. Cierre del ciclo omnicanal completo.

### Hito 6: Procesador de Partes de Trabajo PDF → Excel + BBDD (PAUSADO)
(Ver anexo `ENTERPRISEBOT_ATTACHED_MILESTONE_V06.md`)
- Procesamiento documental de PDFs con fotografías de partes de trabajo diarios.
- Extracción automática de campos mediante Gemini Vision por cada página/parte.
- Persistencia en BD de los datos extraídos (modelos WorkOrder y WorkOrderEntry).
- Generación de informe Excel descargable desde el panel de gestión.
- Funcionalidad multiempresa integrada en el panel existente.
- Constructor de gráficos client-side (Plotly.js) con perfiles guardados por usuario.
- Listado de PDFs mejorado: nombre legible, desplegable de acciones, modal de incidencias.
- Refactor CSS: panel.css extraido del bloque inline de base.html. COMPLETADO 2026-04-27.

### Hito 7: Partes Diarios de Reparación — Entrada Digital desde el Panel (PAUSADO)
(Ver anexo `ENTERPRISEBOT_ATTACHED_MILESTONE_V07.md`)
- Nuevos roles `WORKSHOP` (operario de taller) y `DRIVER` (reservado) en CompanyUser.
- WorkshopRequiredMixin creado. OperatorDashboardView con selector de tres vías implementada.
- Navegación restringida para rol WORKSHOP: sidebar simplificado con único ítem Nuevo parte.
- Tres vías de entrada convergentes en un formulario único de confirmación:
    - Form: formulario web estructurado. Persistencia directa en BD. Sin IA. Coste cero.
    - STT: dictado por voz via Web Speech API (nativa, sin coste, sin IA). Pre-rellena el formulario.
    - Upload: foto/PDF manuscrito procesado por Gemini Vision. Pre-rellena el formulario
      con validación campo a campo de datos faltantes/ilegibles por el operario.
- El formulario de confirmación es el punto de convergencia de las tres vías.
- Pasos 1 y 2 completados. Pausado en sesión 002 (2026-04-28) para abrir H8.

### Hito 8: Mejoras Procesador PDF→Excel + HTMX (PAUSADO)
(Ver anexo `ENTERPRISEBOT_ATTACHED_MILESTONE_V08.md`)
- Implantación quirúrgica de HTMX en lista de PDFs (polling de estado automático)
  y editor de entradas inline (guardado automático por campo sin scroll al top).
- Mejoras del editor: insertar entrada entre líneas, drag & drop, restaurar entrada
  individual, avisos visuales de incidencias con normalización automática de color.
- Correcciones pipeline: columna mano de obra vacía en Excel + parser OCR (O/0, L/1, t/7).
- Detección de PDF duplicado en upload con modal de advertencia y confirmación.
- Concatenación de múltiples Excels con membrete individual por operario.
- Sesion 008: mejora de calidad de datos (auditoria BD, refuerzo prompt extraccion,
  comando repair_entry_lines, resolver morfologico simetrico). UX editor: badge de
  jornada diaria con cuatro niveles de color, columna Flags eliminada del panel.

### Hito 9: Informes y Analítica Cruzada de Costes de Maquinaria (PAUSADO)
(Ver anexo `ENTERPRISEBOT_ATTACHED_MILESTONE_V09.md`)
- Informes de costes de maquinaria cruzando mano de obra (Hito 6/8) con repuestos
  (Hito 10, pendiente de implementación).
- Visualización cruzada en el módulo de Analítica existente con gráficas personalizables.
- Los informes generados deben poderse representar en gráficas configurables por usuario.

### Hito 10: Albaranes de Proveedores — Entrada Digital vía Foto/PDF (PAUSADO)
(Ver anexo `ENTERPRISEBOT_ATTACHED_MILESTONE_V10.md`)
- Procesamiento de albaranes de proveedores mediante Gemini Vision (foto o PDF).
- Extracción automática de artículos, cantidades, precios y proveedor.
- Anotaciones sobre el albarán completo o por línea de artículo para asignar
  a centros de gasto (flota por vehículo, almacén, administración, secciones).
- Integración con el módulo de Informes (Hito 9) para cruzar costes de repuestos
  con costes de mano de obra por máquina.

### Hito 11: Albaranes a Clientes — Generación y Gestión Digital (PAUSADO)
(Ver anexo `ENTERPRISEBOT_ATTACHED_MILESTONE_V11.md`)
- Generación de albaranes a clientes desde el panel de gestión.
- Entrada de datos via formulario web o dictado STT (reutilizando infraestructura Hito 7).
- Extracción desde documentos físicos existentes vía Gemini Vision si procede.
- Integración con centros de gasto y módulo de Informes (Hito 9).

### Hito 12: Gestión de Centros de Gasto y Reorganización del Panel (PAUSADO)
(Ver anexo `ENTERPRISEBOT_ATTACHED_MILESTONE_V12.md`)
- Ampliacion del concepto MachineAsset a Centro de Gasto: maquinaria, administracion,
  almacen, alquiler, secciones externas y cualquier entidad facturable o asignable.
- Comando de gestion import_cost_centers para importar fichero actualizado CSV/Excel.
- CRUD de centros de gasto desde el panel: alta, baja, modificacion, dar de baja
  (campo activo) sin eliminar historico.
- Reorganizacion de la navegacion del panel: separacion de secciones mezcladas,
  agrupacion logica de flujos IVR, usuarios, partes, maquinaria/centros de gasto.
- Los centros de gasto no resueltos en partes historicos podran asignarse tras
  crear el centro de gasto correspondiente.

### Hito 13: Salas de Chat IRC por Sección (WhatsApp → Panel) (PAUSADO)
(Ver anexo `ENTERPRISEBOT_ATTACHED_MILESTONE_V13.md`)
- Sistema de salas de chat en tiempo cuasi-real en el panel, una sala por sección.
- Canal de entrada: WhatsApp (+34607961650). Mensajes de contactos replicados en
  la sala de su sección. Simula grupo WhatsApp sin restricción de 8 integrantes.
- Polling HTMX cada 4 segundos. Persistencia en BD con TTL de 7 días.
- Redis externo (instancia Redis Labs existente, DB separada) como broker Celery.
- Sala especial BREAKDOWNS: agente Gemini 2.5 Flash conversacional recoge datos
  de averías (máquina, síntoma, ubicación, urgencia) campo a campo vía WhatsApp.
- BreakdownTicket persistido en BD. SUPERVISOR cierra el ticket desde el panel.
- Nueva app Django `chat` con modelos ChatRoom, ChatMessage, BreakdownTicket,
  BreakdownConversationTurn. Comando init_chat_rooms idempotente.
- Rol WORKSHOPBOSS implementado con matriz de acceso completa. S009 completado.

### Hito 14: Gestión de Tickets de Avería y Órdenes de Reparación (PAUSADO)
(Ver anexo `ENTERPRISEBOT_ATTACHED_MILESTONE_V14.md`)
- Ciclo de vida completo del BreakdownTicket: creación manual desde panel,
  asignación a WORKSHOPBOSS, conversión a orden de reparación, cierre.
- Campos nuevos en BreakdownTicket: assigned_to (FK CompanyUser nullable),
  urgency usado como priority (LOW/MEDIUM/HIGH/CRITICAL).
- Integración con formulario de parte de operario: desplegable de órdenes
  de reparación abiertas con prerelleno automático de campos.
- Perfil propio del operario: OwnProfileView con edición de alias de chat.
- Gestión completa de membresía sala BREAKDOWNS: sincronización automática
  de contactos, color diferencial rojo/naranja, panel lateral de miembros.
- Completado en S010 (2026-05-21).

### Hito 15: Gestor de Árbol de Directorios con Power Automate (PAUSADO)
(Ver anexo `ENTERPRISEBOT_ATTACHED_MILESTONE_V15.md`)
- Interfaz web donde el usuario define un árbol de directorios destino.
- Lectura de una carpeta origen (y sus subcarpetas y archivos) en OneDrive/SharePoint.
- Organización automática de los archivos leídos según el árbol definido.
- Evaluación de Power Automate como motor de orquestación (la empresa ya dispone
  de licencia). Si Power Automate es suficiente, configuración de flujos sin agente
  propio. Si no, construcción de agente Django + IA.
- Actualización online obligatoria antes de implementar (Directriz 4.4).

### Hito 16: Motor de Presupuestos para Sección ASISTENCIA (PAUSADO)
(Ver anexo `ENTERPRISEBOT_ATTACHED_MILESTONE_V16.md`)
- Skill de generación de presupuestos para la sección de Asistencia.
- Tarifas configurables por compañía aseguradora.
- Motor de cálculo basado en datos de entrada del operario y facturas de referencia.
- Generación de documento de presupuesto exportable.

## 5. Sistema de Ruegos y Preguntas (Stand-by) (EN PROGRESO)
