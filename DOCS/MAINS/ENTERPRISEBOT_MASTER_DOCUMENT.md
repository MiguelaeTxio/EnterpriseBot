# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ENTERPRISEBOT_MASTER_DOCUMENT.md
# Documento Maestro: Proyecto EnterpriseBot

---

### 1. Visión General del Proyecto

EnterpriseBot es una plataforma de gestión empresarial para Grupo Álvarez
(empresa de grúas/maquinaria pesada). Nació como una solución omnicanal de
IA conversacional en tiempo real (voz IVR + WhatsApp) y ha crecido hasta
cubrir el ciclo completo de operación de taller: partes de trabajo
digitales, almacén de repuestos, albaranes de proveedor y cliente, gestión
de flota/centros de gasto, presupuestos (sección ASISTENCIA), analítica
cruzada de costes, documentación oficial de máquinas y (desde H24)
vacaciones/calendario de personal. La capa de IA conversacional (voz +
WhatsApp) sigue activa y en producción, pero ya es una parte más de la
plataforma, no su totalidad — **corregido en esta sección el 2026-07-14
(S018), a petición de Miguel Ángel, porque describía solo el alcance
original y llevaba desactualizada varios hitos.**

#### 1.1. Mapa de apps Django (INSTALLED_APPS real, `enterprise_core/settings.py`)

Referencia rápida para no tener que indagar el árbol de código en cada
sesión — actualizar esta lista cada vez que se instale o retire una app:

| App | Qué hace |
|---|---|
| `ai_services` | Cliente Gemini compartido, transversal a otras apps (principio DRY, H10). |
| `vox_bridge` | Puente de voz principal: Twilio Media Streams ↔ Gemini Live (transcodificación mu-law/A-law ↔ PCM). |
| `ivr_config` | Motor de configuración IVR multiempresa: `Company`, `CompanyUser`, `Section`, `Contact`, `CallFlow`, `PhoneNumber`, `PresenceStatus`, `AbsenceCategory`, etc. Núcleo de datos multiempresa del que dependen casi todas las demás apps. |
| `panel` | Panel de administración/operación (vistas, sin modelos propios salvo `AnalyticsProfile`). Tras el split de H21: `views_operator.py`, `views_workorders.py`, `views_fleet.py`, `views_ivr.py`, `views_auth.py`. |
| `whatsapp` | Canal WhatsApp: `WhatsAppSession`, `WhatsAppMessage`, `WhatsAppTemplate` — chatbot conversacional y sistema de presencia (H4). |
| `work_order_processor` | Pipeline completo de partes de trabajo: `WorkOrder`, `WorkOrderEntry`, `WorkdayGap` — extracción PDF→Excel (H6/H8), entrada digital Form/STT/Upload (H7), gates de integridad de jornada (Gate 1-4). |
| `fleet` | Flota / centros de gasto: `MachineAsset` (entidad central de centro de gasto, H12), `MaintenanceLog`, `MaintenanceItem`. |
| `spare_parts` | Almacén de repuestos y albaranes de proveedor vía Gemini Vision (H10), persistencia en Google Drive (`gdrive_service.py`, patrón reutilizado por H7/H23). |
| `workorder_spare_parts` | Puente entre partes de trabajo digitales y almacén de repuestos (H10, Paso 4). |
| `chat` | Salas de chat IRC por sección (H13) + sala especial BREAKDOWNS con agente Gemini y ciclo de vida de `BreakdownTicket` (H14). |
| `budgets` | Motor de presupuestos de la sección ASISTENCIA: `Insurer`, `VehicleType`, `InsurerTariff`, `TariffLine`, `Budget`, `BudgetLine` (H16). |
| `analytics` | Laboratorio de Análisis Unificado — sustituye a Gráficas/Analítica CdG/Informes, gráficas vía Apache ECharts (H20). |
| `history` | Visor de Historial de Máquinas de solo lectura para rol WORKSHOP (H22), incluye galería de fotos (H7) y sección de documentación (H23). |
| `delivery_notes` | CRUD de administración de albaranes de proveedor (gap detectado 2026-07-08). |
| `machine_documents` | Documentación oficial de centros de gasto vía Gemini Vision + Drive (H23, en curso). |
| `hr_calendar` | Vacaciones y calendario de operario/chófer (H24). |
| `personal_documents` | Documentación oficial de personal vía Gemini Vision + GCS (H25, en curso). |

