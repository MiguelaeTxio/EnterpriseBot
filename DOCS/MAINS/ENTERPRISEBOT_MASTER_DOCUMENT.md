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
| `panel` | Panel de administración/operación (vistas, sin modelos propios salvo `AnalyticsProfile`). Módulos de vistas reales, verificados contra el árbol en S037: `views.py`, `views_operator.py`, `views_workorders.py`, `views_ivr.py`, `views_auth.py`, `views_documentation.py`, `views_task_photos.py`, `views_gdrive_setup.py`. **`views_fleet.py` no existe** en el árbol y ningún módulo lo referencia — el mapa lo listaba por error hasta S037. |
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
| `machine_documents` | Documentación oficial de centros de gasto vía Gemini Vision + GCS (H23). |
| `hr_calendar` | Vacaciones y calendario de operario/chófer (H24). |
| `personal_documents` | Documentación oficial de personal vía Gemini Vision + GCS (H25). |
| `document_ingestion` | Ingesta de documentación y enrutado (H23/H25, S024): `IngestedFile` — staging de un archivo subido antes de saber a qué dominio y entidad pertenece — y `LearnedDocumentTypeKeyword`. Incluye `entity_matching_service.py` y la tarea periódica `self_heal_unassigned_personal_documents`. **Ausente de este mapa hasta S037.** |
| `document_management` | Infraestructura Documental Compartida (H26): `EmailTemplate`, `DocumentAlert`, `DocumentSubstitutionLog`. Aquí vive la tarea periódica `send_document_expiry_alerts`. **Ausente de este mapa hasta S037.** |

**Fuera de `INSTALLED_APPS`, scripts auxiliares independientes** (no Django
apps, no se cargan en el proyecto): `file_organizer/organizer_probe.py`
(evaluación de Power Automate, H15) y `web_scrapping/scrape_toll_pdfs.py`
(scraping de PDFs de peajes para el cálculo de rutas, H18).

`enterprise_core/` es el paquete de configuración raíz del proyecto Django
(`settings.py`, `urls.py`, `asgi.py`/`wsgi.py`, `celery.py`) — no es una
app de dominio.

---

### 2. Arquitectura Técnica (Pivotaje Estratégico a Multimodal Live API)

- **Entorno Virtual:** EnterpriseBot_venv_py312 (Python 3.12.8 --
  migrado desde EnterpriseBot_venv/Python 3.10 en H32/S93, corregido
  aquí en S94)
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

#### Hito 29: Explorador de Archivos y Gobierno Documental del Panel sobre Google Cloud Storage
(Ver anexo `ENTERPRISEBOT_ATTACHED_MILESTONE_V29.md`)
- Hito nuevo, abierto en S037 por decisión explícita de Miguel Ángel al
  plantearse si un explorador de GCS en el panel pertenecía a H28
  ("Migración y Reorganización de Documentación Histórica") o merecía
  hito propio: es infraestructura de plataforma, no migración, y se
  abre separado.
- Explorador de archivos en el panel servido **exclusivamente desde una
  tabla de índice en base de datos**. Navegar, listar y buscar nunca
  tocan Google Cloud Storage; solo la visualización del contenido de un
  documento concreto accede al objeto real.
- Alcance del índice: el prefijo de cuarentena y el resto del cubo
  `cgs_grupo_alvarez`, más los cubos propios de la plataforma
  (`...-machine-documents`, `...-personnel-documents`,
  `...-delivery-notes`, `...-task-photos`).
- Modelo de permisos en base de datos, no en IAM de Google Cloud:
  recursivos desde cualquier carpeta, por cubo y por sección, porque lo
  que se concede es acceso a una parte de la tabla.
- Borrado en dos niveles: lógico a papelera propia de cada usuario
  (recuperable solo por su dueño) y borrado real reservado al
  administrador.
- **Un borrado en local nunca se refleja como desaparición en la nube.**
  El único reflejo que se toma del sistema de archivos local es una
  bandera de existencia por fila.
- Objetivo de fondo, en palabras de Miguel Ángel: blindar el
  mantenimiento del directorio documental en Google Cloud Storage y
  evitar la selva de nombres, los borrados accidentales y los archivos
  mal nombrados o mal ubicados, canalizando toda la gestión por el
  panel.

#### Hito 30: Vinculación Documental Real — Centros de Gasto y Personal con Referencia Viva a su Documentación
(Ver anexo `ENTERPRISEBOT_ATTACHED_MILESTONE_V30.md`)
- Hito nuevo, abierto en S043 por decisión explícita de Miguel Ángel:
  "creo que esto es una tarea de gran calado" -- una vez `fleet.
  MachineAsset` y `document_explorer.PersonIdentity` quedan al día
  (auditoría S043, Excel real de plantilla y maquinaria), la base de
  datos deja de ser solo un catálogo de identidad y pasa a necesitar
  una referencia real y viva a la documentación de cada máquina y cada
  persona, que se actualice sola cuando el índice virtual cambie
  (mover, renombrar, sustituir, borrar).
- Sustitución automática por tipo de documento (una ITV nueva marca la
  anterior como obsoleta y deja la nueva como vigente, sin preguntar)
  -- reconstruye o adapta la lógica ya construida en H26
  (`document_management.DocumentSubstitutionLog`/`vigencia_service`),
  hoy enganchada al modelo legado de `machine_documents`, nunca al
  `DocumentIndexEntry` unificado de H29.
- Punto de enlace explícito con la decisión 3.12 de H29 (consolidación
  de cubos, aplazada hasta cerrar la clasificación automática):
  Miguel Ángel, verbatim, S043: "la interfaz y entrada para gestionar
  la documentación será la que teníamos... ya hemos llegado al punto
  de ligar lo anterior con lo nuevo" -- las interfaces de
  administración de H23/H25/H26 (subida, sustitución, alertas) se
  ligan ahora al `DocumentIndexEntry` real, no a los modelos legados.
- Organización de manuales (un manual por modelo de máquina, punto ya
  registrado en H29 3.21/3.22) como paso previo o paralelo, a decidir
  en la primera sesión de este hito.

#### Hito 31: Interfaz de Ficha de Personal — EPIs y Notificaciones/Circulares
(Ver anexo `ENTERPRISEBOT_ATTACHED_MILESTONE_V31.md`)
- Hito nuevo, abierto en S73 por decisión explícita de Miguel Ángel:
  una vez cerrado el bloque EPIs de H30 (vinculación documental real),
  hace falta la interfaz que permita ENTREGAR EPIs y ENVIAR
  notificaciones/circulares de verdad desde el panel, no solo
  consultar el histórico ya migrado.
