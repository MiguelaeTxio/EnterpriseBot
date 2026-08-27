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

- Cualquier vista/acción de ESCRITURA: entregar EPI, enviar
  notificación, editar ficha de persona, subir foto de carné.
- Selector de personal con casillero para acciones masivas.
- Modelo de contenido de circular/notificación (título, cuerpo con
  formato básico -- colores de fondo/carácter, selección de fuente
  entre pocas opciones) más allá del propio `DocumentIndexEntry` de
  plantilla vigente. Decidir en la primera sesión si el cuerpo vive
  en un campo de texto enriquecido nuevo o si la plantilla vigente
  sigue siendo un archivo real (docx/pdf) sin editor propio -- Miguel
  Ángel pide explícitamente un editor básico integrado, así que
  probablemente hace falta un campo de contenido editable, no solo
  el archivo.
- Importación de Word/PDF para crear o sustituir una circular
  (convertir a la representación interna que se decida en el punto
  anterior).
- Cualquier flujo de envío/notificación real (¿email vía
  `document_management.EmailTemplate` de H26, WhatsApp vía la app
  `whatsapp` ya existente, o simple registro de
  `DocumentAcknowledgment` sin canal de envío real? -- decidir con
  Miguel Ángel en la primera sesión, no asumir).

---

## 3. Hoja de ruta para la primera sesión de H31

1. **Preguntas de diseño RESUELTAS (S73):**
   - **Cuerpo editable de circular/notificación**: campo de texto
     enriquecido NUEVO en BD -- decisión explícita de Miguel Ángel,
     con la advertencia real de que hay que mantener el legacy
     (`current_template`/archivo de plantilla) en paralelo, no
     sustituirlo de golpe.
   - **Envío**: NO WhatsApp para este tipo de comunicación con
     documentos -- correo electrónico vía `mailto:` con asunto+cuerpo
     precargados, que abre el cliente de correo por defecto del
     usuario (Outlook). Mismo criterio ya usado en H26
     (`document_management.EmailTemplate`, "cuerpo copiar/pegar +
     PDF generado aparte, nunca envía él mismo") -- nunca se manda
     nada por SMTP/API desde el propio EnterpriseBot, solo se prepara
     el mensaje y se abre el cliente.
   - **Foto de carné**: confirmado, YA existen 108 imágenes reales
     (`document_type=IMAGEN`) vinculadas vía
     `domain_content_type`/`domain_object_id` a su `PersonIdentity`
     -- sin campo dedicado en el modelo. La ficha de persona debe
     BUSCAR ese vínculo ya existente (mismo mecanismo genérico que
     `EpiDelivery`/fichas técnicas) y mostrarlo como avatar, con un
     icono de persona genérico como placeholder si no hay ninguna
     vinculada. No hace falta campo nuevo.
2. **Ficha de persona editable**: formulario sobre `PersonalDetailView`
   (o vista nueva de edición) para los campos reales de
   `PersonIdentity`, más subida de foto de carné si no existe ya el
   mecanismo.
3. **Entrega individual de EPI** desde la ficha: desplegable de
   `EpiItemCatalog` + fecha, crea `EpiDelivery(extraction_method=MANUAL)`.
4. **Envío individual de notificación** desde la ficha: desplegable
   de `DocumentTypeCatalog` (los tipos tipo circular/nombramiento),
   crea `DocumentAcknowledgment(extraction_method=MANUAL)`.
5. **Selector masivo con casillero** + acción masiva de EPI y de
   circular (mismo backend que los puntos 3-4, en bucle sobre las
   personas seleccionadas).
6. **CRUD de circulares**: crear/editar/importar, actualizando
   `DocumentTypeCatalog.current_template` de forma consistente con el
   mecanismo ya en uso.
7. **Editor de texto básico** integrado en el CRUD (colores, pocas
   fuentes) -- alcance deliberadamente reducido, sin funcionalidades
   de procesador de textos avanzado.

Criterio de cierre de la primera sesión: al menos el punto 1
(preguntas resueltas) y un punto de acción real (2 o 3) completado y
verificado contra BD, no solo diseñado.

---

## 4. Pendiente real, posterior a la interfaz (nota de Miguel Ángel, S73)

Una vez cerrada la interfaz de este hito: revisar que todos los tipos
documentales de `DOC. PERSONAL` tienen el campo `domain` correcto en
`DocumentTypeCatalog` -- verbatim, Miguel Ángel: "creo que ya lo
tenemos todo tipificado, pero no sé si lo tenemos todo en los
dominios correctos [...] habrá que mirar todo lo que hay en personal
y ver si está perfectamente dominado." No confundir con volver a
tipificar (eso ya está cerrado) -- es una auditoría del campo
`domain` (`PERSONAL`/`MACHINE`/`BOTH`/`COMPANY`) sobre el catálogo ya
existente, corrigiendo caso por caso lo que esté mal asignado.