**Fuera de `INSTALLED_APPS`, scripts auxiliares independientes** (no Django
apps, no se cargan en el proyecto): `file_organizer/organizer_probe.py`
(evaluación de Power Automate, H15) y `web_scrapping/scrape_toll_pdfs.py`
(scraping de PDFs de peajes para el cálculo de rutas, H18).

`enterprise_core/` es el paquete de configuración raíz del proyecto Django
(`settings.py`, `urls.py`, `asgi.py`/`wsgi.py`, `celery.py`) — no es una
app de dominio.

---

### 2. Arquitectura Técnica (Pivotaje Estratégico a Multimodal Live API)

- **Entorno Virtual:** EnterpriseBot_venv (Python 3.10)
- **Framework Base:** Django (Configurado para gestión de WebSockets y tareas asíncronas)
- **Motor de IA (ESTÁNDAR OBLIGATORIO):** `gemini-live-2.5-flash-native-audio`
  vía Vertex AI (Live API). Migrado desde `gemini-3.1-flash-live-preview`
  el 2026-04-05 — GA en Vertex AI, sin degradación observada en la
  generación de audio (ver `vox_bridge/services.py` para el detalle
  técnico de la migración). Corregido en esta sección el 2026-07-14
  (S018) para que sea coherente con la directriz 4.1, que ya reflejaba el
  modelo correcto.
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

#### Hito 23: Documentación de Centros de Gasto
(Ver anexo `ENTERPRISEBOT_ATTACHED_MILESTONE_V23.md`)
- Ingesta de documentación de máquina/centro de gasto desde una carpeta
  seleccionada por el usuario en la propia plataforma (subida web, no
  script de servidor).
- Clasificación automática de cada documento vía Gemini Vision, sin lista
  cerrada de categorías previas.
- Detección de documento maestro (combinado) frente a sus componentes
  individuales, y reconciliación: si la suma de individuales cubre el
  maestro, el maestro no se persiste; si falta algún documento presente en
  el maestro, se extrae de él.
- Persistencia exclusiva de los documentos individuales en Google Drive,
  con registro en BD (nuevo modelo, ORM) vinculado al MachineAsset
  correspondiente, con nombres coherentes tanto en BD como en Drive.
- Nueva sección "Documentación Centros de Gasto" en Administración: listado
  y recuperación rápida sin que el usuario necesite saber dónde está
  guardado cada archivo.

#### Hito 24: Vacaciones y Calendario
(Ver anexo `ENTERPRISEBOT_ATTACHED_MILESTONE_V24.md`)
- Generación automática de tarea de vacaciones (bloque de ausencia, centro
  de gasto PERSONAL, categoría VACATION) en la última jornada laboral
  antes del periodo vacacional del operario/chófer.
- Reutiliza infraestructura ya existente de H7/H10: `MachineAsset` PERSONAL
  y catálogo `AbsenceCategory` (código VACATION ya presente en el seed).
- Aplicación de calendario con código de colores por día (trabajado,
  vacaciones, baja, ausencia no justificada, festivo), visible para todos
  los roles autenticados, con filtro por operario/chófer para
  ADMIN/SUPERVISOR y vista propia sin selector para WORKSHOP/DRIVER.