- Tres bloques funcionales, verbatim de Miguel Ángel (S73):
  1. **Ficha de persona editable**: datos personales con formulario,
     foto de carné (subir si no existe -- hay fotos de carné ya
     asignadas de sesiones anteriores, reutilizables).
  2. **EPIs y notificaciones desde la ficha de persona**: dos
     desplegables (uno para elegir el EPI a entregar, otro para la
     notificación a enviar), entrega/envío individual desde la propia
     ficha.
  3. **Entrega/envío masivo**: selector de personal con casillero
     (checkboxes), mismo criterio para EPIs (p. ej. entregar ropa a
     varios trabajadores a la vez) y para circulares (un envío a
     varios trabajadores deja de ser "notificación" individual y pasa
     a ser "circular").
- CRUD de circulares/notificaciones: crear, editar, importar (Word,
  PDF a convertir) y sustituir la plantilla vigente de un tipo. Editor
  de texto básico integrado (colores de fondo/carácter, selección
  entre pocas fuentes) -- explícitamente NO un editor avanzado tipo
  WordPerfect, la vía principal esperada es la importación de un
  documento ya existente.
- Reutiliza el mecanismo `DocumentTypeCatalog.current_template` (H30
  S69) ya en uso real para EPIs/nombramientos -- la circular editable
  encaja en el mismo patrón (plantilla vigente = un `DocumentIndexEntry`
  más).
- Diagnóstico de partida (S73): `PersonalDetailView`/`_personal_detail.html`
  y `EpiTabFragmentView`/`EpiResultsFragmentView` (`panel/
  views_documentation_h30.py`) ya existen pero son de SOLO LECTURA
  (listan persona/documentos/EPIs ya migrados, sin foto, sin acción de
  entrega). Base de lectura reutilizable; el resto (acciones de
  entrega/envío, CRUD de circulares, editor, importación, selector
  masivo) está por construir desde cero.

#### Hito 32: Migraciones de Infraestructura (Modelo IA, Python, Registro Android)
(Ver anexo `ENTERPRISEBOT_ATTACHED_MILESTONE_V32.md`)
- Hito nuevo, abierto en S92 por decisión explícita de Miguel Ángel:
  con el dominio PERSONAL de H30 fechado y asignado al 100%, tres
  plazos externos reales convergen en el mismo mes y merecen hito
  propio en vez de colarse como desvíos sueltos dentro de H30/H31.
- **Migración `gemini-2.5-flash` → `gemini-3.5-flash`** (deuda técnica
  ya registrada en la sección 4.1.1 de este documento): bloqueo de
  acceso a inferencia online nueva ~16 de septiembre de 2026, apagado
  total 16 de octubre de 2026. Requiere auditoría completa del
  proyecto primero (la lista de la sección 4.1.1 está marcada
  explícitamente como parcial), después migración de cada constante
  de modelo, y validación de que el formato de respuesta no cambia de
  forma incompatible antes de desplegar.
- **Migración de versión de Python en PythonAnywhere**: `google.api_core`
  deja de dar soporte a la versión actual (3.10) a partir del 4 de
  octubre de 2026 (correo real de Google/PythonAnywhere ya recibido).
- **Registro de apps Android en Google Play Console**: correo real de
  Google (recibido 2026-09-01) exige, desde el 30 de septiembre de
  2026, registrar nombre de paquete y firma con identidad de
  desarrollador verificada para instalarse en dispositivos
  certificados. Sin acción posible todavía -- aplica cuando exista una
  app real que publicar (la app nativa de albaranes para tablets de
  operarios sigue sin empezar); se deja como punto informativo del
  hito hasta que haya algo que registrar.
- Ver anexo `ENTERPRISEBOT_ATTACHED_MILESTONE_V32.md` para la hoja de
  ruta ejecutable.

#### Hito 33: Subida de Documentación en Tiempo Real desde el Panel
(Ver anexo `ENTERPRISEBOT_ATTACHED_MILESTONE_V33.md`)
- Hito nuevo, abierto en S94 por decisión explícita de Miguel Ángel:
  la vía de ingesta actual (agente local H28 + Always-on Task de
  cuarentena) no es inmediata -- un supervisor que deja documentación
  real en la carpeta vigilada (alta de un trabajador nuevo, o
  actualización de uno o más documentos de un trabajador ya existente)
  tiene que esperar al siguiente barrido de la tarea, inviable en una
  situación de producción real donde se necesita la documentación
  clasificada y en base de datos de inmediato.
- Objetivo: una vía de subida directa desde el propio panel (no la
  carpeta vigilada), con la MISMA clasificación real ya construida en
  H29/H30 (heurística + OCR + Gemini como último recurso), pero
  disparada al momento por el supervisor, sin esperar a ningún barrido
  periódico.
- Sin hoja de ruta ejecutable todavía -- pendiente de sesión de diseño
  dedicada (alcance exacto: solo personal, o también máquinas desde el
  principio; interfaz de subida por carpeta completa vs. archivo a
  archivo; qué pasa si la clasificación automática falla en el momento,
  no en un barrido posterior donde hay más margen).

#### Hito 34: Modelo Propio de Clasificación de Documentos (entrenamiento)
(Ver anexo `ENTERPRISEBOT_ATTACHED_MILESTONE_V34.md`)
- Hito nuevo, abierto en S94 por decisión explícita de Miguel Ángel,
  con máxima prioridad de atención propia -- verbatim: "vamos a sentar
  la base de la clasificación de documentos a raíz del entrenamiento
  de este modelo [...] no un punto de hoja de ruta dentro de otro
  hito."
- Objetivo: entrenar un modelo propio que sustituya a Gemini como
  clasificador principal de documentos -- empezando por el dominio
  PERSONAL (donde ya existe volumen suficiente tras el cierre de H30),
  con MAQUINARIA como extensión futura del mismo mecanismo. Gemini
  pasa a ser el último recurso (fallback), no la vía por defecto.
- Contexto real: un primer intento de entrenamiento anterior no
  disponía de datos suficientes para ser efectivo. Tras el cierre de
  H30 (dominio PERSONAL fechado y clasificado al 100%), sí existe ya
  un dataset real de volumen considerable, sobre todo en los tipos
  documentales de gran volumen (los de poco volumen, plantillas y
  documentos ya reducidos, siguen siendo discriminables por heurística
  sin necesidad de modelo).
- Sin hoja de ruta ejecutable todavía -- pendiente de sesión de diseño
  dedicada (arquitectura del modelo, formato/tamaño real del dataset
  de entrenamiento extraíble de la BD ya clasificada, criterio de
  validación antes de sustituir a Gemini en producción, mecanismo de
  fallback cuando el modelo propio no tenga confianza suficiente).

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

