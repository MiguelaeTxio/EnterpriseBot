# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V31.md
# Anexo H31 — Interfaz de Ficha de Personal: EPIs y Notificaciones/Circulares

---

## 1. Objetivo del hito

Construir la interfaz real que permita, desde el panel:

1. Ver y editar la **ficha de una persona** (datos + foto de carné).
2. **Entregar un EPI** a esa persona, individualmente, desde su ficha.
3. **Enviar una notificación** a esa persona, individualmente, desde
   su ficha.
4. **Entrega masiva de EPIs** y **envío masivo de circulares** a un
   grupo de personas seleccionado con casillero.
5. **CRUD de circulares/notificaciones**: crear, editar, importar
   (Word/PDF) y sustituir la plantilla vigente de un tipo, con un
   editor de texto básico integrado.

Hasta ahora (H30) solo existía el histórico migrado (`EpiDelivery`,
`DocumentAcknowledgment`) y vistas de solo lectura sobre él. Este
hito construye las ACCIONES reales de entrega/envío que un
supervisor usará en producción, no solo la consulta.

---

## 2. Contexto técnico de partida (S73)

### Ya existe (reutilizable)

- `panel/views_documentation_h30.py`:
  - `PersonalDetailView` + `panel/templates/panel/documentation_h30/_personal_detail.html`
    -- ficha de persona de solo lectura: datos, documentos
    (actuales/obsoletos), lista de `EpiDelivery`. **Sin foto de
    carné, sin formulario editable, sin acción de entrega.**
  - `EpiTabFragmentView`/`EpiResultsFragmentView` +
    `_epi_pane.html`/`_epi_results.html`/`_epi_search_form.html` --
    pestaña EPIs de solo lectura (buscar/ordenar/paginar entregas ya
    existentes). **Sin acción de entrega.**
  - `PersonalListFragmentView`/`PersonalResultsFragmentView` +
    `_personal_pane.html`/`_personal_results.html`/
    `_personal_search_form.html` -- listado/búsqueda de personas.
  - `DocumentTypeQuickCreateView` -- atajo de alta de tipo documental
    desde el flujo de subida (no es el CRUD de circulares que hace
    falta aquí, pero confirma el patrón de alta rápida ya aceptado).
- `document_explorer.models.DocumentTypeCatalog.current_template`
  (H30 S69) -- FK a `DocumentIndexEntry`, "plantilla vigente" de un
  tipo documental. YA EN USO REAL (H30 S73):
  `RECURSO_PREVENTIVO`, `NOMBRAMIENTO_RESPONSABLE_SEGURIDAD`,
  `CIRCULAR_INFORMATIVA`, `INFORMACION_MEDIDAS_PROTECCION` tienen
  plantilla vigente asignada. Este es el mecanismo natural sobre el
  que construir el CRUD de circulares -- cambiar la plantilla
  vigente es reapuntar este campo, nunca duplicar filas.
- `document_explorer.models.EpiDelivery`/`EpiReview`/
  `DocumentAcknowledgment` -- modelos de histórico ya maduros (H30),
  con `extraction_method` (`MANUAL`/`HEURISTIC`/`OCR`/`GEMINI`) ya
  preparado para que una entrega hecha desde el panel se registre
  como `MANUAL`.
- `document_explorer.models.PersonIdentity` -- sin campo de foto de
  carné confirmado todavía; verificar en la primera sesión si existe
  algún campo o mecanismo real de "fotos de carné ya asignadas" que
  Miguel Ángel menciona (S73) antes de asumir que hay que añadirlo.

### No existe (por construir)

- Cualquier vista/acción de ESCRITURA real: entregar EPI, enviar
  notificación, editar ficha de persona, subir foto de carné, CRUD de
  circulares. Solo existe la prueba de concepto de envío (ver
  "COMPLETADAS EN S73" más abajo).
- Selector de personal con casillero para acciones masivas.
- El campo de texto enriquecido real para el contenido de
  circulares/notificaciones (decisión de S73: campo NUEVO en BD,
  manteniendo `current_template`/archivo legacy en paralelo -- falta
  decidir el modelo de datos exacto en la próxima sesión).
- Importación de Word/PDF para crear o sustituir una circular.

---

## 3. COMPLETADAS EN S73

