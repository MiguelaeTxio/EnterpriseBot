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

## 5. Hoja de ruta para S75

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
4. **Auditoría de integridad de datos ampliada** (nace de la
   incidencia de S74): la auditoría Excel vs BD de esta sesión se
   hizo a mano, sobre un caso concreto que saltó a la vista en el
   panel. Valorar con Miguel Ángel si conviene un comando de gestión
   real (`audit_person_identities_against_excel` o similar) que
   automatice la comparación nombre+DNI completa cada vez que se
   suba un Excel nuevo, en vez de repetirla a mano. No iniciar sin
   que Miguel Ángel lo pida explícitamente -- consultar primero.

Criterio de cierre de S75: al menos el punto 1 o el punto 2
completado y verificado contra BD, no solo diseñado.

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