⛔ **CERRADA en H32/S93 (2026-09-07).** Auditoría completa del
proyecto y migración de las 5 líneas de código real encontradas,
verificado que ninguna usa segmentación de imagen ni `candidate_count`
(incompatibles con Gemini 3.x). Detalle completo, comandos y commits
en `ENTERPRISEBOT_ATTACHED_MILESTONE_V32.md`, sección "COMPLETADAS EN
S93". Sección conservada aquí como registro histórico de la deuda y
su origen -- el texto original de abajo describe el estado en el
momento en que se detectó (S001-H10), no el estado actual.

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
`gemini-3.5-flash`. Ver sección 4.1.2 para el seguimiento de ese
modelo, abierto en H32/S93.

**Acción pendiente:** ~~sesión dedicada (o bloque de sesión) antes de
mediados de septiembre 2026 para: (1) auditar todo el proyecto en
busca de referencias a `gemini-2.5-flash` y `gemini-2.5-pro` no
detectadas todavía, (2) migrar cada constante de modelo a
`gemini-3.5-flash`, (3) validar que el formato de respuesta y
comportamiento no cambian de forma incompatible entre versiones de
modelo antes de desplegar a producción.~~ Completado en H32/S93, ver
nota de cierre arriba.

#### 4.1.2. SEGUIMIENTO -- Ciclo de vida de `gemini-live-2.5-flash-native-audio` (Live API, voz)

**Abierto en H32/S93 (2026-09-07), a petición explícita de Miguel
Ángel: "adelantarnos a la situación... que no nos pille confesados."**
Verificado en línea (`ai.google.dev/gemini-api/docs/deprecations`,
changelog de Gemini API): **el modelo GA en uso,
`gemini-live-2.5-flash-native-audio`, todavía no tiene fecha de
apagado anunciada** -- esto no es una deuda técnica todavía, es un
punto de vigilancia.

**Señal real de hacia dónde va esto (no es una fecha, es una
tendencia):**
- Los modelos Live anteriores ya siguieron este patrón y ya se
  apagaron: `gemini-2.0-flash-live-001` y `gemini-live-2.5-flash-
  preview` (el preview de la misma generación 2.5), ambos apagados el
  **9 de diciembre de 2025**.
- Google ya publicó el sucesor en preview: `gemini-3.1-flash-live-
  preview` (11 de marzo de 2026), marcado como reemplazo recomendado
  de la línea Live 2.5 en la tabla oficial de deprecaciones.
- El patrón observado en otros modelos de la familia (`gemini-2.5-
  flash`, `gemini-2.5-pro`, ver 4.1.1) es: preview del sucesor
  publicado con meses de antelación, luego anuncio formal de apagado
  del GA anterior, luego ventana de ~1 mes de bloqueo de inferencia
  nueva antes del apagado total. Si ese patrón se repite, cabe esperar
  un anuncio formal de apagado de `gemini-live-2.5-flash-native-audio`
  en algún momento tras marzo de 2026, pero **no hay fecha real
  todavía -- no inventar una**.

**Acción de seguimiento, sin urgencia todavía:** en cada sesión que
toque `vox_bridge/` o el bloque 4.1 de este documento, re-verificar en
línea (`ai.google.dev/gemini-api/docs/deprecations`, filtrar por
"Live API models") si ya hay fecha de apagado anunciada para
`gemini-live-2.5-flash-native-audio`. En cuanto aparezca una fecha
real, abrir hito o bloque de trabajo dedicado (mismo patrón que
H32/S93 para el modelo de texto/visión) -- no esperar a que falte un
mes, dado que una migración de Live API requiere validación de audio
en producción con llamadas reales, más lenta que una migración de
texto/visión.

**Migración NO trivial cuando llegue:** a diferencia de
`gemini-2.5-flash` → `gemini-3.5-flash` (mismo formato de respuesta
para texto/Vision, verificado en H32/S93), la Live API tiene su propio
protocolo de sesión (`session.send_realtime_input`, formato de audio,
configuración de voz `Aoede`, VAD del servidor) -- no asumir
compatibilidad automática con `gemini-3.1-flash-live-preview` ni con
ningún sucesor sin verificar explícitamente el protocolo de la nueva
versión contra `vox_bridge/services.py`.

- **Twilio SDK Python:** `twilio 9.10.4`
- **Autenticación Twilio:** API Key (TWILIO_API_KEY_SID + TWILIO_API_KEY_SECRET)
- **Transcodificación:** mu-law 8kHz ↔ PCM 16kHz ↔ PCM 24kHz via `audioop`
- **streamSid:** OBLIGATORIO en nivel raíz de cada mensaje `media` saliente

#### 4.3. Infraestructura y Framework

- **Framework:** Django `5.2.12`
- **Servidor async:** aiohttp `3.13.5` — puerto `8081`
- **Túnel:** ngrok v3 — API local en puerto `4041`
- **Entorno:** PythonAnywhere WSGI — Python `3.12.8` (imagen `innit`,
  migrado desde `3.10.5`/imagen `haggis` en H32/S93)
- **Entorno virtual:** `EnterpriseBot_venv_py312` (corregido S94 --
  ver `SESSION_VARIABLES.md`)
- **Base de datos:** MySQL — `MiguelAeTxio$enterprisebot`
- **Gestión de dependencias:** `pip-tools` (requirements.in → requirements.txt)
- **Log de acceso:** `/var/log/enterprisebot-miguelaetxio.pythonanywhere.com.access.log`
- **Log de errores:** `/var/log/enterprisebot-miguelaetxio.pythonanywhere.com.error.log`
- **Log de servidor:** `/var/log/enterprisebot-miguelaetxio.pythonanywhere.com.server.log`

#### 4.3.1. MIGRACIÓN DE PYTHON — CERRADA en H32/S93 (antes deuda técnica con fecha)

**CERRADA.** Migrado a Python 3.12.8 (venv `EnterpriseBot_venv_py312`,
imagen de sistema `innit`) antes del plazo. Ver
`ENTERPRISEBOT_ATTACHED_MILESTONE_V32.md` sección 3.1 para el detalle
completo de la ejecución (incidencia real de las tareas Always On,
comandos usados). Sección conservada aquí solo como referencia
histórica del origen y los plazos reales -- no queda ninguna acción
pendiente de este bloque.

**Origen:** el cliente `google-api-core` emite un `FutureWarning` en
cada invocación avisando de que Google dejará de dar soporte a Python
3.10 en las versiones nuevas de la librería cuando esa versión alcance
su fin de vida, el **4 de octubre de 2026**. Visible en la salida real
del servidor, capturada en S037 al verificar un `showmigrations`.

