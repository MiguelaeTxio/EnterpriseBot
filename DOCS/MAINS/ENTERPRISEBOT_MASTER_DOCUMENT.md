# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ENTERPRISEBOT_MASTER_DOCUMENT.md
# Documento Maestro: Proyecto EnterpriseBot

---

### 1. Visión General del Proyecto

EnterpriseBot es una solución omnicanal de nivel empresarial orientada a la
orquestación de inteligencia artificial conversacional en tiempo real. El
objetivo es proporcionar una experiencia de usuario fluida, humana y de baja
latencia a través de canales de voz y mensajería.

---

### 2. Arquitectura Técnica (Pivotaje Estratégico a Multimodal Live API)

- **Entorno Virtual:** EnterpriseBot_venv (Python 3.10)
- **Framework Base:** Django (Configurado para gestión de WebSockets y tareas asíncronas)
- **Motor de IA (ESTÁNDAR OBLIGATORIO):** Gemini 3.1 Live
  (`models/gemini-3.1-flash-live-preview`).
  - **Naturaleza:** Arquitectura Stateful (Estado persistente) para streaming
    A2A (Audio-to-Audio) nativo.
  - **Prohibición:** Queda terminantemente prohibido el uso de modelos de la
    familia "Pro" no-Live para el flujo de voz.
- **Middleware de Audio (Sidecar):** Capa de transcodificación obligatoria
  entre Twilio (G.711 mu-law/A-law) y Gemini Live (PCM Linear 16-bit).

---

### 3. Hoja de Ruta Estratégica

#### Hito 1: Validación de Infraestructura de Voz en Tiempo Real
(Ver anexo `ENTERPRISEBOT_ATTACHED_MILESTONE_V01.md`)
- Implementación de puente con Twilio Media Streams.
- Estabilización del flujo de transcodificación mu-law/A-law → PCM.
- Orquestación de audio nativo con Gemini Live 2.5 Flash Native Audio (Vertex AI).
- Validación E2E con llamada real confirmada.

#### Hito 2: Validación y Aislamiento de Diagnóstico vía Aplicación test_live
(Ver anexo `ENTERPRISEBOT_ATTACHED_MILESTONE_V02.md`)
- Creación de aplicación Django `test_live` para aislamiento de API.
- Implementación de interfaz "Walkie-Talkie" para pruebas directas.
- Auditoría de Handshake de Google GenAI (v1beta) sin dependencias externas.

#### Hito 3: IVR Conversacional Configurable desde Producción
(Ver anexo `ENTERPRISEBOT_ATTACHED_MILESTONE_V03.md`)
- Diseño del modelo de datos multiempresa.
- Sistema de presencia con gestión de ausencias temporales y persistentes.
- Panel de administración personalizado para empresas cliente.
- Motor de inyección dinámica de configuración IVR en LiveConnectConfig.

#### Hito 4: Canal WhatsApp — Chatbot Conversacional y Sistema de Presencia
(Ver anexo `ENTERPRISEBOT_ATTACHED_MILESTONE_V04.md`)
- Integración de WhatsApp como canal bidireccional sobre infraestructura Twilio existente.
- Chatbot conversacional impulsado por Gemini 2.5 Flash (texto) con contexto multiempresa.
- Cierre del bucle de presencia del Hito 3.
- Nueva app Django `whatsapp` con modelos WhatsAppSession, WhatsAppMessage, WhatsAppTemplate.
- Templates Meta gestionados via Content Template Builder (SID prefijo HX).
- Sender +34607961650 registrado y operativo en producción. Validación E2E superada.
- Panel de gestión de templates WhatsApp integrado en /panel/ (Paso 24). COMPLETADO 2026-04-20.

#### Hito 5: Arquitectura Omnicanal IVR ↔ WhatsApp
(Ver anexo `ENTERPRISEBOT_ATTACHED_MILESTONE_V05.md`)
- Hito híbrido que cierra el ciclo omnicanal completo de EnterpriseBot.
- Línea A — Panel: entrada WhatsApp en sidebar con historial de sesiones activas.
- Línea B — Persistencia IVR: nuevo modelo CallDataCapture.
- Línea C — Puente IVR ↔ WhatsApp: datos capturados por el IVR enviados vía
  WhatsApp al contacto referente antes del transfer de llamada.