#### Hito 25: Documentación de Personal
(Ver anexo `ENTERPRISEBOT_ATTACHED_MILESTONE_V25.md`)
- Ingesta y clasificación de documentación oficial de cada trabajador/
  chófer (identidad, contractual, carnets/permisos con vigencia,
  reconocimientos médicos, cursos de formación, EPIS, etc.) vía Gemini
  Vision, siguiendo el mismo principio de "servidor de archivos" ya
  aplicado en H23: el usuario nunca gestiona carpetas, solo indica qué
  documentación sube o necesita y el sistema la organiza.
- Modelo y app Django propios, separados de `machine_documents` (H23) —
  decisión explícita de modularidad de Miguel Ángel en S022, coherente
  con la directriz arquitectónica de H22.
- Persistencia en Google Cloud Storage (bucket
  `enterprisebot-alvarez-personnel-documents`), dentro de la misma
  migración fuera de Google Drive que afecta a H7/H10/H23.
- Vigencia explícita cuando el propio documento la indica (ej.
  reconocimiento médico con validez anual, calculada desde la fecha real
  del examen); calculada solo cuando no hay ninguna referencia explícita
  en el documento — decisión de Miguel Ángel en S022.
- Origen: carpeta de ejemplo real de un trabajador (chófer) aportada por
  Miguel Ángel en S022 como caso de estudio — ver anexo para el análisis
  completo de la estructura de documentos real.

#### Hito 26: Infraestructura Documental Compartida (Alertas, PDF, Email, Sustitución)
(Ver anexo `ENTERPRISEBOT_ATTACHED_MILESTONE_V26.md`)
- Servicio transversal (mismo patrón que `ai_services`/
  `spare_parts/gcs_service.py`), consumido tanto por la interfaz de
  Administración de documentación de centros de gasto (H23) como por
  la de documentación de personal (H25) — nunca duplicado entre las
  dos, decisión explícita de Miguel Ángel en S022 para evitar el
  patrón de la taxonomía de averías duplicada en cuatro sitios.
- Motor de alertas de vencimiento de documentos.
- Fusión/generación de PDF bajo demanda: dossier de documentos
  agrupados en un único PDF para adjuntar a un correo.
- Generación de plantilla de texto de correo (asunto + cuerpo) para
  copiar y pegar en el cliente de correo del usuario — nunca envío
  automático, no hay integración SMTP/API de email en el alcance de
  este hito.
- Diálogo de sustitución de documentos: al subir un documento del
  mismo tipo que uno ya existente, compara fechas y ofrece archivar
  el obsoleto y dejar el nuevo como vigente, o revertir la subida y
  anular el nuevo documento.
- Interfaces de Administración completas (subida, borrado,
  sustitución, alertas) para centros de gasto y personal se
  construyen sobre este servicio, no antes — decisión de Miguel Ángel
  en S022 (Opción B, frente a construirlo dos veces por dominio).

#### Hito 27: Ingesta de Documentación vía Correo Electrónico
(Ver anexo `ENTERPRISEBOT_ATTACHED_MILESTONE_V27.md`)
- Hito nuevo, abierto en S024 a petición explícita de Miguel Ángel
  durante la planificación de la interfaz de H23 — decidido como hito
  independiente (no colgado de H23) por su peso propio: alta de una
  cuenta de correo dedicada, integración con la API de lectura de esa
  cuenta, y clasificación de los documentos que lleguen como adjunto.
- Reutiliza el servicio de clasificación Gemini Vision ya construido
  en H23/H26 (mismo principio DRY que evita duplicar el motor de
  clasificación entre vías de entrada) en vez de duplicarlo.
- Premisa explícita de Miguel Ángel para la implementación: máxima
  modularización — evitar archivos grandes que mezclen
  responsabilidades, para no penalizar la escalabilidad futura.

