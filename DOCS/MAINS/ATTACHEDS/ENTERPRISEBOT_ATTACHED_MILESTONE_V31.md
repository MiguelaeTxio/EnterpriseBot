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

## 5.3. COMPLETADAS EN S76

Sesión larga, misma continuación de S75 -- Miguel Ángel confirmó la
familia genérica actual del catálogo como base del acordeón ("está
bien, voy a echarle un vistazo") y pidió avanzar directamente sobre
puntos 1/2/3/5/6 de la hoja de ruta de arriba, dejando el punto 4
(definición fina de familias de uso real) explícitamente pendiente de
acuerdo, y el punto 7 (cascada de desplegables) sin empezar todavía.

- **Punto 1 (bug de vigencia) -- CERRADO sin tocar código.**
  Diagnóstico completo con datos reales (hermanos de las 11 filas
  candidatas): no es un bug de `vigencia_service.py` -- 10/11 son
  duplicados reales de ingesta (mismo ITV, misma fecha, un vigente y
  un archivado correctamente), 1/11 es un hueco de dato real
  (`expiry_date` vacío pese a fecha en el nombre del archivo).
  Resuelto por diseño con el punto 5 (agrupación + historial aparte).
- **Punto 2 (modo edición con confirmación) -- CERRADO** (commit
  `3282b1e`): campos `readonly` por defecto, botón "Modo edición" →
  modal de confirmación → solo al aceptar se habilita la edición.
- **Punto 3 (reestructuración sin scroll) -- CERRADO en dos pasadas**:
  acordeón por familia real del catálogo primero (`3282b1e`), y
  reestructuración completa en TRES acordeones principales -- Datos
  personales, Documentación, EPIs -- con acordeones internos anidados
  dentro (`b0e4bc5`), a petición explícita de Miguel Ángel tras ver
  los EPIs sueltos fuera de cualquier acordeón. `data-bs-parent` en
  todos los niveles para que abrir un panel cierre los demás (petición
  explícita, "cuando se abre un acordeón se cierran los demás").
  Corrección posterior (`1035c83`): quitados los badges numéricos de
  "Documentación"/"EPIs" en el acordeón principal -- Miguel Ángel
  detectó que no coincidían con lo que se ve al abrir (contaban el
  histórico completo, no la lista ya deduplicada).
- **Punto 5 (solo el vigente, historial aparte) -- CERRADO** para
  documentos (`3282b1e`, `PersonalDocumentTypeHistoryView`) y para
  EPIs (`f5097cf`, `_group_epi_deliveries_by_family()` +
  `PersonalEpiItemHistoryView`) -- mismo modal genérico de historial
  reutilizado para ambos (`openHistoryModal()`).
- **Punto 6 (nombres limpios) -- CERRADO**: `document_type.label` en
  vez de `entry.name` crudo en toda la ficha (`3282b1e`).
- **Casillero Activos/Inactivos + Empresa en el listado Personal**
  (`41c5fbe`), no estaba en la hoja de ruta original pero surgió de
  una petición real de Miguel Ángel sobre el volumen de personal
  inactivo visible. Semántica literal de checkbox, empresas reales
  confirmadas contra BD (`GRUAS ADOLFO ALVAREZ SL`, `TRANSGRUAL SL` +
  variantes, `GRUALDI S.L`, `ASIST.GRUAS GRANADA`), Inactivos =
  `is_active_employee=False` **o** `None` juntos (decisión explícita:
  el histórico real nunca se marcó `False` a propósito). Vista inicial
  por defecto Activos + todas las empresas, luego persistido por
  usuario (`PanelNavigationState`, ya extensible desde S75).
- **Deuda técnica de 1676 documentos sin persona asignada -- resuelta
  de verdad**, reutilizando `resolve_domain_pending_types`/
  `trash_orphan_personal_documents` (S58/S62, sin reinventar nada):
  229 resueltos, 1447 a papelera, 0 huérfanos restantes verificado
  contra BD.
- **Auditoría de dominio `DOC. PERSONAL` -- cerrada**: 73 tipos
  PERSONAL/BOTH confirmados, 3 corregidos con evidencia real de
  nombre de archivo (`CSS`, `SOLICITUD_ADMINISTRATIVA` → PERSONAL;
  `CERTIFICADO_PODERES` → COMPANY).
- **Dirección postal + fecha de alta/baja + icono de edición de
  avatar** (`3df55c9`, migración `0063`): `address_street`/
  `postal_code`/`city`/`province`/`hire_date`/`termination_date`
  nuevos en `PersonIdentity`, editables desde el panel (no vienen del
  Excel). Icono de cámara sobre el avatar, reutiliza `openUploadForm`.
- **Incidencia real -- comentarios Django `{# #}` multilínea se
  mostraban como texto literal en producción** (`f253414`): bug propio
  introducido en S75/S76, corregido convirtiendo a
  `{% comment %}...{% endcomment %}` en los 5 sitios afectados,
  verificado que no había ningún otro caso en todo el repositorio.
- **Regla de diseño permanente: filas alternas gris/blanco en TODAS
  las tablas del panel** (`c8ab3b7`): CSS global en `panel.css`
  (`.table:not(.table-striped)`), no tocar tabla por tabla.
- **Incidencia real -- checkboxes de Activos/Empresa desincronizados
  de los resultados tras recargar** (`0e88e4a`): Chrome restauraba el
  estado de checkboxes de una carga anterior después de que Django ya
  había pintado el HTML real, dejando pantalla y datos
  desincronizados. Corregido con `autocomplete="off"` en el
  formulario.
- **Directriz permanente confirmada por Miguel Ángel: toda pantalla
  nueva del panel debe persistir su navegación por usuario**
  (`72ec21c`, documento maestro §4.15) -- `PanelNavigationState`/
  `NavigationStateSaveView` ya son genéricos por `screen_key` desde
  S75, reutilizables sin construir nada nuevo por pantalla.
- **Columna "Método" de EPIs sustituida por ficha técnica/manual real,
  con corrección de duplicación en la misma sesión**:
  - Primer intento (`8aee11e`, migración `0064`): campo
    `EpiItemCatalog.technical_sheet` (FK única) -- **error real, sin
    comprobar antes si ya existía un mecanismo.**
  - Corregido en el mismo bloque de trabajo (`51ee669`, migración
    `0065`): ya existía desde H30 S73 un mecanismo real y con 7
    documentos reales ya vinculados
    (`DocumentIndexEntry.domain_content_type`/`domain_object_id`
    apuntando a `EpiItemCatalog`, mismo patrón que
    `PersonIdentity`/`MachineAsset`), que además soporta varios
    documentos por EPI (caso real: ficha técnica + declaración de
    conformidad) frente a la FK única que se había creado. Campo
    nuevo retirado sin pérdida de datos (nunca llegó a rellenarse),
    vista de subida reescrita sobre el mecanismo real. **Lección:
    antes de añadir un campo/mecanismo nuevo, buscar primero en el
    propio anexo si ya existe uno -- mismo principio que la
    verificación de campos de modelo (directriz 4.14), aplicado ahora
    también a nivel de arquitectura, no solo de nombres de campo.**

---

## 5.4. Hoja de ruta para S77 -- ACORDEÓN LABORAL (Miguel Ángel, S76, cierre de sesión)

Petición para la próxima sesión, verbatim: *"vamos a incluir también
en la ficha de personal los partes de trabajo y vacaciones [...] un
acordeón que se llame Laboral [...] dentro de Laboral: dietas, partes
de trabajo, vacaciones, bajas [...] incapacidad laboral transitoria y
enfermedad común, accidente laboral, enfermedad laboral."*

**Investigación real hecha en el cierre de S76, antes de escribir
esta hoja de ruta (para no repetir el error de `technical_sheet` --
comprobar primero qué ya existe):**

1. **Vacaciones -- YA EXISTE modelo real, no construir nada nuevo.**
   `hr_calendar.VacationPeriod` (H24): `operator` es FK a
   `ivr_config.CompanyUser` (no a `PersonIdentity` directamente) --
   pero `PersonIdentity.company_user` (OneToOne, S74) ya tiende el
   puente. El acordeón Laboral > Vacaciones debe **consultar y
   mostrar** `VacationPeriod` filtrado por
   `operator=person.company_user`, nunca duplicar el modelo. Personas
   sin `company_user` vinculado no tendrán vacaciones que mostrar por
   esta vía -- confirmar con Miguel Ángel si eso es aceptable o si
   hace falta otro puente para el personal sin cuenta de panel.
2. **Partes de trabajo -- YA EXISTE el pipeline real
   (`work_order_processor.WorkOrder`/`WorkOrderEntry`), pero el
   vínculo al trabajador NO es una FK.** `WorkOrderEntry.worker_name`
   es texto libre derivado del nombre de archivo del PDF ("para evitar
   variantes ortográficas" según su propio docstring) -- **no hay hoy
   una forma fiable de filtrar partes de un `PersonIdentity` concreto
   sin resolver por nombre, el mismo problema de fondo que ya se ha
   dado en otros puntos del proyecto.** Antes de construir el
   acordeón Laboral > Partes de trabajo hay que decidir con Miguel
   Ángel: (a) resolver por nombre con el mismo criterio ya usado en
   `run_fase_a_sweep`/`resolve_domain_pending_types` (folder/nombre/
   ventana deslizante), aceptando que no será 100% fiable, o (b)
   quedarse solo con un enlace al explorador filtrado por nombre,
   sin intentar una vinculación exacta. **No decidir esto sin
   Miguel Ángel -- es una decisión de producto, no técnica.**
3. **Dietas -- YA EXISTE el dato real (`WorkOrderEntry.has_diet`,
   booleano por parte/jornada), pero Miguel Ángel pidió
   explícitamente un PLACEHOLDER por ahora** ("Alejandro me lo acaba
   de decir hoy [...] ahora mismo es un placeholder hasta que le
   metamos mano, pero bueno, que ya esté ahí"). Criterio de cierre
   del placeholder: una entrada "Dietas" visible dentro del acordeón
   Laboral, con un mensaje claro de "en construcción" -- sin lógica
   real todavía, sin prometer un cálculo o listado que no existe.
4. **Bajas médicas (incapacidad temporal) -- NO existe hoy ningún
   modelo estructurado**, solo tipos documentales sueltos
   (`PARTE_BAJA_MEDICA`, 250 documentos reales; `BAJA_PERSONAL`, 684,
   que es baja de Seguridad Social, no médica). Investigado en la web
   antes de escribir esto (petición explícita de Miguel Ángel):
   categorías reales españolas según el Ministerio de Trabajo/LGSS --
   **contingencias comunes** (enfermedad común, accidente no laboral)
   y **contingencias profesionales** (accidente de trabajo, enfermedad
   profesional), más maternidad/paternidad, riesgo en
   embarazo/lactancia y (desde 2023) situaciones de salud
   menstrual/reproductiva. Miguel Ángel mencionó explícitamente
   "incapacidad laboral transitoria y enfermedad común, accidente
   laboral, enfermedad laboral" -- encaja con las categorías reales de
   contingencia común/profesional. **Decisión pendiente con Miguel
   Ángel**: ¿construir un modelo real nuevo (fecha inicio/fin,
   categoría de contingencia, documento de origen) o empezar mostrando
   solo los documentos ya tipados (`PARTE_BAJA_MEDICA`) agrupados,
   sin modelo estructurado todavía?

**Criterio de cierre de S77 (a proponer, confirmar con Miguel Ángel al
arrancar):** al menos el acordeón Laboral construido con sus
secciones (Dietas como placeholder explícito, Vacaciones conectado a
`VacationPeriod` real, Bajas mostrando al menos los documentos ya
tipados) verificado contra BD real de al menos una persona con datos
reales en cada sección. Partes de trabajo queda condicionado a la
decisión del punto 2 -- no bloquea el resto si Miguel Ángel necesita
tiempo para decidirlo.

**Si al valorarlo mañana el volumen de trabajo del acordeón Laboral
parece demasiado grande para seguir dentro de H31, Miguel Ángel dejó
dicho explícitamente que se puede abrir como hito aparte (PCH) -- su
impresión inicial es que cabe bien dentro de H31, pero la decisión
final se toma al arrancar S77, no ahora.**

---

## 5.5. COMPLETADAS EN S77 y PAUSA DEL HITO

**Acordeón Laboral + Salud construido y verificado contra ficha real
(Alejandro García Luque, pk=158):**

- `LABORAL` y `SALUD_BAJAS_PERSONA` sacadas de dentro de "Documentación"
  a dos acordeones propios de primer nivel (mismo documento, sin
  duplicar -- `_group_current_by_family(exclude_family_codes=...)`).
  `SALUD_BAJAS_PERSONA` ES el bloque de Bajas -- sin acordeón aparte
  (decisión de Miguel Ángel S77, para no duplicar ni chocar de nombre
  con la family documental "Laboral" ya existente).
- Vacaciones: `VacationPeriod` real, filtrado por
  `operator=person.company_user`, solo lectura por ahora.
- Dietas: placeholder ("En construcción"), tal cual pedido en S76.
- Partes de trabajo -- decisión de vinculación tomada (punto 2 de
  arriba, ya resuelto, retirado de pendiente): `DIGITAL`
  (`uploaded_by` fiable, el propio operario autenticado) +
  histórico `PDF_UPLOAD` resuelto por nombre normalizado (mayúsculas,
  sin acentos, espacios colapsados) -- sondeo real S77: 504/545
  entradas (92.5%) casan exacto; el resto (41, "Juan Antonio Galván
  Ramos", sin `PersonIdentity` en la plantilla activa) queda sin
  vincular a propósito, nunca por parecido de apellido.
  `GENERATED` (tarea fantasma de vacaciones) explícitamente excluida
  -- ya se ve en el bloque Vacaciones, no es trabajo real.
- Miguel Ángel, verbatim, tras ver el primer listado plano: "no sirve
  de nada ver un listado [...] qué sentido tiene eso para un
  supervisor [...] quiero saber las horas que ha echado, en qué
  máquina ha estado trabajando, el parte del día resumen con toda la
  hora del periodo." Sustituido por resumen agregado
  (`_partes_summary()`): horas totales del periodo, horas por
  máquina, resumen diario -- reutiliza `WorkOrderEntryLine.delta_hours`
  con el mismo criterio de exclusión de la hora fantasma de vacaciones
  que ya usa el Laboratorio de Análisis
  (`AnalyticsLabDataView._line_cost`).
- Filtro real de Partes de trabajo: periodo de cobro REAL
  (`ivr_config.WorkPeriod`, no el mes natural -- 21 a 20 del mes
  siguiente para horas extra), rango manual de fechas, orden.
  **Periodo ACTIVO por defecto** (el que cubre hoy), nunca "Todos" --
  reutiliza `_resolve_work_period()` del Laboratorio de Análisis tal
  cual, sin reinventar el criterio.
- Detalle real de un día concreto (`PersonalWorkdayDetailView`),
  formato documento en modo solo lectura -- mismas secciones que
  `form_entry.html` (fecha, dieta, pausa de comida; por tarea:
  máquina, H.C./H.F., horas, O.R., avería, reparación, in situ,
  ticket, repuestos, fotos) pero sin `<input>`, sin ayudas, sin modo
  edición. Fotos reutilizan `_build_photo_entries()`
  (`panel/views_task_photos.py`) tal cual para la URL firmada de GCS.
- **Incidencia real en producción, corregida en la misma sesión**: al
  sustituir el listado plano por el resumen agregado se dejó un badge
  del template referenciando variables retiradas del contexto
  (`VariableDoesNotExist`, `/panel/documentacion/personal/158/`) --
  corregido, y desde entonces se aplica una comprobación cruzada
  automática (variables del template vs. claves reales del contexto)
  antes de cada commit sobre este archivo.

**Bloqueo real que PAUSA el hito, descubierto en S77 verificando el
"galimatías" de Documentos que Miguel Ángel señaló** (ver captura de
la ficha de Alejandro García Luque: "Informe de Datos para la
Cotización" x3, "Alta (Seguridad Social)" x3, "Nómina" x3...):

`vigencia_service.is_current()` YA sabe archivar por `issue_date`
("el más reciente de su tipo es el vigente") -- pero si `issue_date`
está vacío, la propia función lo da por vigente por defecto ("sin
fecha, no hay base para archivar, nunca se archiva a ciegas"). Sondeo
real S77 contra producción: familias `LABORAL` + `SALUD_BAJAS_PERSONA`,
**6.085 documentos, 0% con `issue_date`/`expiry_date` extraído.**
Reparto real:

| Tipo | Documentos |
|---|---|
| Declaración de estar al corriente en el pago de salarios (por obra) | 1.762 |
| Baja (Seguridad Social) | 683 |
| Reconocimiento médico | 672 |
| Investigación de accidente laboral | 661 |
| Contrato laboral | 430 |
| Registro de jornada / control horario | 335 |
| Alta (Seguridad Social) | 330 |
| Informe de Datos para la Cotización | 250 |
| Parte de baja médica (incapacidad temporal) | 250 |
| Certificado de estar al corriente (Seguridad Social) | 220 |
| Modelo 145 | 160 |
| Nómina | 83 |
| Parte de vacaciones | 74 |
| Resto (19 tipos, 1 a 63 documentos cada uno) | ~140 |

Miguel Ángel, verbatim: "tenemos que detener y volver a H30 [...]
para ingesta de datos [...] ya lo tenemos todo tipificado, ya lo
tenemos todo con su dominio [...] lo que nos falta es meter todos
esos datos en base de datos." Sin esto, la interfaz de Documentación
no se puede verificar de verdad -- no hay forma de saber si
`_split_current_obsolete()` está funcionando bien o simplemente no
tiene con qué trabajar. **HITO PAUSADO al cierre de esta sesión,
PCH a H30** -- ver `ENTERPRISEBOT_ATTACHED_MILESTONE_V30.md` para la
hoja de ruta de la ingesta.

**Pendiente real para cuando H31 se retome** (nada se pierde, solo
espera a que H30 cierre la ingesta):

1. Pestaña "Vacaciones" real en el hub de Documentación (CRUD
   completo reescrito a htmx, adaptando
   `VacationPeriodListView`/`Create`/`Update`/`Delete` de
   `hr_calendar/views.py`, hoy páginas completas con redirect) --
   concertado en S77, no construido todavía. Una vez exista, retirar
   el enlace "Vacaciones" del sidebar de Administración (gate
   ADMIN/SUPERVISOR) -- "Calendario" (`hr_calendar:calendar`) se
   queda donde está, no se toca.
2. Bajas médicas (incapacidad temporal) -- decisión pendiente sin
   resolver todavía (punto 4 de la sección 5.4 de arriba): ¿modelo
   estructurado nuevo o solo los documentos ya tipados agrupados?
3. Una vez H30 extraiga `issue_date`/`expiry_date` de estos tipos,
   volver a verificar la ficha de Alejandro García Luque (u otra con
   volumen real) para confirmar que el acordeón Laboral/Salud/
   Documentación ya solo muestra el documento vigente de cada tipo,
   con el resto accesible vía "Historial" -- este es el verdadero
   criterio de cierre de la interfaz, no solo que el código compile.
4. Verbatim S73 (fase de auditoría de `domain`, sección 4.1 de abajo)
   sigue pendiente, sin relación con lo de arriba.

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

---

## Registro de sesión (reubicado desde V30, S78 -- estaba mal pegado
## en el anexo de H30 por error, corregido según directriz 4.9)

EOF
# 2026-08-28
# EnterpriseBot
# ENTERPRISEBOT_ATTACHED_MILESTONE_V31.md
*  **Session:** Acordeón Laboral en ficha de personal: Dietas, Vacaciones y Bajas médicas
*  **Description:** Sesión de continuidad de H31 (Interfaz de Ficha de Personal: EPIs y Notificaciones/Circulares), sobre la petición de Miguel Ángel en el cierre de S76: incluir en la ficha de persona un nuevo acordeón "Laboral" con Dietas, partes de trabajo, vacaciones y bajas (incapacidad temporal por contingencia común y profesional). Se construirá el acordeón con al menos: Dietas como placeholder explícito ("en construcción", sin lógica real todavía, según petición literal de Miguel Ángel); Vacaciones conectado a hr_calendar.VacationPeriod real vía PersonIdentity.company_user, sin duplicar el modelo; Bajas mostrando al menos los documentos ya tipados (PARTE_BAJA_MEDICA) agrupados. Antes de tocar el punto de Partes de trabajo se decidirá con Miguel Ángel el criterio de vinculación (resolución por nombre vs. enlace al explorador filtrado), dado que WorkOrderEntry.worker_name es texto libre sin FK fiable a PersonIdentity. Se confirmará también si el volumen del bloque completo aconseja abrirlo como hito aparte (PCH) o seguir dentro de H31. Criterio de cierre: acordeón Laboral verificado contra BD real de al menos una persona con datos reales en cada sección construida esta sesión.

EOF