#### Hito 6: Procesador de Partes de Trabajo PDF → Excel + BBDD
(Ver anexo `ENTERPRISEBOT_ATTACHED_MILESTONE_V06.md`)
- Procesamiento documental de PDFs con fotografías de partes de trabajo diarios.
- Extracción automática de campos mediante Gemini Vision.
- Persistencia en BD (modelos WorkOrder y WorkOrderEntry).
- Generación de informe Excel descargable.
- Constructor de gráficos client-side (Plotly.js) con perfiles guardados por usuario.
- Refactor CSS: panel.css extraído del bloque inline de base.html. COMPLETADO 2026-04-27.

#### Hito 7: Partes Diarios de Reparación — Entrada Digital desde el Panel
(Ver anexo `ENTERPRISEBOT_ATTACHED_MILESTONE_V07.md`)
- Nuevos roles `WORKSHOP` y `DRIVER` en CompanyUser.
- Tres vías de entrada convergentes: Form / STT / Upload (Gemini Vision).
- El formulario de confirmación es el punto de convergencia de las tres vías.
- Pasos 1 y 2 completados. Pausado en sesión 002 (2026-04-28) para abrir H8.

#### Hito 8: Mejoras Procesador PDF→Excel + HTMX
(Ver anexo `ENTERPRISEBOT_ATTACHED_MILESTONE_V08.md`)
- Implantación quirúrgica de HTMX en lista de PDFs y editor de entradas inline.
- Mejoras del editor: insertar entrada entre líneas, drag & drop, restaurar entrada.
- Correcciones pipeline: columna mano de obra vacía en Excel + parser OCR.
- Concatenación de múltiples Excels con membrete individual por operario.

#### Hito 9: Informes y Analítica Cruzada de Costes de Maquinaria
(Ver anexo `ENTERPRISEBOT_ATTACHED_MILESTONE_V09.md`)
- Informes de costes cruzando mano de obra (H6/H8) con repuestos (H10).
- Visualización cruzada en el módulo de Analítica con gráficas personalizables.

#### Hito 10: Albaranes de Proveedores — Entrada Digital vía Foto/PDF
(Ver anexo `ENTERPRISEBOT_ATTACHED_MILESTONE_V10.md`)
- Procesamiento de albaranes mediante Gemini Vision.
- Anotaciones por línea de artículo para asignar a centros de gasto.
- Integración con módulo de Informes (H9).

#### Hito 11: Albaranes a Clientes — Generación y Gestión Digital
(Ver anexo `ENTERPRISEBOT_ATTACHED_MILESTONE_V11.md`)
- Generación de albaranes a clientes desde el panel.
- Entrada via formulario web o dictado STT.
- Integración con centros de gasto y módulo de Informes (H9).

#### Hito 12: Gestión de Centros de Gasto y Reorganización del Panel
(Ver anexo `ENTERPRISEBOT_ATTACHED_MILESTONE_V12.md`)
- Ampliación del concepto MachineAsset a Centro de Gasto.
- Comando de gestión `import_cost_centers`.
- CRUD de centros de gasto desde el panel.
- Reorganización de la navegación del panel.

#### Hito 13: Salas de Chat IRC por Sección (WhatsApp → Panel)
(Ver anexo `ENTERPRISEBOT_ATTACHED_MILESTONE_V13.md`)
- Sistema de salas de chat en tiempo cuasi-real, una sala por sección.
- Polling HTMX cada 4 segundos. Persistencia en BD con TTL de 7 días.
- Sala especial BREAKDOWNS: agente Gemini 2.5 Flash conversacional.
- Nueva app Django `chat`. Rol WORKSHOPBOSS implementado. S009 completado.

#### Hito 14: Gestión de Tickets de Avería y Órdenes de Reparación
(Ver anexo `ENTERPRISEBOT_ATTACHED_MILESTONE_V14.md`)
- Ciclo de vida completo del BreakdownTicket.
- Integración con formulario de parte de operario.
- Perfil propio del operario: OwnProfileView.
- Completado en S010 (2026-05-21).