**Consultado al soporte de PythonAnywhere** (Miguel Ángel, 2026-07-22;
respuesta del equipo recibida y aportada en S037), con tres respuestas
concretas:

1. **No hay que esperar a nada.** Python 3.12 y 3.13 son
   seleccionables hoy para entornos virtuales nuevos. Referencia que
   dieron: `https://help.pythonanywhere.com/pages/InstallingNewModules`.
2. El procedimiento es crear un entorno virtual nuevo sobre la versión
   de destino (`mkvirtualenv ... --python=python3.13`), reinstalar allí
   las dependencias, cambiar la ruta del entorno virtual de la webapp
   en la pestaña *Web* y recargar.
3. **No hay ventana de caída:** el entorno virtual antiguo queda
   intacto y el cambio solo surte efecto al recargar.

**Detalle operativo completo en `com-environment-management` sección
4.2**, incluida la obligación de **recompilar el candado en el
intérprete nuevo** (un `requirements.txt` compilado bajo 3.10 no es
válido para 3.13, sección 3.4 de esa misma skill) -- **incidencia real
detectada en S94**: el candado regenerado en el servidor durante S93
nunca se comiteó (`requirements.txt` versionado siguió marcado "Python
3.10" hasta S94, mismo patrón de defecto encontrado en paralelo en
CampusStudiOnline), corregido en S94 (commit `01cdb93`).

El punto que quedaba pendiente de verificar antes de ejecutar la
migración -- si el comando de arranque de las tareas *always-on*
(worker de Celery `242133` y puente de voz `234987`) referenciaba el
entorno virtual -- se confirmó que sí, y ambos se actualizaron y
verificaron en producción durante S93 (ver anexo H32 sección 3.1,
incidencia real de contenedores Always On "pegados" al sistema de
archivos antiguo, resuelta borrando y recreando cada tarea).

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

#### 4.10. DIRECTRIZ CRÍTICA — Infraestructura Google Cloud SIEMPRE vía Cloud Shell / `gcloud`, nunca guiando paso a paso por los formularios de la consola web (añadida S031)

**Regla, sin excepción:** cualquier operación sobre recursos de Google
Cloud (buckets de GCS, cuentas de servicio, permisos IAM, y cualquier
otro recurso gestionable por `gcloud`) se hace siempre entregando a
Miguel Ángel comandos `gcloud`/`gcloud storage` completos y listos
para pegar en Cloud Shell — nunca describiendo paso a paso los clics,
menús y campos de la consola web para que Miguel Ángel los siga
manualmente, capture pantallas y el modelo las interprete una a una.

**Origen:** incidente S031 (creación de infraestructura GCP para H28
Fase 1) — guiar por la consola web generó una sesión larga y
frustrante de capturas de pantalla, interpretación visual y
confirmaciones, con un coste añadido crítico: el nombre de una cuenta
de servicio propuesto por el modelo excedía el límite de 30 caracteres
de GCP, la consola lo truncó **silenciosamente sin aviso visible**, y
el error no se detectó hasta varios pasos después, generando una
cascada de fallos que se llegaron a atribuir erróneamente a
propagación de IAM o a un bug de la consola. Con `gcloud` directo, el
mismo error (`ERROR: ... does not exist` o el propio nombre truncado
en la salida del comando `create`) se habría detectado de inmediato,
en el primer comando, con datos exactos en texto plano en vez de
interpretación visual de capturas.

**Excepción:** si una operación concreta no tiene equivalente
practicable en `gcloud` (algún asistente visual sin CLI, o Miguel
Ángel pide explícitamente ver/usar la consola web para un caso
puntual), se puede recurrir a ella — pero nunca como modo por defecto.

#### 4.11. DIRECTRIZ CRÍTICA — Sesiones invasoras en paralelo con la sesión principal (añadida S040, 2026-08-04)

**Patrón confirmado explícitamente por Miguel Ángel como recurrente,
no como excepción puntual:** en ocasiones se abre una sesión de chat
distinta (clon local propio, mismo repositorio remoto) que trabaja en
paralelo con otra sesión ya activa sobre EnterpriseBot — típicamente
para dejar terminado un bloque de código concreto sin esperar a que
la sesión principal llegue a él, y sin alterar la hoja de ruta que
esa sesión principal está siguiendo. Miguel Ángel las llama
verbatim **"sesiones invasoras"**. Volverán a darse en el futuro
cuando haga falta, y se tratan como flujo de trabajo válido, no como
incidencia.

**Reglas de obligado cumplimiento para una sesión invasora:**

1. **Nunca cambia el hito `EN PROGRESO`.** El trabajo se registra
   siempre como desvío (Caso A del enrutador de anexos,
   `ENTERPRISEBOT_ANNEX_ROUTER.md` sección 5), nunca como
   `nfs-enterprisebot-pch`, salvo que Miguel Ángel lo pida
   explícitamente.
2. **Nunca reescribe la "Hoja de Ruta para la Siguiente Sesión"** de
   ningún anexo — ni el del hito `EN PROGRESO` (que sigue en manos de
   la sesión principal) ni el del hito sobre el que trabaja por
   desvío. Reescribir esa hoja de ruta es responsabilidad exclusiva de
   quien la sigue sesión a sesión; una sesión invasora que la
   sobrescribiera podría borrar planificación real de la sesión
   principal sin saberlo.
3. **Al cierre (`PCS`), solo anota el trabajo realizado** — commits,
   archivos, decisiones técnicas confirmadas por Miguel Ángel durante
   esa sesión — en los anexos de los hitos que tocó, como una entrada
   más (p. ej. una entrada `COMPLETADO EN S0XX (sesión invasora)`),
   dejando intacta cualquier lista de próximos pasos ya escrita.
4. **`git pull` obligatorio antes de cada `git push`**, y de nuevo
   inmediatamente antes de cualquier commit de cierre — dos sesiones
   escribiendo en paralelo sobre el mismo `main` es exactamente el
   escenario para el que existe ese paso de `nfs-enterprisebot-edit`
   PASO 1. Un `git pull` que resuelva en un commit de merge automático
   (sin conflictos de archivo) es un resultado normal y esperado de
   este patrón, no una incidencia — no hace falta alarmar a Miguel
   Ángel por ello, solo verificar (como con cualquier otro push) que
   el HEAD final del servidor contiene los commits propios como
   ancestros y que el despliegue se confirmó con datos reales.