- **Hito abierto** (PCH CASO C): H31 dado de alta inmediatamente
  después de cerrar el bloque EPIs de H30, decisión explícita de
  Miguel Ángel. PCH a `EN PROGRESO` en la misma sesión (CASO B),
  H30 pausado.
- **Diagnóstico real de lo existente**: `PersonalDetailView`/
  `EpiTabFragmentView` y sus templates confirmados como solo lectura
  (sin foto, sin acción de entrega/envío) -- ver sección 2 arriba.
- **Tres preguntas de diseño RESUELTAS** por Miguel Ángel:
  1. Cuerpo de circular/notificación: campo de texto enriquecido
     NUEVO en BD, manteniendo el legacy (`current_template`) en
     paralelo, no sustituyéndolo de golpe.
  2. Envío: por correo electrónico, nunca WhatsApp para este tipo de
     comunicación con documentos. Primer intento (`mailto:`)
     descartado por Miguel Ángel al aclarar que el cuerpo debe salir
     con el HTML real (colores, negrita), no como adjunto -- `mailto:`
     no soporta HTML. Sustituido por generación de `.eml` real.
  3. Foto de carné: confirmado, 108 imágenes reales
     (`document_type=IMAGEN`) ya vinculadas vía
     `domain_content_type`/`domain_object_id` a su `PersonIdentity`
     -- sin campo dedicado, se reutiliza el mismo mecanismo genérico
     ya usado en toda la plataforma.
- **Prueba de concepto de envío VALIDADA con Outlook real**:
  `PersonalTestEmlView` (`panel/views_documentation_h30.py`) genera
  un `.eml` con `email.message.EmailMessage.add_alternative(...,
  subtype="html")` (contenido de prueba fijo: fondo de color,
  negrita, color de texto, lista), servido como descarga desde un
  botón nuevo en `_personal_detail.html`. Miguel Ángel confirmó con
  captura real de Outlook: el formato HTML llega íntegro. Commits
  `ba7f2a9` (vista + botón) y `6028e28` (documentación). **Vista y
  botón son temporales** -- a retirar cuando el CRUD real de
  circulares los sustituya.
- Sin migraciones esta sesión (H31 no tocó `models.py` todavía).

## 4. COMPLETADAS EN S74

Sesión larga (8 commits reales), puntos 1-4 de la hoja de ruta
cerrados y verificados contra BD real, más una decisión de diseño
nueva no prevista (vínculo Company/CompanyUser + WhatsApp de EPI) y
una incidencia real de integridad de datos descubierta y corregida
en la misma sesión.

- **Punto 1 -- modelo de datos del contenido enriquecido** (commit
  `a4305bd`): campo `content_html` (TextField) añadido directamente
  en `DocumentTypeCatalog` -- decisión de diseño: mismo patrón que
  `current_template` (campo directo, no modelo aparte, sin necesidad
  de versionado histórico). Migración `0059`, verificada en
  producción (`showmigrations` + lectura/escritura real contra la
  fila `CIRCULAR_INFORMATIVA`).
- **Logo corporativo real** (commit `9f3d95a`): descargado por
  Miguel Ángel de `gruasalvarez.com` (mismo logo real de cabecera/pie
  de la web pública), guardado en
  `panel/static/panel/img/grupo_alvarez_logo.png`. Decisión técnica:
  se incrustará siempre como adjunto INLINE con Content-ID
  (`add_related`), nunca como `<img src>` remoto -- Outlook y la
  mayoría de clientes de correo bloquean imágenes remotas por
  defecto.
- **Punto 2 -- ficha de persona editable con avatar** (commit
  `4bc21bb`): `PersonalUpdateView` nueva (given_name/first_surname/
  second_surname/phone/email editables; el resto de campos, origen
  Excel, quedan de solo lectura). Avatar real vía
  `domain_content_type`/`domain_object_id` filtrado por
  `DocumentTypeCatalog.code='IMAGEN'`, sin campo dedicado nuevo.
  Verificado contra BD real: 187 imágenes vinculadas a personas,
  consulta exacta de la vista resuelta sobre un caso real (persona
  pk=128).
- **Punto 3 -- entrega individual de EPI** (commit `a845df9`):
  `EpiIndividualDeliveryView` nueva, crea
  `EpiDelivery(extraction_method=MANUAL)`. Verificado contra BD real
  con una entrega de prueba creada y eliminada.