#### Hito 15: Gestor de Árbol de Directorios con Power Automate
(Ver anexo `ENTERPRISEBOT_ATTACHED_MILESTONE_V15.md`)
- Interfaz web para definir árbol de directorios destino.
- Lectura de carpeta origen en OneDrive/SharePoint.
- Evaluación de Power Automate como motor de orquestación.

#### Hito 16: Motor de Presupuestos para Sección ASISTENCIA
(Ver anexo `ENTERPRISEBOT_ATTACHED_MILESTONE_V16.md`)
- Skill de generación de presupuestos para la sección de Asistencia.
- Tarifas configurables por compañía aseguradora.
- Motor de cálculo basado en datos de entrada del operario.
- Generación de documento de presupuesto exportable.

#### Hito 17: Albaranes y Órdenes de Trabajo ASISTENCIA
(Ver anexo `ENTERPRISEBOT_ATTACHED_MILESTONE_V17.md`)
- Generación de órdenes de trabajo desde presupuesto aceptado o entrada directa.
- Albarán digital prellenado enviado al operario vía notificación WhatsApp.
- Interfaz móvil optimizada. Firma digital del cliente en pantalla táctil.
- Modo offline PWA con sincronización automática.

#### Hito 18: Gestión de Mapas y Geolocalización
(Ver anexo `ENTERPRISEBOT_ATTACHED_MILESTONE_V18.md`)
- Geocodificación de bases desde el panel: Google Maps Platform.
- Coordenadas persistidas en Base.latitude/longitude.
- Cálculo de ruta en wizard: carretera + PK → Google Routes API → km real + peajes.
- Campos de ruta en Budget: road_name, pk_km, route_distance_km, route_toll_cost.
- Peajes como concepto adicional en calculate_budget().

#### Hito 19: Mejoras WorkOrderAdminHistoryView
(Ver anexo `ENTERPRISEBOT_ATTACHED_MILESTONE_V19.md`)
- Filtro adicional por familia de avería en WorkOrderAdminHistoryView.
- Campo de búsqueda libre acotado a fault_description + repair_notes.
- Ordenación ascendente/descendente por columna en las tres pestañas.
- Motor de exportación por plantillas: sustituye completamente a WorkOrderAdminExportView.
- Nuevo modelo `ExportTemplate` en app `work_order_processor`.

#### Hito 20: Laboratorio de Análisis Unificado
(Ver anexo `ENTERPRISEBOT_ATTACHED_MILESTONE_V20.md`)
- Unificación y sustitución de las vistas Gráficas, Analítica CdG e Informes.
- Centro de análisis configurable por cinco dimensiones.
- Gráficas interactivas via Apache ECharts 5 (CDN).
- Vista de tres paneles con divisor arrastrable y pantalla completa independiente.

#### Hito 21: Refactorización Arquitectónica — Split de panel/views.py
(Ver anexo `ENTERPRISEBOT_ATTACHED_MILESTONE_V21.md`)
- Desmantelamiento del fichero monolítico panel/views.py (16.482 líneas tras S049).
- Fase B: extraer vistas de operario → panel/views_operator.py.
- Fase C: extraer vistas de supervisor/partes → panel/views_workorders.py.
- Fase D: extraer vistas de flota → panel/views_fleet.py.
- Fase E: extraer vistas IVR config → panel/views_ivr.py.
- Fase F: extraer vistas auth+WhatsApp → panel/views_auth.py.
- Objetivo final: panel/views.py < 200 líneas (solo imports y re-exports).

#### Hito 22: Visor de Historial de Máquinas (Operario)
(Ver anexo `ENTERPRISEBOT_ATTACHED_MILESTONE_V22.md`)
- Vista de solo lectura para rol WORKSHOP que permite consultar el historial
  completo de intervenciones sobre cualquier máquina de la flota.
- El operario selecciona una máquina y un rango de fechas y obtiene un
  listado cronológico: fecha, operario, familia de avería, subcategoría,
  descripción, reparación y horas invertidas.