#### Hito 28: Migración y Reorganización de Documentación Histórica
(Ver anexo `ENTERPRISEBOT_ATTACHED_MILESTONE_V28.md`)
- Hito nuevo, abierto en S030 a petición explícita de Miguel Ángel:
  "vamos a cambiar radicalmente el tema de la documentación, tanto de
  personal como de la maquinaria" — decidido como hito independiente
  (no colgado de H23/H25) porque precede y condiciona a ambos: mientras
  la documentación histórica real (OneDrive/Microsoft 365, carpetas
  `DOC. MAQUINAS`, `DOC. PERSONAL` y otras hermanas bajo `DOCUMENTOS
  GRUPO ALVAREZ`) siga sin migrar y sin limpiar, cualquier prueba real
  de H23/H25 sigue partiendo de datos "de la selva" (carpetas vacías,
  duplicados, dosieres redundantes, nombres inconsistentes entre
  versiones del mismo documento).
- Motivo explícito de Miguel Ángel: "eliminar la selva... quiero
  reorganizarlo todo, los archivos que sean iguales quitarlos, los
  dosieres que ya tienen partes en el archivo, eliminarlos... y dejar
  un directorio limpio, sin carpetas vacías, sin archivos duplicados,
  sin archivos redundantes."
- **No toca** la ingesta ya construida de partes de trabajo ni de
  albaranes/repuestos — explícitamente fuera de alcance ("eso no se
  toca, eso va a seguir exactamente igual").
- Tres fases, secuenciales, cada una condición de la siguiente:
  1. **Copia** — agente residente en Windows, sube en bruto (estructura
     tal cual, con toda la suciedad real) a un cubo de GCS dedicado
     ("cubo sucio", separado de los cubos de producción de H23/H25).
  2. **Clasificación** — herramienta exclusiva para Miguel Ángel:
     explorador de archivos en la nube con clasificación asistida por
     Gemini + heurística, detección de duplicados, limpieza de carpetas
     vacías y dosieres redundantes, hasta dejar el árbol coherente y
     con nombres de archivo estables tanto para máquina como para
     humano.
  3. **Despachador** — interfaz de servidor de archivos para el resto
     de usuarios (subida/descarga ordenada), construida solo cuando la
     Fase 2 ya ha dejado el árbol limpio -- nunca antes.
- Detalle técnico completo, incluidas las cuatro decisiones de diseño
  de la Fase 1 y la hoja de ruta ejecutable, en el anexo H28.

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

#### 4.5. DIRECTRIZ CRÍTICA — MIGRACIONES DJANGO (REESCRITA EN S014, 2026-07-13)

**Flujo vigente desde S014, decisión explícita y final de Miguel
Ángel, sustituye por completo la directriz anterior ("el modelo jamás
genera migraciones"):**

1. El modelo modifica `models.py`.
2. **El modelo genera también el archivo de migración
   (`0XXX_*.py`)**, escrito directamente en el mismo commit que el
   cambio de modelo -- replicando el formato real que Django genera
   en este proyecto (ver migraciones ya existentes como referencia de
   estilo: `verbose_name`/`help_text` conservados, mismo patrón de
   `UniqueConstraint`/`condition` que las constraints ya aplicadas).
3. El modelo hace `commit` + `push` de `models.py` y del archivo de
   migración juntos. El push dispara el despliegue automático
   (`.github/workflows/deploy.yml`): `git pull` + `migrate --noinput`
   + `collectstatic` + reload, sin intervención de Miguel Ángel.
4. Si el build/despliegue falla (visible en GitHub → Actions), el
   modelo diagnostica sobre esa salida real y corrige con un commit
   nuevo -- mismo principio empírico de siempre, nunca a ciegas.

**Motivo del cambio:** Miguel Ángel valora más la velocidad y el
ahorro de tokens de no ejecutar un ciclo manual de
`makemigrations`/descarga/análisis en cada cambio de modelo, que la
red de seguridad que ese ciclo aportaba. Decisión suya, informada,
tomada en S014 tras planteársele el riesgo -- ver
`com-migrations` sección 6.0 para el detalle completo y la fecha.

**Sigue aplicando sin cambios**, porque es un límite técnico, no de
política: el modelo no tiene ninguna ruta de red hacia PythonAnywhere
ni hacia la BD MySQL real (verificado empíricamente en S014, ver
`com-migrations`) -- por tanto nunca ejecuta él mismo
`makemigrations`/`migrate`, solo escribe los archivos de código
(modelo + migración) que luego GitHub Actions aplica por su cuenta.

**Únicas excepciones que siguen requiriendo intervención manual de
Miguel Ángel en su propia consola** (reparación de historial de
migraciones corrupto, `--fake`/`--fake-initial`, squash, o cualquier
operación excepcional sobre el historial de Django): estos casos
dependen de introspección real del estado de la BD/tabla
`django_migrations` que el modelo no puede ver, y siguen el ciclo
manual completo de `com-migrations` sección 3.

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

#### 4.7. DEUDA TÉCNICA — Reparto de gastos generales de PERSONAL entre centros de gasto

**Origen:** detectado en S018 (2026-07-14), a raíz de una pregunta abierta
de H24 (calendario de vacaciones) sobre si las horas de ausencia por
`PERSONAL` deben excluirse de los cómputos de horas/coste. Miguel Ángel
aclaró el criterio de negocio completo y pidió dejarlo anotado sin
implementar por ahora.

**Comportamiento actual, verificado en código (H20, `analytics/views.py`,
nota de diseño S010 2026-07-09, ya acordada con Miguel Ángel):** el coste
de un operario se reparte proporcionalmente entre todos los centros de
gasto en los que registró horas ese periodo — `PERSONAL` y `EMPRESA_ALMACEN_*`
entran en ese reparto exactamente igual que una máquina real, sin caso
especial. Es decir, `PERSONAL` recibe su propia fracción de coste y
aparece como su propia fila en el cruce de Analítica — **ese coste no se
redistribuye después sobre el resto de centros de gasto.**

**Comportamiento deseado (criterio de negocio de Miguel Ángel, S018):**
el gasto laboral que cae en `PERSONAL` (vacaciones, bajas, etc. — el
coste de pagar a un operario mientras no repara ninguna máquina) es en
realidad un sobrecoste de estructura que debe **repercutirse entre
todos los demás centros de gasto** (máquinas + `EMPRESA_ALMACEN_*`/
dependencias), no quedarse aparcado en su propia fila. Es el mismo
principio que aplicará el día que se reparta el gasto de administración
general: un sobrecoste que no es imputable a ningún centro de gasto
concreto se divide entre todos los demás.

**Excepción explícita:** `PERSONAL` nunca se repercute a sí mismo — el
reparto es entre el resto de centros de gasto, excluyendo `PERSONAL`.

**Acción pendiente:** ninguna por ahora — **Miguel Ángel ha pedido
explícitamente no entrar en esto todavía.** Cuando se aborde, requiere
diseñar el mecanismo de reparto (¿proporcional a horas de cada centro de
gasto en el periodo? ¿a partes iguales?) con Miguel Ángel antes de tocar
`analytics/views.py`.

**Relacionado, pero distinto — no confundir:** la hora fantasma de
`VACATION` (1h, tarea automática de H24) no forma parte de esta deuda.
Esa hora concreta nunca debe contabilizar en ningún sitio (ni siquiera
como coste de `PERSONAL`) — ver `ENTERPRISEBOT_ATTACHED_MILESTONE_V24.md`
sección 3.1. Las horas reales de los días de vacaciones sí generan coste
en `PERSONAL`, y ESE coste es el que algún día se repercutirá según esta
deuda técnica.

#### 4.8. DIRECTRIZ CRÍTICA — Fidelidad absoluta a las instrucciones explícitas de Miguel Ángel (añadida S019, 2026-07-15)

**Regla, sin excepción:** cuando Miguel Ángel especifica un flujo, diseño
o comportamiento de forma explícita, el modelo lo implementa TAL CUAL lo
ha dicho — sin reinterpretarlo, sin "mejorarlo" y sin sustituirlo por un
diseño alternativo que al modelo le parezca más elegante, más robusto o
más completo. Si algo no se entiende, o el modelo cree que se podría
plantear de otra forma, se **pregunta antes de implementar** — nunca se
decide unilateralmente y se sigue adelante dando por hecho que la
interpretación propia es válida. Mientras Miguel Ángel no diga lo
contrario, se hace única y exclusivamente lo que él ha dicho.

Cualquier instrucción explícita de flujo/diseño que dé Miguel Ángel debe
quedar plasmada **tal cual** en el anexo del hito correspondiente — nunca
una reinterpretación del modelo, nunca una versión "probablemente" o
"candidato natural" inventada para rellenar un hueco de especificación.
Si una sesión anterior dejó una decisión sin cerrar (marcada como
pregunta abierta, "a confirmar", "probablemente", etc.), la sesión que la
retome debe **preguntar a Miguel Ángel antes de construir nada sobre
ella**, no asumir la interpretación que le resulte más natural y darla
por buena.

**Origen — incidente S019 (H24):** el anexo `ENTERPRISEBOT_ATTACHED_MILESTONE_V24.md`
(escrito en S018) dejaba anotado, sin cerrar del todo ("probablemente"),
que la tarea automática de vacaciones se dispararía "desde el alta/
edición de un periodo de vacaciones en el nuevo módulo de calendario".
La sesión S019 tomó esa nota como decisión cerrada y construyó un CRUD de
panel completo (`hr_calendar/views.py`, formulario de alta/edición) bajo
la premisa de que un ADMIN/SUPERVISOR registra el periodo y de ahí se
genera la tarea. Miguel Ángel corrigió en S019: el flujo real es el
inverso — **el propio operario añade su tarea de vacaciones (1 hora,
centro de gasto PERSONAL) en su parte digital normal, en su última
jornada laboral, indicando ahí mismo la fecha de fin de su periodo; de
esa tarea real se deriva el `VacationPeriod`, nunca al revés.** El CRUD
de panel no es lo que él pidió y no debía haberse construido sin
confirmárselo primero explícitamente.

#### 4.9. DIRECTRIZ CRÍTICA — Ningún hallazgo real se deja como deuda técnica sin reparar (añadida S019, ampliada S024)

**Regla, sin excepción:** si durante una sesión se detecta un error real
en el código — aunque no pertenezca al hito o tarea en curso, y aunque
no se haya introducido en la sesión actual — se corrige de inmediato en
la misma sesión. Nunca se deja anotado como "deuda técnica" o "fuera de
alcance" a la espera de confirmación. Al cierre de sesión (PCS) se
documenta en el anexo correspondiente al hito donde vivía el error (no
en el anexo del hito que se estaba trabajando, salvo que coincidan).

**Ampliación S024, a petición explícita de Miguel Ángel:** esta regla
cubre también los avisos de linter no bloqueantes — aquellos que no
impiden el funcionamiento del script (ej. estilos inline en HTML,
avisos de formato) — no solo errores que rompen la ejecución. Si al
pasar el linter sobre un archivo tocado en la sesión aparece un aviso
de este tipo, se repara igualmente en la misma sesión, sin dejarlo
anotado para más adelante, exista o no relación con la tarea en curso.

**Origen:** incidente S019 — el modelo detectó que el patrón de mostrar
`{exc}` (texto crudo de excepción) directamente en mensajes de usuario
existía ya en varios archivos de producción desplegados
(`panel/views_operator.py`, `panel/views_workorders.py`,
`budgets/views.py`) y, en vez de corregirlo, lo dejó anotado
preguntando si abordarlo como tarea aparte — corregido por instrucción
explícita de Miguel Ángel. Ampliada en S024 durante la planificación de
H23/H27, cuando Miguel Ángel extendió explícitamente el mismo criterio
a los avisos de linter no bloqueantes.