- **Requisito nuevo de Miguel Ángel -- confirmación WhatsApp de
  entrega de EPI** (commit `7f1d4d0`): al entregar un EPI, el
  trabajador recibe confirmación por WhatsApp con constancia escrita
  de la entrega. Requirió:
  - `PersonIdentity.company` (FK nula a `ivr_config.Company`,
    migración `0060`) -- backfill real verificado: solo existe 1
    Company en toda la plataforma (`Grupo Álvarez`), 69 personas
    vinculadas por normalización de las 6 variantes reales de
    `employer_company`.
  - `whatsapp.services.send_epi_delivery_whatsapp_confirmation()`,
    no bloqueante -- un fallo de WhatsApp nunca revierte la entrega
    ya comprometida en BD.
  - `whatsapp/management/commands/create_epi_delivery_whatsapp_template.py`
    (nuevo): crea y somete a aprobación de Meta la plantilla
    `epi_delivery_confirmation` vía Twilio Content API, usando
    `requests` crudo en vez de
    `client.content.v1.contents.create()` del SDK -- bug real y
    confirmado en `twilio-python` (issue #881, abierto desde 9.7.2,
    sin fix reportado, verificado contra GitHub en esta sesión).
    Ejecutado en producción: plantilla creada
    (`HX041e42204143fa11b942cfb76608fcb0`), sometida a Meta, estado
    `received`. Coletilla de opt-out reutilizada literalmente de
    `document_expiry_alert` (ya aprobada por Meta).
- **Vínculo `PersonIdentity` <-> `CompanyUser`** (commit `72bd046`):
  petición explícita de Miguel Ángel -- el personal de plantilla
  también son usuarios reales del panel (supervisor, administrador,
  operario de taller...), debe quedar reflejado. `company_user`
  (OneToOne nula, migración `0061`), backfill por cruce EXACTO de
  DNI: de 25 `CompanyUser` reales, 11 tenían DNI relleno y los 11
  cruzaron limpio contra `PersonIdentity`, sin ambigüedad. Reflejado
  en la ficha (rol real, estado de la cuenta).
- **Incidencia real de integridad de datos, detectada y corregida en
  la misma sesión** (commit `cbce231`): al ver la ficha de Alejandro
  García Luque en el panel, Miguel Ángel detectó que mostraba
  "Antonio Jesús" pese a que 84+ documentos reales llevaban su
  nombre correcto. Auditoría completa Excel
  (`EXEL_TRABAJADORES.xlsx`, 58 trabajadores reales) vs los 230
  `PersonIdentity` de BD, por nombre y por DNI. Hallazgo raíz:
  `PersonIdentity pk=96` (dni=`74852725F`) era un fantasma de
  captura -- DNI matemáticamente válido (pasa la letra de control)
  pero sin persona real correspondiente, a solo 1 dígito de
  distancia tanto del DNI real de Alejandro (`74852724Y`, pk=158)
  como del de un compañero real. Demuestra con datos reales que la
  letra de control (ya aplicada en `seed_person_identities` desde
  S040) no puede detectar todos los dígitos mal leídos -- la única
  defensa real es la auditoría cruzada contra una fuente externa, no
  una mejora del validador (`is_valid_spanish_dni`, ya correcto).
  Migración `0062`: 3 correcciones de apellido según el Excel
  (fuente de verdad, decisión explícita de Miguel Ángel) + fusión
  pk=96 -> pk=158 (repunte de 87 `DocumentIndexEntry` y 5
  `EpiDelivery`, operación pura de BD, blob_name nunca se toca).
  Verificado tras el despliegue: pk=158 con 241 documentos y 93 EPIs
  (154+87 y 88+5 exactos), pk=96 con 0 referencias -- borrado a
  continuación (229 `PersonIdentity` restantes).
- **Punto 4 -- envío individual de notificación** (commit `f9d9f03`):
  `PersonalNotificationSendView` sustituye a `PersonalTestEmlView`
  (S73, retirada junto con su botón -- punto 7 cerrado de paso).
  Contenido real de `DocumentTypeCatalog.content_html`, logo
  corporativo incrustado inline vía Content-ID
  (`staticfiles.finders.find` + `add_related`), registra
  `DocumentAcknowledgment(extraction_method=MANUAL)` al generar el
  `.eml`. Sigue sin envío SMTP real -- el proyecto no tiene
  `EMAIL_BACKEND` configurado, el `.eml` se descarga y el supervisor
  lo envía desde su propio Outlook (mismo flujo validado en S73).
  Verificado con una simulación real en memoria (sin tocar BD):
  `.eml` de 7211 bytes, `cid:` presente en el HTML, `Content-ID` y
  `image/png` del logo confirmados en los bytes generados.