- Objetivo: que el operario pueda contextualizar una orden de trabajo,
  identificar patrones de avería recurrentes y detectar problemas ocultos
  que generen averías periódicas en una parte concreta de una máquina.
- Sin acceso a costes ni a partes individuales. Solo lectura, sin exportación.

---

### 4. Directrices Técnicas Vinculantes

Estas directrices son de **OBLIGADO CUMPLIMIENTO** en todas las sesiones
de desarrollo del proyecto sin excepción.

#### 4.1. Inteligencia Artificial

- **SDK:** `google-genai 2.7.0`
- **Modelo IVR Conversacional (Live API, voz):** `gemini-live-2.5-flash-native-audio`
- **Modelo de texto/visión no-Live (OBLIGATORIO para código nuevo desde S001-H10, 2026-06-30):**
  `gemini-3.5-flash`. Aplica a extracción de documentos, clasificación
  de texto, generación de JSON estructurado y cualquier uso de
  `client.models.generate_content()` que no sea Live API.
- **Plataforma:** Vertex AI — autenticación via Service Account JSON
- **Variables de entorno:** `GCP_CREDENTIALS_PATH`, `GOOGLE_CLOUD_PROJECT`,
  `GOOGLE_CLOUD_LOCATION`
- **Protocolo de sesión:** Setup-First via `async with client.aio.live.connect(...)`
- **Voice:** `Aoede` — obligatorio en `speech_config` para modelo de audio nativo
- **VAD servidor:** `disabled=True` (obligatorio para puentes de telefonía)
- **Greeting:** `await session.send_client_content(turns=..., turn_complete=True)`
- **Firma audio SDK 2.7.0:**
  `await session.send_realtime_input(audio=types.Blob(data=..., mime_type='audio/pcm;rate=16000'))`

#### 4.1.1. DEUDA TÉCNICA — Migración gemini-2.5-flash → gemini-3.5-flash

**Origen:** detectado en S001-H10 (2026-06-30) al construir
`GeminiVisionExtractionService`. Verificado en línea: los plazos de
retirada de Gemini 2.5 Pro, Gemini 2.5 Flash-Lite y Gemini 2.5 Flash
en Vertex AI/Gemini Enterprise Agent Platform están fijados al
**16 de octubre de 2026**, con bloqueo de acceso nuevo a inferencia
online aproximadamente un mes antes (~16 de septiembre de 2026).

**Decisión adoptada:** todo código NUEVO usa `gemini-3.5-flash` desde
esta fecha (directriz 4.1 actualizada). El código EXISTENTE que usa
`gemini-2.5-flash` (texto/visión, no Live API) se mantiene sin tocar
por ahora — no se aborda dentro de S001-H10 para no desviar la sesión
— pero **debe migrarse antes del 16 de septiembre de 2026**.

**Puntos confirmados con `gemini-2.5-flash` pendientes de migración**
(lista parcial, basada en archivos descargados durante S001-H10 —
**requiere auditoría completa** del resto de módulos antes de
considerarse exhaustiva):

- `work_order_processor/services.py` — constante `_GEMINI_MODEL =
  "gemini-2.5-flash"`, usada por `extract_work_order_page()`
  (Gemini Vision, extracción de partes PDF históricos) y
  `classify_fault()` (clasificación de avería, solo texto).

**Fuera de alcance de esta deuda técnica:** `gemini-live-2.5-flash-
native-audio` (Live API, voz/IVR) tiene su propio ciclo de vida y
requiere verificación específica de Live API antes de decidir
sustituto — no se asume equivalencia automática con
`gemini-3.5-flash`.

**Acción pendiente:** sesión dedicada (o bloque de sesión) antes de
mediados de septiembre 2026 para: (1) auditar todo el proyecto en
busca de referencias a `gemini-2.5-flash` y `gemini-2.5-pro` no
detectadas todavía, (2) migrar cada constante de modelo a
`gemini-3.5-flash`, (3) validar que el formato de respuesta y
comportamiento no cambian de forma incompatible entre versiones de
modelo antes de desplegar a producción.