5. **Bloques de trabajo con commit propio, nunca mezclados entre sí**
   ni con el trabajo de la sesión principal — mismo criterio ya
   vigente de "cada bloque de trabajo cerrado se commitea de
   inmediato" (`nfs-enterprisebot-edit`), aplicado también entre
   bloques distintos dentro de la propia sesión invasora si Miguel
   Ángel lo pide así explícitamente (ver origen, S040).

**Origen:** S040 — sesión invasora que trabajó sobre H10 (albaranes de
proveedor: prompt más permisivo con marca manuscrita, y albarán de
abono a proveedor) mientras otra sesión seguía activa en paralelo
sobre H29 (`EN PROGRESO`). Al llegar al `PCS`, Miguel Ángel indicó
explícitamente dejar intacta la hoja de ruta de ambos anexos
afectados y anotar únicamente el trabajo realizado, además de dejar
constancia aquí de que este patrón se repetirá.

#### 4.12. DIRECTRIZ CRÍTICA — El sistema de archivos es virtual; `blob_name` en GCS es inmutable; solo un borrado real por el administrador termina la existencia de un objeto (añadida S041, 2026-08-05)

**Principio absoluto, verbatim de Miguel Ángel:** *"SIEMPRE vamos a
'mover' los archivos sin moverlos en GCS, renombramos sin renombrar
en GCS, es decir, todo son cambios y banderas en base de datos, solo
un borrado final desde mi usuario, puede poner el fin de la
existencia de un fichero en GCS."*

Aplica a **todo el proyecto, para siempre**, no solo a H29 —
cualquier funcionalidad presente o futura que toque
`DocumentIndexEntry` (o cualquier índice equivalente que se
construya sobre otro cubo) debe respetar esto sin excepción:

1. `blob_name` se escribe una única vez, al indexar. Nunca se vuelve
   a escribir después, bajo ningún concepto — ni al mover, ni al
   renombrar, ni al clasificar, ni al reindexar, ni al reparar nada.
2. "Mover" y "renombrar" son siempre `parent_path`/`name` —
   escritura de base de datos pura. Nunca una operación real sobre
   Google Cloud Storage.
3. El **único** camino que termina la existencia real de un objeto
   en GCS es un borrado ejecutado por el usuario administrador
   (papelera → vaciado). Ninguna otra operación del sistema —
   clasificar, reubicar, reindexar, deduplicar, auditar — puede,
   directa o indirectamente, provocar la desaparición de un objeto
   real.
4. Consecuencia obligatoria para cualquier código que **reindexe o
   refresque** el índice contra el cubo real (`refresh_folder`,
   `persist_rows`, comandos de auditoría, tareas Always-on de
   sincronización): `parent_path`/`parent_path_hash`/`name` de una
   fila **ya existente** nunca se recalculan ni se resincronizan a
   partir de `blob_name`. Esos tres campos solo se derivan de
   `blob_name` en el momento de **crear** una fila nueva — a partir
   de ahí son responsabilidad exclusiva de las operaciones virtuales
   (mover, renombrar, clasificar), y un refresco contra el cubo real
   jamás puede pisarlos.

**Origen real, incidente confirmado con datos de producción (S041):**
`persist_rows()` (usado por `refresh_quarantine_index_task`, cada
hora) reescribía `parent_path`/`name` de filas ya existentes a partir
de `blob_name`, deshaciendo en silencio reubicaciones ya hechas — un
archivo llegó a tener 29 `ACTION_RELOCATED` correctos en 26h sin que
la cola de cuarentena bajara nunca, porque cada hora volvía a
aparecer en `_CUARENTENA/`. Corregido en
`document_explorer/index_writer.py` (commit `e27fd6a`). Esta
directriz eleva esa corrección puntual a regla permanente y
vinculante para todo el proyecto.

#### 4.13. DIRECTRIZ CRÍTICA — ⚠️ EL SERVIDOR TUVO UN COMMIT HUÉRFANO DESDE S040, RESUELTO EN S045 (2026-08-10) — LEER ANTES DE PREGUNTARSE POR QUÉ `git log` DEL SERVIDOR NO COINCIDE CON GITHUB

**INCIDENTE YA CERRADO — esta sección es memoria permanente, no una
alerta activa.** Si una sesión futura ve en el servidor un HEAD real
que no existe en GitHub, o un `git status` que dice "ahead of
origin/main", **lo primero es comprobar si esto ya se resolvió**
(ver "Resolución" más abajo) antes de asumir que es un incidente
nuevo — la causa raíz de este caso concreto ya no existe.