- **Todas las migraciones de la sesión (0059-0062) verificadas en
  producción** con datos reales -- HEAD del servidor, `showmigrations`,
  y consultas ORM reales sobre las filas afectadas, nunca solo el
  icono verde de GitHub Actions (regla S014).

## 5. Hoja de ruta para S75 -- CERRADA, ver COMPLETADAS EN S75 abajo

1. **Selector masivo con casillero** + acción masiva de EPI y de
   circular (mismo backend que los puntos 3-4 ya construidos, en
   bucle sobre la selección). Criterio de cierre: al menos una
   entrega/envío masivo real ejecutado desde el panel sobre 2+
   personas, verificado contra BD (N `EpiDelivery`/
   `DocumentAcknowledgment` nuevas, N = tamaño de la selección).
2. **CRUD de circulares**: crear/editar/importar (Word/PDF) y
   sustituir la plantilla vigente (`current_template`) de forma
   consistente con el mecanismo ya en uso. Editor de texto básico
   integrado (colores, pocas fuentes) -- alcance deliberadamente
   reducido, nunca un procesador de textos completo. Este es el
   punto que rellenará `content_html` de verdad para las circulares
   reales (`CIRCULAR_INFORMATIVA`,
   `NOMBRAMIENTO_RESPONSABLE_SEGURIDAD`, etc.) -- ahora mismo sigue
   vacío salvo pruebas puntuales restauradas a blanco. Criterio de
   cierre: al menos una circular real editada desde el panel con
   `content_html` no vacío, verificada leyendo la fila real desde
   BD.
3. **Comprobar el estado real de aprobación de Meta** de la
   plantilla WhatsApp `epi_delivery_confirmation`
   (`HX041e42204143fa11b942cfb76608fcb0`, estado `received` al
   cierre de S74) -- `GET
   https://content.twilio.com/v1/Content/HX041e42204143fa11b942cfb76608fcb0/ApprovalRequests`
   vía Comando S, o revisar directamente en el Console de Twilio.
   Criterio de cierre: estado `approved` confirmado y al menos una
   entrega real de EPI con `whatsapp_sent: true` en la respuesta.
   **Pospuesto explícitamente** -- Miguel Ángel redirigió la sesión
   hacia UX/persistencia/integridad de datos antes de llegar aquí.
4. **Auditoría de integridad de datos ampliada** (nace de la
   incidencia de S74): la auditoría Excel vs BD de esta sesión se
   hizo a mano, sobre un caso concreto que saltó a la vista en el
   panel. Valorar con Miguel Ángel si conviene un comando de gestión
   real (`audit_person_identities_against_excel` o similar) que
   automatice la comparación nombre+DNI completa cada vez que se
   suba un Excel nuevo, en vez de repetirla a mano. No iniciar sin
   que Miguel Ángel lo pida explícitamente -- consultar primero.
   **No iniciado.**

Criterio de cierre de S75: al menos el punto 1 o el punto 2
completado y verificado contra BD, no solo diseñado. **CUMPLIDO POR
PARTIDA DOBLE** -- ver COMPLETADAS EN S75.

## 5.1. COMPLETADAS EN S75

- **Punto 1 -- selector masivo con casillero** (commit `6b2af9e`):
  casillero en `_personal_results.html` + "seleccionar todos los de
  esta página", barra de acción masiva persistida en memoria (Set +
  delegación de eventos sobre `#pane-personal`, sobrevive a
  búsqueda/paginación). `EpiMassDeliveryView` (POST): N
  `EpiDelivery(MANUAL)` reales en bucle, WhatsApp de confirmación no
  bloqueante por persona. `PersonalNotificationMassSendView` (POST):
  N `.eml` empaquetados en un único `.zip` de descarga (decisión de
  diseño explícita, no especificada en la hoja de ruta -- un solo
  zip en vez de N descargas simultáneas), un `DocumentAcknowledgment`
  real por persona con éxito. Refactor DRY:
  `_build_notification_eml()` extraído y compartido entre la vista
  individual y la masiva. Desplegado y verificado, sin migración.