#### 4.2. Telefonía

- **Twilio SDK Python:** `twilio 9.10.4`
- **Autenticación Twilio:** API Key (TWILIO_API_KEY_SID + TWILIO_API_KEY_SECRET)
- **Transcodificación:** mu-law 8kHz ↔ PCM 16kHz ↔ PCM 24kHz via `audioop`
- **streamSid:** OBLIGATORIO en nivel raíz de cada mensaje `media` saliente

#### 4.3. Infraestructura y Framework

- **Framework:** Django `5.2.12`
- **Servidor async:** aiohttp `3.13.5` — puerto `8081`
- **Túnel:** ngrok v3 — API local en puerto `4041`
- **Entorno:** PythonAnywhere WSGI — Python `3.10.5`
- **Entorno virtual:** `EnterpriseBot_venv`
- **Base de datos:** MySQL — `MiguelAeTxio$enterprisebot`
- **Gestión de dependencias:** `pip-tools` (requirements.in → requirements.txt)
- **Log de acceso:** `/var/log/enterprisebot-miguelaetxio.pythonanywhere.com.access.log`
- **Log de errores:** `/var/log/enterprisebot-miguelaetxio.pythonanywhere.com.error.log`
- **Log de servidor:** `/var/log/enterprisebot-miguelaetxio.pythonanywhere.com.server.log`

#### 4.4. Requisito SINE QUA NON

Antes de entregar o implementar cualquier código que involucre servicios
externos o APIs, el modelo **DEBE** actualizarse en línea obligatoriamente
para usar datos actuales de implementación en lugar de datos obsoletos.

#### 4.5. DIRECTRIZ CRÍTICA — MIGRACIONES DJANGO

**[PROHIBICIÓN ABSOLUTA] EL MODELO JAMÁS GENERA MIGRACIONES MANUALMENTE**

Las migraciones de Django se generan **ÚNICA y EXCLUSIVAMENTE** mediante:

```bash
python -m dotenv run python manage.py makemigrations
```

**QUEDA TERMINANTEMENTE PROHIBIDO** escribir, crear, dictar o entregar
archivos de migración (`0XXX_*.py`) en ninguna caja de código, bajo
ninguna circunstancia, sin importar cuán obvia parezca la migración.

**Flujo estándar obligatorio e irrompible:**
1. El modelo modifica `models.py` mediante NEW-EDIT.
2. El usuario ejecuta `makemigrations` en su consola.
3. Django genera el archivo de migración automáticamente.
4. El usuario ejecuta `migrate` para aplicarla.

**Únicas excepciones permitidas** (requieren autorización explícita de
Miguel Ángel en el mismo prompt):
- Reparación de historial de migraciones corrupto.
- Uso de `--fake` o `--fake-initial`.
- Squash de migraciones.
- Cualquier otra operación excepcional sobre el historial de Django.

**Penalización:** Generar una migración sin autorización explícita es un
**ERROR CRÍTICO** de sesión. Sin excepciones. Sin urgencias que lo
justifiquen. Sin ningún pretexto.

#### 4.6. DIRECTRIZ CRÍTICA — Section.ivr_breakdown_enabled

`Section.ivr_breakdown_enabled` controla ÚNICA Y EXCLUSIVAMENTE si esa
sección aparece en el `section_callflow_map` para enrutar llamantes
**EXTERNOS** al flujo IVR de esa sección. No interviene en ningún otro
mecanismo del sistema.

**Para detectar que una llamada o mensaje es una avería interna, la ÚNICA
condición necesaria y suficiente es:**

```python
Contact.objects.filter(company=company, phone_number=caller_number).first()
```

**QUEDA TERMINANTEMENTE PROHIBIDO** condicionar cualquier lógica de averías
(perfil Alia, greeting personalizado, creación de BreakdownTicket, agente WA)
a que exista `breakdown_context`, a que `breakdown_section_pks` tenga
elementos, o a que alguna sección tenga `ivr_breakdown_enabled=True`.
Esas flags son irrelevantes para el flujo de averías internas.