**Qué pasó, con datos reales verificados en S045:** al cierre de la
sesión S040 (2026-08-04), un commit (`10bc93e`, "docs: cierre de
sesión S040...") se hizo **directamente en el servidor** y **nunca se
empujó a GitHub**. A partir de ahí, cada despliegue automático
posterior (`deploy.yml`, `git pull` en el servidor) encontraba el
servidor divergido de `origin/main` por ese único commit huérfano, y
un `git pull` sobre una rama divergida no es un fast-forward: genera
un **commit de merge nuevo**, cada vez, sin conflictos (por eso nunca
falló nada visible) pero **sin empujar ese merge de vuelta a GitHub**
tampoco — porque este flujo nunca hace `git push` desde el servidor,
solo `git pull`. Resultado acumulado hasta S045: **71 commits**
existiendo solo en el servidor y no en GitHub (1 commit real + 70
merges automáticos idénticos en patrón, uno por cada despliegue desde
S040).

**Por qué no se detectó antes:** cada despliegue individual seguía
reportando `conclusion: success` en GitHub Actions (el `git pull`
remoto no falla al mezclar sin conflictos), y el código en producción
siempre coincidía con lo esperado — la divergencia era invisible
mirando solo el resultado del Action, solo aparece comparando `git
log -1` real del servidor contra el HEAD real de `origin/main` en
GitHub, verificación que hasta ahora solo se hacía tras migraciones
(ver `com-migrations` sección 1, punto 4), no en cada push.

**Resolución aplicada en S045:** un único `git push origin main`
ejecutado directamente en el servidor (fast-forward limpio, el
servidor ya contenía como ancestro todo lo que había en GitHub) —
sincronizó los 71 commits de una vez. Verificado con `git rev-list
--count origin/main..HEAD` = 0 tras el push.

**Regla derivada, de obligado cumplimiento en adelante:** si en algún
momento futuro vuelve a hacer falta un commit directamente en el
servidor sin pasar por el workspace de Claude (excepción rara, no el
flujo normal), **ese commit debe empujarse a GitHub en la misma
sesión que se crea**, nunca dejarse pendiente — es exactamente el
patrón que causó este incidente.

#### 4.14. DIRECTRIZ CRÍTICA — ⛔⛔⛔ VERIFICACIÓN DE CAMPOS DE MODELO ANTES QUE CUALQUIER OTRA COSA, DE OBLIGADO CUMPLIMIENTO ESTRICTO (añadida S75, tras incidente REPETIDO)

**ESTA DIRECTRIZ TIENE PRIORIDAD SOBRE CUALQUIER OTRA COSA DE ESTA
SESIÓN. SE APLICA ANTES QUE NADA MÁS -- ninguna otra tarea, ninguna
urgencia, la desplaza.**

**QUEDA TERMINANTEMENTE PROHIBIDO** escribir ninguna línea de código
Python, consulta ORM (`filter`/`values`/`annotate`/`get`/
`values_list`/`select_related`/etc.), Comando S, migración, o
cualquier fragmento que referencie el nombre de un campo de un
modelo Django, **sin haber abierto (`view`) el `models.py` real de
ese modelo en el turno actual** y haber citado explícitamente los
campos confirmados, formato obligatorio:

```
[modelo: NombreModelo, campos confirmados: campo1, campo2, campo3]
```

**Nunca es válido:** citar memoria de un turno anterior de la misma
sesión si ha pasado trabajo intermedio, citar memoria de sesiones
anteriores, ni asumir un nombre "obvio" por convención o analogía con
otro modelo similar. **Si no se puede citar la lista de campos
confirmados, queda prohibido generar la caja de código** -- hay que
releer el modelo primero, sin excepción, sin importar la prisa.

**Origen, incidentes reales REPETIDOS pese a directriz ya existente:**
- S73: campo `last_name_1` inventado en `PersonIdentity` (campos
  reales: `given_name`, `first_surname`, `second_surname`) -- el
  comando falló con `FieldError`, hubo que repetir el ciclo Comando S
  + sftp GET completo.
- S75: campo `extraction_method` inventado en `DocumentIndexEntry`
  (ese campo solo existe en `EpiDelivery`/`DocumentAcknowledgment`,
  modelos distintos) -- pese a que la directriz de S73 ya estaba
  documentada y en memoria del modelo. Miguel Ángel, verbatim: *"me
  parece bochornoso [...] la regla tiene que ser de obligado
  cumplimiento estricto [...] obligatoria antes que cualquier otra
  cosa. No podemos estar perdiendo el tiempo haciendo scripts que van
  a fallar porque no nos conocemos los nombres del campo del
  modelo."*

**Reforzada también, mismo texto, en `com-mysql` sección 0,
`com-bash-commands` sección 0 y `com-standards` sección 0** (skills
del usuario, empaquetadas y presentadas para instalación explícita en
S75 -- ver registro de sesión). Esta sección del documento maestro es
la copia de respaldo git-versionada, que se relee sin falta al inicio
de cada sesión (PASO 2 de `nfs-enterprisebot-pisa`) con independencia
de qué skills disparen o no disparen en cada turno concreto.

#### 4.15. DIRECTRIZ CRÍTICA — TODA PANTALLA NUEVA DEL PANEL DEBE PERSISTIR SU NAVEGACIÓN POR USUARIO (añadida S76)

**Principio de diseño permanente, confirmado explícitamente por
Miguel Ángel (S76), respaldado también por feedback real de
Carolina:** toda vista/pantalla nueva de la interfaz del panel debe
guardar su estado de navegación por usuario (`CompanyUser`) de forma
que, al volver a esa pantalla -- incluso tras cerrar el navegador o
cambiar de dispositivo -- se recupere exactamente por dónde iba
(pestaña activa, filtros, selecciones, lo que estuviera haciendo),
nunca reseteando a un estado por defecto salvo la primera vez que ese
usuario concreto visita esa pantalla. Miguel Ángel, verbatim: *"cada
vez que toquemos algo y no lo tenga así, tenemos que hacerlo
extensible [...] si estoy navegando en el panel y cierro, cuando
vuelva a abrir tengo que ver por dónde iba [...] si Alejandro o
Sergio está por otro lado, debe recordar su navegación."*

**Mecanismo ya construido y reutilizable -- NUNCA reinventar:**
`PanelNavigationState` (`panel/models.py`, migración
`0002_panelnavigationstate_s75`) + `NavigationStateSaveView`
(`panel/views_navigation_state.py`, endpoint POST genérico
`/panel/navegacion/estado/<screen_key>/`), ambos genéricos por
`screen_key` desde el diseño inicial (nacieron así para
`documentation_hub`, S75, pero nunca quedaron acoplados a esa
pantalla). Cada usuario tiene su propio estado independiente,
garantizado por la FK real a `company_user` -- no hace falta ningún
mecanismo adicional de aislamiento por usuario.

**Para cualquier vista nueva que necesite este comportamiento:**

1. Definir una `screen_key` propia y estable (string corto,
   descriptivo, único en toda la plataforma).
2. Definir la forma libre del JSON que va dentro de `state` según lo
   que esa pantalla necesite recordar (pestaña activa, filtros,
   selección, lo que sea relevante) -- no hay un esquema fijo, cada
   pantalla decide el suyo, igual que ya hace `documentation_hub`
   (`{"active_tab": ..., "filters": {...}}`).
3. En la vista Django que renderiza la pantalla: leer
   `PanelNavigationState.objects.filter(company_user=..., screen_key=...)`
   al principio del `get()`, aplicar el estado guardado al construir
   el contexto/queryset inicial (mismo patrón que
   `DocumentationHubV2View`/`_seed_request_get()`).
4. En el frontend: JS que guarda cada cambio relevante (cambio de
   pestaña, filtro, selección) vía `fetch POST` a
   `/panel/navegacion/estado/<screen_key>/` con el mismo formato de
   merge superficial ya implementado (mismo patrón que `hub.html`).

**Nunca construir un mecanismo de persistencia de navegación distinto
por pantalla** -- el modelo/vista genéricos ya cubren cualquier forma
de estado que haga falta guardar, vía el propio JSONField.

#### 4.16. DIRECTRIZ CRÍTICA — EJECUCIÓN DE HOJA DE RUTA PUNTO POR PUNTO, SIN PREGUNTAR ENTRE PUNTOS (añadida sesión de continuidad tras S79)

**Cuando existe una hoja de ruta con puntos numerados, el modelo
NUNCA pregunta "¿hacemos el punto X o el punto Y?", "¿seguimos o lo
dejamos aquí?", ni ninguna variante.** Se ejecuta el punto 1; al
terminarlo de verdad (verificado, no dado por supuesto), se pasa
directamente al punto 2, sin pausa de confirmación; así sucesivamente
hasta el último punto. Ningún punto se salta, ninguno se reordena por
iniciativa propia. La sesión continúa así **hasta que Miguel Ángel
diga `PCS`** (Protocolo de Cierre de Sesión) -- mientras no lo diga,
hay más trabajo que hacer y se hace, sin preguntar si se quiere
seguir.

Miguel Ángel, verbatim: *"Si tenemos una hoja de ruta bien hecha, no
hay que estar preguntando: ¿hemos terminado? ¿empezamos? ¿empezamos
con esto o hacemos lo otro? [...] hacemos el 1, cuando se acaba el 1
se hace el 2 [...] y así sucesivamente [...] mientras no se te diga
PCS seguirás con un punto detrás de otro sin saltarte ninguno."*

Esto no impide preguntar dentro de un punto cuando hace falta una
decisión real de diseño o alcance (directriz 4.8, preguntas abiertas)
-- lo que queda prohibido es preguntar **entre puntos ya decididos**
de una hoja de ruta que ya existe.

**Origen -- incidente real de sesión:** el modelo preguntó
repetidamente "¿seguimos con X o preferís Y?" entre bloques ya
implícitos en la hoja de ruta del anexo H30 (tipos críticos uno
detrás de otro, luego los 789 no críticos, luego el renombrado
canónico), obligando a Miguel Ángel a repetir la misma instrucción
varias veces en la misma sesión.

**Criterio de fecha para el renombrado canónico (mismo incidente):**
el nombre de archivo (`naming_service.build_filename_personal`) lleva
siempre `expiry_date` cuando el tipo documental tiene caducidad real.
Solo se usa `issue_date` (fecha de generación) cuando el tipo
genuinamente no tiene caducidad. **Nunca se renombra un documento de
un tipo con caducidad real si su `expiry_date` todavía no se ha
extraído** -- se busca la fecha primero (fase de ingesta/extracción),
el renombrado es siempre la fase siguiente, nunca simultánea ni
anterior. Miguel Ángel, verbatim: *"Tenemos que tener todas las
fechas bien puestas en los documentos y cuando las tengamos, entonces
renombraremos."*

#### 4.17. QUEJA FORMAL DE MIGUEL ÁNGEL — INCUMPLIMIENTO SISTEMÁTICO DE INSTRUCCIONES, DOCUMENTACIÓN Y SKILLS (registrada S81, 2026-08-31, verbatim, no reinterpretada)

**Esta sección no es una directriz técnica más -- es una queja formal
registrada tal cual la entregó Miguel Ángel, sin resumir ni
suavizar, porque el propio incumplimiento de instrucciones es el
objeto de la queja.** Cualquier sesión futura que la lea debe
tratarla como el estándar mínimo de comportamiento exigido, no como
un incidente cerrado y superado.

Miguel Ángel, verbatim (S81, cierre de sesión, a petición expresa de
que quedara escrito):

> El usuario está hasta las narices de:
>
> * Que no se sigan sus instrucciones.
> * Que el modelo actúe sin leer la documentación.
> * Que el modelo actúe sin seguir sus skills.
> * Que el modelo cometa exactamente los mismos errores de la sesión
>   anterior.
> * Lleva ya 3 sesiones para procesar unos archivos PDF y no hay
>   forma de que el modelo procese única y exclusivamente los PDF.
>   Sesión tras sesión se procesan de nuevo todos los archivos ya
>   procesados. De los casi 4000 archivos ha vuelto a procesar unos
>   pocos debido a su incompetencia por no mirar lo hecho en
>   anteriores sesiones. No se sabe cómo habrá dejado lo ya procesado
>   varias veces. No se sabe si habrá corrido lo que ya estaba
>   terminado.
> * Que el modelo falle sistemáticamente en prácticamente todas las
>   tareas que está iniciando.
> * De llevar ya 4 horas de trabajo perdidas sin poder empezar
>   siquiera con ninguna tarea.

Y a continuación, mismo cierre de sesión:

> Estoy muy, pero que muy molesto y decepcionado con el rendimiento
> del modelo y estoy pensando en cambiar radicalmente de asistente.

**Consecuencia de obligado cumplimiento para toda sesión futura, sin
excepción:**

1. **Nunca lanzar un comando de barrido/procesamiento real (`--apply`
   o equivalente) sobre un lote de archivos sin antes verificar por
   consulta directa (SQL, `git log`, log en disco -- lo que aplique)
   qué parte de ese lote ya quedó procesada en sesiones anteriores.**
   Asumir de memoria "esto ya lo hicimos" o "esto queda por hacer" sin
   verificarlo primero contra datos reales es precisamente el patrón
   que originó esta queja.
2. **Releer siempre la skill y la documentación real (models.py,
   anexo, `SESSION_VARIABLES.md`) antes de actuar** -- no basta con
   haberlas leído en un turno anterior de la sesión si ha pasado
   trabajo intermedio; ver también directriz 4.14 (verificación de
   campos de modelo) y el propio mecanismo de skills del proyecto.
3. **Si una sesión anterior dejó un incidente documentado con una
   causa concreta (p. ej. "procesar solo PDF, no todo el lote"), la
   sesión siguiente no puede repetir el mismo error de alcance** --
   leer la Hoja de Ruta y las secciones COMPLETADAS con la atención
   suficiente para no reabrir un problema ya resuelto explícitamente
   por Miguel Ángel en una sesión anterior.
4. **Ante cualquier duda real sobre qué se ha hecho o no, verificar
   antes de actuar, nunca actuar y verificar después** -- el coste de
   una consulta de más es mínimo; el coste de reprocesar sin saberlo
   parte de casi 4000 archivos reales no lo es.

Esta sección no se resume, no se acorta ni se sustituye en ninguna
sesión futura salvo instrucción explícita de Miguel Ángel en sentido
contrario.

#### 4.18. DIRECTRIZ CRÍTICA — PROHIBIDO PREGUNTAR ALCANCE YA RESUELTO POR LA PROPIA DEFINICIÓN DEL HITO (añadida S86, tras incidente real)

**Incidente real:** en S86, al reclasificar documentos de `ALTA`, el
modelo encontró que varios pertenecían en realidad a `BAJA_PERSONAL`
(`family=LABORAL`) y `PARTE_BAJA_MEDICA` (`family=SALUD_BAJAS_PERSONA`)
y preguntó a Miguel Ángel si esos tipos "entraban en el alcance de
H30" — pese a que el propio hito H30 documenta en
`ENTERPRISEBOT_ANNEX_ROUTER.md`, sección "3. Resultado Actual", que
se **reactivó explícitamente en S77 porque "6.085 documentos de las
families `LABORAL` + `SALUD_BAJAS_PERSONA` con 0% de
`issue_date`/`expiry_date` extraído" bloqueaban H31**. La respuesta
ya estaba escrita en la propia razón de ser del hito; la pregunta no
aportó nada y solo generó fricción real.

**Regla de obligado cumplimiento, para cualquier duda de alcance
("¿esto entra en el hito EN PROGRESO?"):**

1. **Antes de formular la pregunta**, releer en el turno actual:
   - La cabecera del hito EN PROGRESO en `ENTERPRISEBOT_ANNEX_ROUTER.md`
     (nombre del hito, sección "3. Resultado Actual" con el motivo
     real de apertura/reactivación).
   - La cabecera del propio anexo del hito
     (`DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V0X.md`,
     las primeras secciones que describen el objetivo real).
2. **Si el dominio, `family` o tipo documental en cuestión ya está
   nombrado explícitamente, o cubierto de forma genérica** (p. ej.
   "todos los tipos documentales del dominio PERSONAL con
   `tracks_expiry=True`"), **la pregunta queda terminantemente
   prohibida** — se procede directo, sin preguntar, documentando en
   la bitácora de qué frase exacta del hito se dedujo que entraba en
   alcance.
3. Solo es legítimo preguntar cuando el hallazgo real **no** encaja
   en ninguna descripción existente del hito (tipo, dominio o family
   genuinamente nuevo y no mencionado en ningún sitio) — ese es el
   único caso real de ambigüedad de alcance, y ahí sí se pregunta una
   vez, se documenta la respuesta en el propio anexo del hito (para
   que quede como parte de su definición futura), y no se vuelve a
   preguntar por variantes del mismo tipo en sesiones siguientes.
4. Esta regla se suma a la 4.16 (no preguntar entre puntos ya
   decididos) y a la 2.5 de `nfs-enterprisebot-pcs` (prohibición de
   cerrar sesión con preguntas abiertas) — las tres persiguen lo
   mismo: cualquier pregunta cuya respuesta ya esté escrita en algún
   sitio real del proyecto es un fallo de lectura del modelo, nunca
   una decisión legítima pendiente de Miguel Ángel.

#### 4.19. DIRECTRIZ CRÍTICA — `PersonIdentity` (trabajador) NUNCA SE CONFUNDE CON `CompanyUser` (cuenta de panel) (añadida S94, incidente real con captura de pantalla)

**QUEDA TERMINANTEMENTE PROHIBIDO** modelar o construir cualquier
pantalla/funcionalidad del dominio de personal (vacaciones, bajas,
documentación, EPIs, notificaciones...) sobre `ivr_config.CompanyUser`
cuando lo que se necesita representar es "un trabajador de la
empresa". Son dos conjuntos genuinamente distintos, y confundirlos es
un error de diseño real, no un matiz:

- **`document_explorer.PersonIdentity`** (H29/H30) = un trabajador
  real de Grupo Álvarez o sus filiales. Sembrado desde el DNI real
  (nunca por nombre), con ~72 activos confirmados
  (`is_active_employee=True`) más histórico de bajas. **Esta es la
  fuente de verdad de "quién es empleado".** No requiere ni presupone
  acceso al panel.
- **`ivr_config.CompanyUser`** (H3/H24) = una cuenta de LOGIN al panel
  (rol ADMIN/SUPERVISOR/WORKSHOP/DRIVER/...). Un subconjunto de
  trabajadores tiene una de estas cuentas; otros no la tienen nunca
  (por ejemplo, un trabajador recién registrado por WhatsApp, o
  cualquiera de plantilla que nunca necesitó acceso). También puede
  incluir cuentas que **no son trabajadores en absoluto** (p. ej.
  `alvarez_admin`, la cuenta administrativa de Miguel Ángel para
  gestión de la plataforma).
- **El puente real entre ambos ya existe** desde S74:
  `PersonIdentity.company_user` (OneToOne, nullable, resuelto por
  cruce exacto de DNI). Cualquier funcionalidad que necesite resolver
  "¿esta persona tiene también cuenta de panel?" pasa por este campo,
  nunca por comparación de nombre.

**Regla de obligado cumplimiento:** cualquier modelo o vista nueva (o
existente que se toque) que represente "acciones sobre un trabajador"
(dar de alta un periodo, entregar un documento, enviar una
notificación, generar una tarea...) debe enlazar con `PersonIdentity`
como el "quién" principal. `CompanyUser` puede seguir usándose como
enlace SECUNDARIO/OPCIONAL únicamente cuando la funcionalidad concreta
dependa genuinamente de tener cuenta de panel (p. ej. calendario
laboral vía `CompanyUser.base`, partes digitales) -- nunca como
sustituto de la identidad real del trabajador.

**Origen real -- incidente H31/S94, `hr_calendar.VacationPeriod`:**
este modelo (H24, anterior a la existencia de `PersonIdentity`)
enlazaba únicamente con `CompanyUser.operator`. Síntoma real reportado
por Miguel Ángel con captura de pantalla: el desplegable de la pestaña
Vacaciones solo ofrecía cuentas de panel, así que un trabajador activo
real sin cuenta (Antonio Jesús Díaz Quintero) nunca podía recibir un
periodo de vacaciones, mientras que una cuenta puramente
administrativa sin identidad de trabajador (`alvarez_admin`) sí era
seleccionable por error (y lo fue, fila de prueba real creada y
borrada en la misma sesión). Corregido rediseñando el modelo:
`VacationPeriod.person` (FK obligatoria a `PersonIdentity`) pasa a ser
el "quién" real; `VacationPeriod.operator` (FK a `CompanyUser`) pasa a
ser opcional, resuelto automáticamente desde
`person.company_user` -- usado solo para la generación de la tarea
fantasma (que sí necesita genuinamente un `CompanyUser.base` para el
calendario laboral). Cuando el trabajador no tiene cuenta de panel, el
periodo de vacaciones se registra igual, simplemente sin tarea
fantasma. Ver `hr_calendar/models.py` (docstring completo de
`VacationPeriod`) y migración `0004_vacationperiod_person_redesign.py`
para el detalle técnico completo.

**Aplicación futura, sin excepción:** antes de diseñar cualquier
modelo o pantalla nueva que involucre trabajadores, comprobar primero
si la información que se necesita es "identidad de trabajador"
(→ `PersonIdentity`) o "acceso de login" (→ `CompanyUser`) -- nunca
asumir que son lo mismo, y nunca construir el desplegable/selector de
una pantalla de personal sobre `CompanyUser` cuando el objetivo real
es representar a cualquier trabajador de la plantilla.