- **Punto 2 -- CRUD de circulares** (commit `bb131a5`): nuevo módulo
  `panel/views_circulars_h31.py`, acotado a `DocumentTypeCatalog` de
  dominio PERSONAL/BOTH -- listar, crear (mismo patrón que
  `DocumentTypeQuickCreateView`), editar `content_html` con editor de
  texto básico integrado (`contenteditable` + `document.execCommand`,
  paleta de color y tipografías deliberadamente reducidas, pegado
  externo limpiado a texto plano), importar Word/PDF real
  (`python-docx`/`pymupdf4llm` con fallback a `fitz`, ya en
  `requirements.txt`) que sustituye `content_html` por el texto
  extraído como punto de partida a retocar, y sustituir la plantilla
  vigente (`current_template`) subiendo el archivo real a
  `_PLANTILLAS_CIRCULARES/<code>/` sin tocar ni borrar la anterior
  (4.12). Verificado en producción con datos reales vía Comando S:
  `python-docx` 1.2.0, `pymupdf4llm` y `fitz` disponibles en el venv
  de producción, 73 tipos PERSONAL/BOTH activos. Desplegado, sin
  migración.
- **Incidencia real corregida en la misma sesión -- persistencia de
  navegación** (commit `ca836c7`): Miguel Ángel reportó que recargar
  la página o volver atrás en el navegador tras entrar en
  Documentación reseteaba siempre a la pestaña "Centros de Gasto" (la
  marcada activa por defecto) y perdía cualquier filtro/orden
  aplicado -- verbatim: *"el que cambie la pestaña soy yo. No me la
  cambia el sistema [...] los filtros deben ser persistentes
  siempre."* Decisión explícita: tabla real en BD, nunca localStorage
  -- tiene que sobrevivir a cerrar el navegador o cambiar de
  dispositivo. Nuevo modelo `PanelNavigationState` (migración
  `0002_panelnavigationstate_s75`): una fila por
  `(company_user, screen_key)`, JSONField de forma libre
  (`active_tab` + `filters` por pestaña). `NavigationStateSaveView`
  (POST genérico por `screen_key`, merge superficial). El servidor
  restaura la pestaña activa y los filtros de Maquinaria al renderizar
  `hub.html` (`DocumentationHubV2View` + `_seed_request_get`), sin
  parpadeo; Personal/EPIs pasan de `hx-trigger="click once"` a
  `"load once"` cuando son la pestaña persistida, con sus filtros ya
  inyectados en la propia URL htmx. JS guarda `active_tab` en el
  evento `shown.bs.tab` (el usuario es el único que cambia de
  pestaña) y los filtros interceptando `htmx:afterRequest` sobre los
  endpoints de listado/resultados exclusivamente. Desplegado --
  **pendiente de verificación con datos reales por parte de Miguel
  Ángel** (la salida del Comando S de cierre de este bloque no trajo
  el bloque `git log`/`showmigrations`, se repitió el Comando S).
- **Incidencia real diagnosticada y CERRADA -- documentos con fecha de
  caducidad futura marcados `is_obsolete=True`** (Miguel Ángel: "he
  visto ya carnés que cumplen en 2030 y me los marca como
  obsoletos"). Diagnóstico completo contra BD real (hermanos: mismo
  tipo + mismo sujeto de cada una de las 11 filas): **no es un bug de
  código.** `is_current()`/`evaluate_substitution()` se comportan tal
  como están escritas. 10 de las 11 filas son duplicados reales del
  mismo ITV (dos escaneos del mismo documento, misma fecha exacta de
  caducidad, un hermano vigente y otro archivado -- el sistema no
  perdió ningún dato). La fila de `CARNET_CONDUCIR` sí es un hueco de
  calidad de dato real y distinto: el hermano que queda vigente tiene
  `expiry_date` vacío en BD pese a que el nombre del archivo dice
  2030 -- candidato a que Fase C le extraiga la fecha real algún día,
  no urgente, no bloquea nada. **`vigencia_service.py` NO se toca --
  el problema real es de presentación (ver punto 5 de la hoja de ruta
  S76: agrupar por familia, mostrar solo el vigente, historial aparte
  bajo demanda), ya cubierto por el rediseño planificado.**
- **Auditoría de dominio de `DOC. PERSONAL` -- CERRADA.** Catálogo
  completo confirmado: 73 tipos activos de dominio PERSONAL/BOTH (ver
  desglose completo por familia en el registro de sesión S75).
  Corregidos 3 tipos con dominio incorrecto, verificados con muestra
  real de nombres de archivo antes de tocar nada (nunca a ciegas):
  `CSS` (COMPANY -> PERSONAL, cuota de autónomo -- hermano de
  `AUTONOMO`), `SOLICITUD_ADMINISTRATIVA` (MACHINE -> PERSONAL,
  solicitudes de examen individuales), `CERTIFICADO_PODERES` (MACHINE
  -> COMPANY, mandatos/poderes de empresa, ni de máquina ni de
  persona concreta). `CE`/`POLIZA_SEGURO`/`SEGURO` confirmados
  correctos ya en `MACHINE`, sin cambio.
- **Deuda técnica de personas huérfanas -- CERRADA (Miguel Ángel,
  S75: "influye en la presentación de datos en la interfaz").** 1676
  documentos tipados como PERSONAL/BOTH sin ninguna persona vinculada
  (58 tipos distintos, `FORMACION` con 944 el mayor volumen).
  Reutilizadas las herramientas ya existentes (S58/S62, sin
  reinventar nada): `resolve_domain_pending_types --apply` resolvió
  229 por carpeta/nombre/ventana deslizante; `trash_orphan_
  personal_documents --apply` (mismo criterio S62/S73: no está entre
  los 70 activos -> papelera) mandó los 1447 restantes a papelera.
  0 fallos en ambos pasos. Verificación final contra BD: 0 huérfanos
  restantes en tipos PERSONAL/BOTH. Ningún archivo real se toca
  (4.12) -- papelera es escritura pura de índice, los 1447 siguen en
  GCS.
- **Directriz permanente confirmada por Miguel Ángel (S75):**
  extracción de datos (fechas/campos) siempre con OCR, nunca con
  Gemini (coste) -- Gemini queda como último recurso real (Fase C).
  El OCR nunca corre en la consola de PythonAnywhere -- corre en
  local o en VMs de nube programáticas (mismo patrón que
  `h28-ocr-batch`). Antes de tocar código de Google Cloud/Vertex
  AI/SDK, `web_search` obligatorio primero. Aplicará quien retome la
  Fase C de H30.

## 5.2. Hoja de ruta para S76 -- REDISEÑO DE LA INTERFAZ DE FICHA DE PERSONA (Miguel Ángel, S75)

Miguel Ángel replanteó una parte sustancial del hito tras ver la
ficha de persona real en producción -- verbatim: *"tú ya la habías
dado por construida y nos queda todavía un mundo hasta terminarla."*
Sustituye/amplía lo que quedaba de la hoja de ruta original de este
punto. Premisa que gobierna TODO lo siguiente: **UX por encima de
todo, cero scroll en pantallas normales (ordenador/tablet), cero
"selva documental"** -- el supervisor tiene que ver de un vistazo qué
puede hacer, sin explicaciones.

1. **Bug de vigencia (`is_obsolete`)** -- cerrar el diagnóstico
   iniciado en S75 (ver 5.1) y corregir la causa raíz real una vez
   confirmada con datos, nunca antes. Prioridad -- bug de integridad
   de datos, corrección inmediata en cuanto se confirme la causa
   (directriz de sesión, nunca deuda técnica).
2. **Modo edición con confirmación explícita en la ficha de persona**
   (requisito NUEVO, introducido en S75 -- no existía antes).
   Actualmente `PersonalUpdateView`/el formulario de
   `_personal_detail.html` son editables directamente sin ninguna
   barrera. Rediseño: los campos nacen de solo lectura; un botón
   "Modo edición" dispara un modal de confirmación ("¿Vas a activar
   el modo edición?" Aceptar/Cancelar); solo tras aceptar se habilitan
   los campos para editar. Objetivo explícito: que nunca se cambie un
   dato por error de un clic o un tabulado accidental.
3. **Reestructuración completa de la ficha de persona -- objetivo
   "todo visible sin scroll"**: cabecera fija con foto/nombre/
   domicilio/teléfono/correo (falta domicilio en el formulario actual
   -- revisar qué campos reales tiene `PersonIdentity` para dirección
   y si faltan, plantearlo con Miguel Ángel antes de inventar
   campos). El resto de la información (documentos, EPIs,
   notificaciones) organizado en bloques de acceso directo -- acordeón
   como opción por defecto, iconos cuadrangulares si el acordeón se
   queda corto para caber sin scroll. Responsive (ordenador/tablet)
   -- toda la información accesible en la misma pantalla sin scroll
   vertical largo.
4. **Documentos agrupados por familias de USO real, no por el campo
   `family` genérico actual del catálogo** -- Miguel Ángel dio
   ejemplos concretos a definir con él en la próxima sesión antes de
   tocar código:
   - "Documentación de circulación/habilitación" -- DNI, carné de
     conducir, carné de gruísta, permiso de circulación y cualquier
     otro documento que acredite para manejar máquinas o circular
     (lo que "se lleva en la cartera").
   - "Formación" -- formaciones recibidas, distinta de "certificados"
     (Miguel Ángel: "no es lo mismo un certificado que una formación
     recibida" -- valorar si son dos familias o una con subtipo).
   - "Nombramientos y poderes" -- nombramientos, poderes,
     autorizaciones de la empresa.
   - Definir el resto de familias reales revisando el catálogo
     completo de `DOC. PERSONAL` con Miguel Ángel -- no inventar una
     taxonomía sin su confirmación explícita.
5. **Dentro de cada familia, mostrar solo el documento VIGENTE por
   nombre de tipo, nunca el histórico completo de entrada** --
   ejemplo explícito de Miguel Ángel: un trabajador con 30-40 años en
   la empresa puede tener 30-40 reconocimientos médicos; la ficha
   solo debe mostrar "Reconocimiento médico" (el vigente), con un
   acceso aparte ("ver historial") para desplegar el resto bajo
   demanda -- nunca de primeras.
6. **Limpieza de nombres mostrados en la interfaz** -- Miguel Ángel,
   verbatim: *"estamos presentando los nombres de los archivos tal y
   como estaban en el disco [...] eso no es lo que dije."* En la
   ficha de persona, el nombre visible de cada documento debe ser
   siempre `document_type.label` (p. ej. "Reconocimiento médico",
   "DNI"), nunca `entry.name` crudo -- ya no hace falta repetir el
   nombre de la persona (se está en su ficha) ni la fecha de
   caducidad en el nombre (ya se ve en el propio bloque). El nombre
   real del archivo (`entry.name`, heredado del disco o del esquema
   de `naming_service`) queda como metadato interno, nunca como
   etiqueta visible al supervisor. Confirmado con datos reales (ver
   5.1) que los archivos siguen mostrando su nombre crudo de
   Microsoft 365 -- este punto lo corrige de raíz en la UI,
   independientemente de si el `blob_name`/`name` real se renombra o
   no (4.12: `blob_name` nunca se reescribe, así que la limpieza es
   puramente de presentación, vía `document_type.label`).
7. **Desplegables con autocompletado y, donde la lista de opciones
   sea larga, desplegables en cascada** (una opción despliega el
   siguiente nivel de opciones relacionadas, patrón árbol) -- aplicar
   donde corresponda dentro de todo lo anterior (selección de tipo
   documental, de EPI, de familia, etc.).

**No iniciar el punto 4 (definición de familias) sin antes acordar
con Miguel Ángel la lista real de familias y qué tipos documentales
entra en cada una** -- es una decisión de producto, no una que el
modelo pueda tomar solo por analogía. El resto de puntos (1, 2, 3, 6,
7) sí tienen alcance suficientemente claro para empezar sin más
preguntas bloqueantes.

---

## 4.1. Pendiente real, posterior a la interfaz (nota de Miguel Ángel, S73)

Una vez cerrada la interfaz de este hito: revisar que todos los tipos
documentales de `DOC. PERSONAL` tienen el campo `domain` correcto en
`DocumentTypeCatalog` -- verbatim, Miguel Ángel: "creo que ya lo
tenemos todo tipificado, pero no sé si lo tenemos todo en los
dominios correctos [...] habrá que mirar todo lo que hay en personal
y ver si está perfectamente dominado." No confundir con volver a
tipificar (eso ya está cerrado) -- es una auditoría del campo
`domain` (`PERSONAL`/`MACHINE`/`BOTH`/`COMPANY`) sobre el catálogo ya
existente, corrigiendo caso por caso lo que esté mal asignado.
