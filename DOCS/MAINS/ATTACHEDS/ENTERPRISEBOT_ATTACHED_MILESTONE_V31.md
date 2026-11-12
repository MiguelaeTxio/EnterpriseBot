# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V31.md
# Anexo H31 — Interfaz de Gestión Documental de Personal: Altas, Bajas, Sustituciones, EPIs y Circulares

---

**REACTIVADO EN S110** (PCH desde H36, cerrado por completo en la
misma sesión -- ver "COMPLETADAS EN S110 -- H36 CERRADO POR COMPLETO"
en `ENTERPRISEBOT_ATTACHED_MILESTONE_V36.md` para el detalle
completo). Hoja de ruta de arranque intacta desde S99, sin reescribir
-- los 3 puntos siguen tal cual, empezando por el punto 3 (enviar un
dossier real con firma y confirmarlo visualmente en Outlook real),
que es precisamente el que motivó el desvío a H36 en S109.

## COMPLETADAS EN S110

Ningún trabajo de ejecución sobre H31 en esta sesión -- la sesión
completa (S110) se dedicó a H36 (retipado de cursos de formación),
cerrado del todo (ver "COMPLETADAS EN S110 -- H36 CERRADO POR
COMPLETO" en `ENTERPRISEBOT_ATTACHED_MILESTONE_V36.md`). Miguel Ángel
pivotó (PCH) de vuelta a H31 al cierre de esta misma sesión para
retomarlo en la sesión siguiente.

## COMPLETADAS EN S108

Ningún trabajo de ejecución sobre H31 en esta sesión -- la sesión
completa (S108) se dedicó a H35 (retipado/refechado masivo de
documentación histórica de personal), cerrado del todo en la misma
sesión (ver "COMPLETADAS EN S108 -- H35 CERRADO POR COMPLETO" en
`ENTERPRISEBOT_ATTACHED_MILESTONE_V35.md` para el detalle completo:
118 candidatos de otra persona revisados, 3 bugs reales corregidos en
`is_current()`/`backfill_obsolete_duplicates`/`db_query.yml`, 3
migraciones nuevas de catálogo). Al cerrar H35, Miguel Ángel pivotó
(PCH) a H31 para retomarlo en la sesión siguiente, y cerró esta misma
sesión (PCS) inmediatamente después sin ejecutar nada más -- de ahí
que la hoja de ruta de abajo llegue sin avance real desde su última
ejecución en S104.

## COMPLETADAS EN S109 -- PAUSADO por PCH a H36 (retipado de formación)

Sesión que arrancó ejecutando ampliaciones reales a la hoja de ruta de
H31, planteadas por Miguel Ángel sobre la marcha (grupos de reparto,
agrupación de formación por curso, triángulo de alerta con detalle,
avisos WhatsApp configurables, firma digital genérica):

1. **Grupos de reparto** (`PersonGroupTemplate`, migración `0096`):
   conjunto guardado de personas, sin FK a Company a propósito (cruza
   empresas por diseño -- caso real de chalecos de alta visibilidad a
   choferes de varias empresas). Selector "Grupo de reparto guardado"
   + botón "Guardar selección como grupo" en `_personal_pane.html`,
   sobre el mismo Set `selection` que ya acumulaba el frontend --
   ninguna de las 3 vistas de acción masiva existentes se tocó.
   Verificado real en producción (`django_migrations`, `applied`
   real). Commit `f140ba5`.
2. **Triángulo de alerta con detalle real**: `_attach_alert_flags`
   ahora adjunta `alert_labels` (tipos exactos que disparan la
   alerta) en vez del tooltip genérico de antes; en la ficha de
   persona, el mismo triángulo aparece también a nivel de cabecera de
   familia (Laboral, Salud, acordeón genérico), combinando tipos que
   faltan (`missing_types_by_family`, ya existente) con tipos
   caducados (`attention_types_by_family`, nuevo). Filtro de plantilla
   `get_item` nuevo para el lookup dinámico del acordeón genérico. Sin
   migración. Commit `c0bc55c`.
3. **Catálogo de 14 tipos de curso de FORMACION** (migración `0097`,
   dominio PERSONAL, familia PRL_FORMACION, `tracks_expiry=True`,
   `is_cumulative=True`), confirmados contra el Excel real de Miguel
   Ángel (hoja "CURSOS TRABAJADORES GRUAS"). Verificado real en
   producción (17 filas `FORMACION_%` confirmadas por consulta SQL de
   solo lectura). Junto a esto, nueva directriz **4.22** del documento
   maestro: ningún tipo nuevo se deja sin retipar su histórico.
   Commit `98d71a9`.

**Al plantear el retipado real del punto 3** (los documentos que hoy
llevan el tipo genérico `FORMACION`), la consulta real reveló un
volumen -- 1.182 documentos de 67 trabajadores activos (tras acotar a
activos por decisión explícita de Miguel Ángel, dejando fuera 414
documentos de 95 inactivos) -- mayor que el que motivó H35 en su
momento. Miguel Ángel decidió explícitamente abrir esto como su
propio hito (**H36**, ver `ENTERPRISEBOT_ATTACHED_MILESTONE_V36.md`)
en vez de seguir como punto de H31, y trabajarlo "en caliente" en la
misma sesión (PCH CASO C, desvío). Con esto se PAUSA H31 y se PCH a
H36, EN PROGRESO.

**Los puntos 2 (formación) y 4 (firma digital genérica) quedaron
sin cerrar del todo** -- el resto de tipos de curso ya sembrados
cubre solo la parte de catálogo del punto 2 (el retipado real es
ahora H36); el punto 4 (firma con el dedo/ratón vía link, genérica
para EPI/información/cualquier firma) se planteó y se diseñó a nivel
conceptual pero no se llegó a implementar en esta sesión -- queda
como parte de la hoja de ruta de H31 al reactivarse.

## COMPLETADAS EN S109 (continuación -- desvío de sesión tras el PCH a H36)

Con H36 ya `EN PROGRESO` y sus 12 shards de OCR corriendo de fondo en
las VMs efímeras, Miguel Ángel pidió atender en la misma sesión una
serie de mejoras reales sobre H31 mientras la campaña avanzaba sola
(Caso A de `nfs-enterprisebot-pch`, desvío de sesión -- el marcador
`← EN PROGRESO` de H36 no se movió):

1. **EPIs en plantillas de dosier** (`PersonalDossierTemplate.epi_items`,
   M2M a `EpiItemCatalog`, migración `0099`): al aplicar una plantilla
   se resuelven las entregas reales (`EpiDelivery`) de cada EPI
   marcado para la persona concreta, añadiendo una sección propia al
   PDF/ZIP generado (`_build_epi_section_page`) -- **deliberadamente
   sin ningún bloque de firma todavía**, con aviso visible de que no
   sirve como acreditación ante terceros hasta integrar un proveedor
   de firma electrónica homologado (comparativa real Docuten/
   Signaturit/Viafirma hecha en la propia sesión, sin decisión de
   negocio tomada -- ver hoja de ruta). Conectado en los 3 flujos
   reales que usan plantilla (aplicar individual, envío por correo,
   generación masiva). Commit `7b6d57b`.
2. **Puestos de trabajo** (`JobPosition`, migración `0100`): catálogo
   de puestos con sus tipos documentales obligatorios ("plantilla de
   puesto", misma mecánica que las de dosier), `PersonIdentity.
   job_position` (FK nullable). El aviso de documento FALTANTE en la
   ficha (`missing_required_types_by_family`) pasa a depender
   exclusivamente del puesto de la persona, nunca del catálogo
   completo de 70-80 tipos -- Miguel Ángel, verbatim: *"no es cuestión
   de marcar cuando falte uno de los 70 u 80 tipos [...] sino de los
   documentos que realmente son necesarios [...] dependiendo del tipo
   de puesto que cada trabajador desempeña."* DNI/NIE tratados como
   excluyentes (tener uno cubre el requisito de identidad). Asignación
   masiva de puesto sobre el mismo Set `selection` de siempre
   (`PersonMassSetJobPositionView`) -- sustituye siempre el puesto
   anterior, nunca lo acumula. **Dos bugs reales corregidos en el
   mismo mecanismo, ambos con caso real de Miguel Ángel**: (a) el
   listado de Personal nunca reflejaba el aviso de obligatorio
   faltante, solo el de caducado (`_attach_missing_required_alert`
   nueva, commit `5d965f6`); (b) la ficha individual seguía contando
   un tipo como "presente" aunque estuviera marcado `is_obsolete=1`
   (reutilizaba por error `present_type_codes`, pensada a propósito
   para el botón "+ Subir" -- nueva `present_current_type_codes`,
   solo vigentes, commit `32a0427`, encontrado al retipar un documento
   real de Daniel Anaya). Commits `1cb9835`, `4555c61`, `32a0427`.
3. **Triángulo de aviso propagado al primer nivel "Documentación"**
   (`documentacion_has_alert`): el acordeón que envuelve las familias
   genéricas (Circulación, Administrativo, Identidad y personal...)
   no heredaba el aviso de sus hijas, a diferencia de Salud/Laboral
   (que son familia y primer nivel a la vez). Commit `f19bee4`.
4. **Mecanismo nuevo "Cambiar tipo" de un documento suelto**
   (`DocumentChangeTypeView`, genérico personal/máquina): no existía
   ningún camino en el panel para corregir la clasificación de UN
   documento sin montar una campaña completa de retipado por OCR en
   VMs -- origen real: una carta de baja voluntaria de Daniel Anaya
   tipada como `CONTRATO` por un falso positivo de la señal de
   contenido "CONTRATO DE TRABAJO" (mencionada de pasada en la
   cláusula de preaviso de la propia carta). Corregido por Miguel
   Ángel en el momento, a `CARTA_BAJA_VOLUNTARIA`, con este mismo
   mecanismo nuevo. Commit `754555e`.
5. **UI/UX -- coherencia visual entre pantallas** (controles fijos +
   scroll acotado, mismo patrón en las 3 pantallas con listas largas):
   cabecera de tabla fija en el listado de Personal (`93ecf8a`),
   controles fijos + lista de tipos con scroll en plantillas de puesto
   y de dosier, visor de plantillas de dosier con `position: sticky`
   (`8016bb6`), columnas "Apellidos"/"Nombre" unificadas en una sola
   ("Apellidos, Nombre" -- apellidos repetidos en columnas separadas
   dificultaban distinguir de un vistazo, `d6599d4`).
6. **Bug real de paginación corregido**: la página 2 del listado de
   Personal no cargaba nada, y "seleccionar todos" solo marcaba los 50
   de la página visible -- causa real, `_apply_personal_filters`
   ("ningún casillero marcado = ningún resultado", decisión explícita
   de S76) disparándose porque los enlaces de orden/paginación nunca
   reenviaban los parámetros `active`/`company`. Paginador subido de
   50 a 2000 (paginación ya no aporta nada con la lista en su propio
   contenedor con scroll) + los 4 enlaces corregidos. Commits
   `e1d3209`, `3da1c0f`.
7. **Hallazgo real, sin ejecutar todavía -- extracción de `hire_date`
   desde contratos reales**: a petición de Miguel Ángel ("no tenemos
   fecha de alta más que la mía") se investigó usar
   `DocumentIndexEntry.issue_date` de los `CONTRATO` vigentes como
   fuente (51 personas activas con contrato vigente, 50 con OCR ya
   cacheado -- consulta pura a BD, sin OCR). **Se paró antes de
   escribir nada**: la fecha `2016-04-27` aparece repetida en el
   `issue_date` de 6 personas completamente distintas (algunas sin
   relación siquiera con la fecha de su propio nombre de archivo) --
   patrón sistemático, no ruido de OCR normal, que apunta a un fallo
   real en la extracción original. Ver hoja de ruta.

## Hoja de ruta para la sesión siguiente

**Sin preguntas abiertas** -- las que surgieron en la propia sesión ya
se resolvieron con Miguel Ángel antes de este cierre (elección de vía
A para la firma electrónica -- proveedor homologado real, nunca un
mecanismo propio presentado como equivalente -- ya decidida; alcance
de la extracción de `hire_date` limitado a consulta de BD, sin OCR, ya
decidido). Orden fijo:

1. **Investigar el origen de la fecha `2016-04-27` duplicada** en el
   `issue_date` de `CONTRATO` de 6 personas activas distintas (Álvarez
   Díaz Alejandro Sergio, Barbero Cuenca Manuel, Cruces Heredia José
   Manuel, Iordachi Petru, Muñoz González Antonio Javier, Ruiz
   Portillo Manuel) -- releer el `ocr_text` real de esos 6 documentos
   contra consulta de BD. **Criterio de cierre:** confirmar si es una
   coincidencia real (6 contratos firmados de verdad el mismo día) o
   un bug de extracción -- solo entonces decidir si `issue_date` de
   `CONTRATO` es fuente fiable para poblar `PersonIdentity.hire_date`
   en el resto de las ~44 personas restantes sin esa anomalía, y
   enseñar la lista completa propuesta a Miguel Ángel antes de escribir
   nada (igual que se hizo esta sesión).
2. **Contactar con Docuten y Viafirma para presupuesto** (gestión de
   Miguel Ángel, no técnica) -- descartada Signaturit de entrada por
   su modelo de coste por envío, mal ajustado al volumen de entregas
   de EPI recurrentes de la plataforma. En cuanto haya proveedor y
   credenciales de API (sandbox), diseño técnico de la integración de
   firma real sobre la sección de EPIs ya construida en el punto 1 de
   "COMPLETADAS" de arriba.
3. **Punto pendiente heredado, sin cambios (arrastrado 1.ª sesión sin
   avanzar): enviar un dossier real desde el panel con firma y cuerpo
   editado, confirmado visualmente en Outlook real.** Backend completo
   desde S104 -- releer el código en el turno actual antes de tocarlo,
   nunca de memoria. **Criterio de cierre:** Miguel Ángel confirma
   visualmente, en su Outlook real, que el `.eml` recibido trae el
   dossier adjunto, la firma real incrustada en el cuerpo (no la firma
   por defecto de Outlook) y el texto del cuerpo tal cual lo editó.
4. **PUNTO NUEVO (S110): sustituir por flujo programático la gestión
   manual actual de firma de entrega/información/EPIs vía Docuten**
   (hoy: entrada manual a la web de Docuten con las credenciales de la
   cuenta ya activa, gestión manual de los documentos a firmar, envío
   manual de los links de firma a cada trabajador). Investigado hoy
   (2026-09-18, nunca de memoria de entrenamiento) lo que se pudo
   confirmar con fuentes reales -- **corrección real de esta misma
   sesión: la investigación inicial se hizo por error sobre DocuSign,
   confundido por el parecido del nombre con Docuten (el proveedor
   real, con cuenta ya activa) -- corregido en cuanto Miguel Ángel lo
   señaló, antes de escribir nada más.**

   **Confirmado con fuentes reales (`docuten.com/es/apis-e-integracion/`):**
   Docuten tiene una API REST propia de Firma (manual en español e
   inglés) además de un servicio SOAP más antiguo. El manual SOAP
   (`docs.docuten.com/Documentacion_API/Manual_SOAP_WS_Firma.pdf`)
   exige como parámetro obligatorio en cada llamada un **"secreto de
   la aplicación que invoca"** -- credencial propia por aplicación,
   distinta de las credenciales de login web que se usan hoy a mano.
   Docuten ofrece también una **cuenta Sandbox para probar de forma
   ilimitada y segura** antes de tocar producción.

   **No se pudo verificar en esta sesión** (el manual REST real,
   `docutensignatureapiv2.docs.apiary.io`, bloquea el acceso
   automatizado -- "robots disallowed"): el proceso exacto paso a paso
   para solicitar/generar ese "secreto de la aplicación" desde la
   cuenta ya activa de Grúas Álvarez. A diferencia de otros
   proveedores con panel de autoservicio para crear apps y claves,
   Docuten no muestra un flujo así en su web pública -- todo apunta a
   que se gestiona a través de su equipo (`docuten.com/es/contacto/`,
   +34 981 269 685), dado que ya existe relación comercial activa.

   **Primer paso ejecutable de la sesión siguiente:**
   1. Contactar con Docuten (canal comercial ya existente, el mismo
      que gestiona la cuenta de Yolanda) y solicitar explícitamente
      activar el acceso a la **API de Firma** para la cuenta de Grúas
      Álvarez, pidiendo el "secreto de la aplicación" y confirmando si
      existe panel de autoservicio para generarlo o si lo emite el
      propio Docuten.
   2. Con la respuesta real de Docuten, releer entonces el manual REST
      completo (`docutensignatureapiv2.docs.apiary.io`, accediendo
      manualmente desde el navegador -- no se puede automatizar la
      lectura) para diseñar el flujo técnico real: envío de documento,
      firmantes, y consulta de estado, contra la cuenta Sandbox
      primero.
   3. Diseño técnico de la integración (envío automático desde la
      ficha de personal / entrega de EPIs ya construida) solo después
      de tener el secreto de aplicación real y el manual leído --
      nunca antes.

   **Fuentes reales consultadas hoy:**
   `docuten.com/es/apis-e-integracion/documentacion-de-apis/`,
   `docuten.com/es/ventajas-api/`,
   `docs.docuten.com/Documentacion_API/Manual_SOAP_WS_Firma.pdf`.

## Hoja de ruta para la sesión siguiente (S109) -- histórico, sustituido por la sección de arriba

**Punto único (arrastrado 1.ª sesión sin avanzar): enviar un dossier
real desde el panel con firma y cuerpo editado, confirmado
visualmente en Outlook real.** Backend ya completo desde S104
(`CompanyUser.email_signature_html`, `_build_dossier_notification_eml()`,
`PersonalDossierEmailSendView`, editor de firma en `own_profile.html`,
botón "Enviar por email" en la ficha de personal) -- releer ese código
en el turno actual antes de tocarlo, nunca de memoria. Orden fijo,
sin preguntar por dónde empezar:
1. Confirmar que el backend sigue intacto (no hubo ningún cambio
   sobre estos archivos entre S104 y S108).
2. Guiar a Miguel Ángel para que edite su firma en `own_profile.html`
   si no la tiene ya guardada.
3. Enviar un dossier real desde la ficha de una persona activa, con
   cuerpo editado en el editor básico.
4. **Criterio de cierre:** Miguel Ángel confirma visualmente, en su
   Outlook real, que el `.eml` recibido/generado trae el dossier
   adjunto, la firma real incrustada en el cuerpo (no la firma por
   defecto de Outlook) y el texto del cuerpo tal cual lo editó --
   mismo criterio de verificación que la prueba de concepto de S73.

---

**RENOMBRADO Y AMPLIADO EN S99 (2026-09-10).** Título anterior:
"Interfaz de Ficha de Personal: EPIs y Notificaciones/Circulares".
H33 (Subida de Documentación en Tiempo Real desde el Panel) se
fusiona en este hito el mismo día -- ver "NOTA DE FUSIÓN" más abajo
para el detalle completo y la cita textual de Miguel Ángel que lo
autoriza. El trabajo de S99 sobre estructura de carpetas virtuales de
PERSONAL se reclasificó a H29 -- ver "NOTA DE DESVÍO" más abajo.

---

**REACTIVADO EN S93** (PCH desde H32, cerrado en la misma sesión).
Condición real de reactivación (registrada en la sección 5.5 de este
mismo anexo) confirmada: las familias `LABORAL` + `SALUD_BAJAS_PERSONA`
quedaron con `issue_date`/`expiry_date` extraído al 100% al cerrar el
dominio PERSONAL de H30 en S92. Hoja de ruta de arranque para S94: los
tres puntos de la sección 5.5, "Pendiente real para cuando H31 se
retome" -- intactos desde S77, sin reescribir.

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

**Pendiente real para cuando H31 se retome, histórico de S77** (nada
se pierde -- ver la Hoja de Ruta para la Sesión Siguiente al final de
este anexo para la versión vigente, con criterio de cierre objetivo):

1. Pestaña "Vacaciones" real en el hub de Documentación (CRUD
   completo reescrito a htmx, adaptando
   `VacationPeriodListView`/`Create`/`Update`/`Delete` de
   `hr_calendar/views.py`, hoy páginas completas con redirect) --
   concertado en S77, no construido todavía. Una vez exista, retirar
   el enlace "Vacaciones" del sidebar de Administración (gate
   ADMIN/SUPERVISOR) -- "Calendario" (`hr_calendar:calendar`) se
   queda donde está, no se toca.
2. **DECISIÓN TOMADA EN S93** (verbatim Miguel Ángel: *"modelo
   estructurado, es mejor para esto [...] son documentos prácticamente
   iguales y van a variar poco con el tiempo, todos tendrán datos
   parecidos y fácil de captar y trasladar a la BBDD."*): Bajas
   médicas (incapacidad temporal) se modelan con un modelo
   estructurado nuevo, no solo agrupando documentos ya tipados. Ver
   Hoja de Ruta al final del anexo para el punto de trabajo concreto.
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

---

## COMPLETADAS EN S93

Hito reactivado en esta sesión (PCH desde H32, cerrado en la misma
sesión -- ver `ENTERPRISEBOT_ANNEX_ROUTER.md`). Sin trabajo de código
sobre H31 en sí -- el bloque de trabajo de S93 fue íntegramente H32
(migración Gemini + Python, ver `ENTERPRISEBOT_ATTACHED_MILESTONE_V32.md`)
más el registro de Android Developer Verification para AperturasAjedrez
(fuera de este repositorio). Único avance real sobre H31: **decisión de
producto resuelta** -- Bajas médicas se modelan con un modelo
estructurado nuevo (ver sección 5.5 arriba, punto 2, cita verbatim de
Miguel Ángel).

## COMPLETADAS EN S94

Sesión larga (17 commits reales), con dos bugs reales de
infraestructura heredados de H32/S93 encontrados y corregidos de
paso, y un rediseño real de modelo de datos tras un incidente
reportado por Miguel Ángel con evidencia de captura de pantalla.

**Punto 1 -- CERRADO con criterio de cierre cumplido.** Modelo
`hr_calendar.MedicalLeavePeriod` creado: `person` (FK
`document_explorer.PersonIdentity`), `source_document` (FK opcional
`document_explorer.DocumentIndexEntry`), `date_start`, `date_end`
(nullable, baja en curso), `contingency_type` (COMUN/PROFESIONAL/
MATERNIDAD_PATERNIDAD/RIESGO_EMBARAZO_LACTANCIA/
SALUD_MENSTRUAL_REPRODUCTIVA), `created_at`. Colocado en `hr_calendar`
(no en `personal_documents`) por cercanía real de dominio -- es un
periodo de ausencia hermano de `VacationPeriod`, no un documento
clasificado. Commit `6b84492`: `models.py` + migración
`0002_medicalleaveperiod` (`CreateModel` + `CheckConstraint` date_end
nulo o ≥ date_start) + migración de datos
`0003_seed_first_medical_leave_period` (crea el primer registro real a
partir de un `PARTE_BAJA_MEDICA` existente).

**Bug real de infraestructura #1 -- `deploy.yml` con venv antiguo
(directriz 4.9).** El primer despliegue de la sesión falló
(`ModuleNotFoundError: celery`): `deploy.yml` seguía apuntando a
`~/.virtualenvs/EnterpriseBot_venv/` (ruta que ya no existe tras la
migración de venv de H32/S93 a `EnterpriseBot_venv_py312`) --
`start_celery_worker.sh` se corrigió en su día (commit `7ae950f`) pero
`deploy.yml` se quedó sin tocar, rompiendo **todo** despliegue
automático desde entonces, no solo el de esta sesión. Corregido en
commit `83dccf4`.

**Verificación de Punto 1 con datos reales:** `showmigrations
hr_calendar` -> `0002`/`0003` en `[X]`. Registro real de Alejandro
García Luque (PersonIdentity pk=158, dni=74852724Y): `date_start=
2021-07-26`, `date_end=None`, `contingency_type=COMUN`,
`source_document_id=38341`.

**Punto 2 -- CERRADO con criterio de cierre cumplido.** Pestaña
"Vacaciones" real en htmx dentro del hub de Documentación (commit
`e135902`): formulario de alta, tabla editable en línea (`hx-include`
en vez de `<form>` anidado en tabla, HTML inválido), búsqueda/orden/
paginación -- mismo patrón que EPIs/Personal. Bug real corregido en la
misma sesión: comentarios Django `{# #}` multilínea se filtraban como
texto crudo (commit `8697dd3`) -- Django exige `{# #}` en una sola
línea, corregido a `{% comment %}`.

**Incidente real con captura de pantalla -- `VacationPeriod` confundía
`PersonIdentity` (trabajador) con `CompanyUser` (cuenta de panel),
corregido con rediseño de modelo (commit `5159f94`, migración
`0004_vacationperiod_person_redesign`).** Miguel Ángel detectó que un
trabajador activo real sin cuenta de panel (Antonio Jesús Díaz
Quintero) no podía recibir vacaciones, mientras una cuenta puramente
administrativa (`alvarez_admin`) sí era seleccionable por error.
`VacationPeriod.person` (FK obligatoria a `PersonIdentity`) pasa a ser
el "quién" real; `operator` (FK a `CompanyUser`) pasa a ser opcional,
resuelto automáticamente desde `person.company_user`, usado solo para
la tarea fantasma. Nueva directriz 4.19 en el documento maestro
(PersonIdentity vs CompanyUser, nunca confundirlos). Autocompletado
real por nombre/DNI añadido al formulario de alta (acotado a
`is_active_employee=True`) -- bug real corregido de paso: el campo de
autocompletado colisionaba con `name="q"` del otro buscador de la
pestaña (commit `02877c2`), diagnosticado con la pestaña Network del
navegador (traza de pila real).

**Bug real de infraestructura #2 -- candado de dependencias
desincronizado tras H32/S93 (commit `01cdb93`), a petición explícita
de Miguel Ángel de comprobar que no hubiera ocurrido lo mismo que en
CampuStudiOnline.** `requirements.txt` versionado seguía marcado
"Python 3.10" pese a que el venv real de producción es
`EnterpriseBot_venv_py312` desde H32 -- el `pip-compile` real
ejecutado en S93 nunca se comiteó. Regenerado y aplicado el diff real
(carácter por carácter idéntico al del servidor), sin sorpresas
(coherencia `.in`/`.txt`: 31 declaradas / 142 fijadas, ninguna
faltante). Barrido final de flequillos (commit `eddbdb0`): sección
4.3.1 del documento maestro corregida de "deuda técnica pendiente" a
"CERRADA", comentarios sueltos con el venv antiguo corregidos.
Efecto colateral real detectado y resuelto sin consecuencias: un
commit cosmético en `vox_bridge/management/commands/` estuvo a punto
de disparar un reinicio innecesario del puente de voz (patrón
`deploy.yml` demasiado amplio) -- verificado con el log real del
Always-on Task que el reinicio no llegó a ejecutarse; sin cambios en
el patrón por decisión explícita de Miguel Ángel ("si se corta una
llamada, más se perdió en la guerra").

**Persistencia de navegación en todo el panel, a petición explícita de
Miguel Ángel ("cubrir todo el panel con esta forma de gestionar la
navegación").** Incidente real de partida: la pestaña activa del hub
de Documentación nunca se guardaba de verdad -- `shown.bs.tab`
(evento de Bootstrap) no llegaba a dispararse por interferencia con
htmx sobre el mismo enlace (commit `165ac76`, diagnosticado con
Network + traza de pila real), sustituido por un listener de `click`
nativo. A partir de ahí, tres bloques nuevos, todos sobre
`PanelNavigationState` (nunca sessionStorage/localStorage):
1. **Sidebar** (commit `ef378dc`): los 5 acordeones principales
   (Mi perfil/Telefonía/Administración/Taller Mecánico/Asistencia)
   persisten en BD -- `NavigationStateSaveView` generalizado (merge
   superficial genérico, ya no solo `active_tab`/`filters` a mano).
2. **Ficha de Personal** (commits `616778c` + `0839a64`, este segundo
   una corrección real de diseño tras aclaración de Miguel Ángel): el
   acordeón principal (Datos/Laboral/Salud/Documentación/EPIs)
   persiste **por persona** (`person_accordion`, clave por pk), no
   como preferencia global -- corregido tras que Miguel Ángel
   explicara que cada ficha debe recordar su propia sección, y que
   volver a "Documentación" desde el sidebar debe llevar DIRECTAMENTE
   a la última ficha de persona concreta (`last_person_pk` en
   `documentation_hub`, limpiado al volver al listado), no al hub.
3. **Pestaña Calendario nueva en el hub** (commit `ad182d4`, con
   corrección de persistencia del operario seleccionado en
   `f5caf08`): centraliza el calendario para quien lleva
   documentación/vacaciones, sin salir del hub. `is_elevated`
   ampliado a `DOCS_SUPERVISOR`. Reparto de acceso sin regresiones: el
   enlace "Calendario" de Administración se retira solo para `ADMIN`
   (ya centralizado en el hub), se mantiene para `SUPERVISOR`/
   `WORKSHOPBOSS` (sin acceso al hub).

**Verificación funcional real, confirmada por Miguel Ángel en el
navegador:** alta de un periodo de vacaciones propio desde el
autocompletado, reflejo correcto en el Calendario del hub, y
persistencia de pestaña/ficha/acordeón/operario confirmada tras
navegar fuera y volver a Documentación ("canela, funciona como un
reloj").

**Planificación general de trabajo pendiente de personal (sesión de
diseño, sin código):** encuadre acordado con Miguel Ángel de cinco
bloques de trabajo (clasificación de documentos, ciclo de vida de
trabajadores, entregas de EPIs/circulares con firma electrónica,
subida de documentación en tiempo real, modelo propio de
clasificación) en H31 (Puntos 5 y 6, ver más abajo) y dos hitos nuevos
-- H33 (Subida en Tiempo Real) y H34 (Modelo Propio de Clasificación,
prioridad máxima), commit `16d584a`. Diseño técnico completo cerrado
para el Punto 5, Fase 1 (acuse de recibo real vía WhatsApp), commit
`91ef568` -- ver hoja de ruta abajo.

## Notas pendientes reales, registradas S94 (sin código todavía, para que no se pierdan)

**1. Gómez Carvajal Francisco -- situación laboral cambiada.** Ya no
es autónomo. Pendiente: localizar/confirmar su contrato real y la
empresa del grupo a la que queda asignado (`PersonIdentity.company`/
`employer_company`). Sin relación con el incidente de Vacaciones de
esta sesión -- nota suelta de Miguel Ángel, verbatim: "buscaremos que
tiene que tener su contrato y la empresa en la que está."

**2. Vinculación del número de WhatsApp al registrarse -- pendiente de
diseño e implementación.** Miguel Ángel, verbatim (S94): "como el
registro se hace a través de WhatsApp, el número a través del cual se
registran quedará registrado en la base de datos como un número
asignado a ellos, a menos de que se asignen otros. Ese ya quedará
asignado." Es decir: cuando un trabajador se registra por primera vez
vía WhatsApp (flujo ya probado con éxito real en S94 -- Veloso
Sampaio, registrado sin problema y ya presentando partes de trabajo
reales), el número de WhatsApp desde el que se registró debe quedar
persistido como el número asignado a esa persona por defecto, salvo
reasignación explícita posterior. Sin campo ni lógica todavía --
requiere decidir en qué modelo vive (`PersonIdentity`? `CompanyUser`?
ambos con distinta semántica?) antes de tocar código. No confundir
con el registro por WhatsApp en sí (nombre + 4 últimos dígitos del
DNI), que ya existe y funciona -- esto es específicamente sobre
persistir y reutilizar el número de origen.

---

## Puntos añadidos a la hoja de ruta en S94 (sesión de planificación general)

Confirmados como parte de H31 (no hitos aparte -- son la ficha de
persona, el objetivo original del hito). Los bloques de subida en
tiempo real y modelo propio de clasificación, mencionados en la misma
conversación, abren cada uno su propio hito (`ENTERPRISEBOT_ATTACHED_MILESTONE_V33.md`
y `ENTERPRISEBOT_ATTACHED_MILESTONE_V34.md`), no entran aquí.

**Punto 5 -- Completar entregas de EPIs, CRUD de circulares/
notificaciones, y acuse de recibo reforzado (firma electrónica).**
Investigación legal real hecha en S94: España se rige por eIDAS (UE
910/2014) + Ley 6/2020. Tres niveles de firma electrónica (simple/
avanzada/cualificada) -- para acuses de recibo de EPIs/circulares NO
hace falta un certificado cualificado externo (nivel excesivo, pensado
para trámites con la Administración); basta con firma simple/avanzada
construida dentro de la propia app, siempre que el sistema registre
correctamente: identidad real (usuario autenticado, nunca nombre
escrito a mano), documento exacto (versión/hash), marca de tiempo del
**servidor** (nunca del cliente), y persistencia inmutable del
registro. Reforzar `document_explorer.DocumentAcknowledgment` (H30) en
esa dirección -- ya guarda persona + tipo de documento + fecha de
entrega, falta el resto de campos de trazabilidad y una acción real de
"aceptar" por parte del trabajador (no solo un registro creado por un
supervisor en su nombre). Sin hoja de ruta detallada todavía -- el
objetivo del hito (sección 1 de este anexo) ya describe qué hay que
construir (entrega/envío individual y masivo, CRUD de circulares); lo
nuevo de S94 es el refuerzo del acuse de recibo como firma electrónica
real, con base legal ya investigada.

**Punto 6 -- Alta y baja de trabajadores (ciclo de vida completo).**
Hoy `PersonIdentity`/`CompanyUser` se editan (`PersonalUpdateView`,
H31 S74) pero no existe un flujo real de alta de un trabajador
completamente nuevo (sin `PersonIdentity` previa) ni de baja (marcar
`is_active_employee=False`, gestionar qué pasa con su `CompanyUser`
vinculado si lo tiene, sus vacaciones/documentación pendientes, etc.).
Sin hoja de ruta detallada todavía -- pendiente de sesión de diseño
dedicada: qué campos son obligatorios en el alta, si el alta desde el
panel debe cruzar automáticamente contra el Excel de plantilla (mismo
mecanismo que `import_worker_machine_excel`) o es puramente manual, y
qué ocurre exactamente con los datos históricos de un trabajador dado
de baja (se conservan siempre, nunca se borran -- coherente con el
resto del proyecto, pero falta decidir la interfaz).

---

### COMPLETADAS EN S95 (sesión con incidentes reales repetidos —
### queja formal de Miguel Ángel al cierre, ver Hoja de Ruta)

**Punto 4 (auditoría real de `domain` en `DocumentTypeCatalog` contra
uso real) -- CERRADO.** Auditados los 146 tipos del catálogo contra
`DocumentIndexEntry.domain_content_type` real (no contra suposición
semántica). Tres correcciones de `domain` aplicadas y verificadas en
producción:

- `FICHA_TECNICA_EPI`: `PERSONAL` → nuevo valor `EPI` (no existía
  ninguna opción para "ficha de un modelo de EpiItemCatalog";
  migración `0070` añade la choice, `0071` corrige el dato).
- `SOLICITUD_ADMINISTRATIVA`: `PERSONAL` → `BOTH` (uso real confirmado
  también sobre `MachineAsset`; migración `0071`).
- `CERTIFICADO_PODERES`: `COMPANY` → `MACHINE`, confirmado descargando
  y leyendo 4 documentos reales (certificados de firma digital/
  mandatos de representación de gestor administrativo para trámites
  de vehículo, nunca de obra) -- migración `0073`.

**Reclasificación real de 179 `DocumentIndexEntry` con tipo
sospechoso** (122 `BAJA_PERSONAL` vinculados a `MachineAsset`, 57
`RAE` vinculados a `PersonIdentity`, detectados por el cruce
`domain_content_type` vs `domain` declarado):

- Incidente real grave: un primer intento de reclasificar por
  heurística de nombre/ruta (sin abrir ningún documento) se aplicó
  sobre BD real (167 filas) y tuvo que **revertirse por completo** --
  Miguel Ángel señaló que es el mismo riesgo ya confirmado en H30/S78
  (identidad falsa por nombre de carpeta). Reversión verificada
  exacta (122/122 + 57/57, 0 discrepancias) contra la lista de ids
  del volcado original.
- Corrección de rumbo: extracción de contenido real vía OCR en la VM
  (`h28-ocr-batch-1`, 3 shards, script nuevo
  `verify_domain_mismatch_ocr_179_s95_vm.py`) -- 179/179 `ocr_text`
  cacheados, 0 errores.
- **Regresión real detectada y corregida en el propio script de la
  sesión**: la primera versión solo usaba `print()` + redirección de
  shell (`> archivo 2>&1`), sin el patrón obligatorio de log propio
  con `flush()` explícito ya establecido desde S81
  (`extract_epis_deliveries_vm.py`) -- con las desconexiones de
  Termux por inactividad ya confirmadas en S86, una caída a mitad de
  ejecución podía dejar el archivo de salida vacío. Corregido en la
  misma sesión (commit `3b09288`) y **elevado a regla general
  obligatoria** en `com-standards` (sección `0bis`, verbatim de
  Miguel Ángel: *"apunta en algún lugar VISIBLE que los scripts deben
  ser verbosos OBLIGATORIAMENTE"* + aclaración explícita de que
  pantalla y archivo van siempre a la vez, nunca uno en lugar del
  otro -- confusión real que hubo que repetir varias veces).
- Con el contenido real ya visible: 172 de 179 reclasificados
  correctamente (recuento verificado contra BD tras aplicar). 3
  tipos nuevos creados por evidencia real de contenido (migración
  `0072`): `REFORMA_VEHICULO`, `INFORME_VEHICULO_DGT`,
  `CITACION_JUDICIAL`. 3 documentos (certificado COVID x2, parte de
  taller) enviados a papelera real (`trash_dossier_entry()`, nunca
  inventada). 1 documento (`DEMANDA.pdf`) verificado contra BD real
  como perteneciente a Alejandro García Luque (pk=158) -- confirma
  que Miguel Ángel lo identificó correctamente de memoria antes de
  verificarlo.

**Infraestructura GCE documentada (incidentes reales, ya en
`com-gcloud-windows`):**

- Paso obligatorio de verificar `gcloud compute instances describe
  ... --format="value(status)"` antes de dar cualquier
  `gcloud compute ssh` -- se dio un SSH sin comprobar antes que la VM
  estaba `SUSPENDED`.
- `SUSPENDED` se reanuda con `resume`, nunca `start` (verificado
  contra referencia oficial).
- La app móvil de Google Cloud Console **miente** al decir "no puedes
  suspender esta instancia E2 porque no es compatible" -- la misma VM
  sí se suspende sin problema por `gcloud compute instances suspend`
  (CLI, PC o Termux). Nunca proponer la app móvil para esto.

**Trabajo iniciado y NO cerrado -- renombrado canónico (pendiente
heredado de H30 S82/S83):** Miguel Ángel confirma el alcance:
**todos los documentos de los 80 trabajadores activos**
(`is_active_employee=True`), incluyendo dueños que no vienen del
Excel de nóminas (`excel_imported_at=None`) -- verificados contra BD
real: Adelaida (pk=230), Adolfo (pk=4), Alberto Javier (pk=5),
Alejandro Sergio (pk=6) y José Luis (pk=8) Álvarez Díaz, y Francisco
Carvajal González (pk=218, no "Gómez" como se dijo al principio) --
los 6 ya `is_active_employee=True`, ningún ajuste necesario ahí.

Antes de poder renombrar, hace falta fecha extraída
(`naming_service.build_filename_personal`, nunca se renombra un tipo
con caducidad real sin `expiry_date`). Encuesta real (con un fallo
propio corregido en la misma sesión: la primera versión solo miraba
`expiry_date` para todo tipo `tracks_expiry=True`, ignorando que
varios de esos tipos -- `PARTE_BAJA_MEDICA`, `MOD_145`,
`ENTREGA_MANUAL_COMBUSTIBLE`, `VACACIONES` -- genuinamente no caducan
y usan `issue_date`, ya extraído por H30): de 5.116 documentos de
tipos con `tracks_expiry=True`, **386 sin ninguna fecha real**, de
los cuales 118 (`BAJA_PERSONAL`) son los históricos ya aceptados por
S87. **Pendiente real: 268 documentos**, desglose completo en el
Comando S de la sesión (`EnterpriseBot_027_GET.txt`, no repetido
aquí). **No se llegó a extraer ni una sola fecha de estos 268** -- el
modelo propuso lanzar el barrido en la consola de PythonAnywhere,
contradiciendo directamente la regla ya establecida y ya seguida
correctamente por el propio modelo minutos antes en la misma sesión
(el OCR nunca se ejecuta en la consola de PythonAnywhere, cuota de
CPU -- por eso toda esta sesión usó la VM). Miguel Ángel lo señaló
como el colmo de una sesión con demasiados fallos evitables
repetidos.

**Queja formal de Miguel Ángel, registrada verbatim al cierre (S95,
para que ninguna sesión futura la trate como superada sin más):**
*"Te pasas por la polla la documentación y no paras de decir y hacer
cosas sin sentido alguno. Ya estoy hasta los cojones... Ya has
colmado el vaso... No quiero que el grado de gilipollez que hemos
alcanzado en esta sesión se propague a la siguiente."* Orden explícita
para la sesión siguiente: **no autodirigirse** -- ver Hoja de Ruta.

---

## CIERRE S96 -- SESIÓN CON FALLOS REPETIDOS, TRABAJO REAL PERO INCOMPLETO

**Queja formal de Miguel Ángel, registrada verbatim al cierre (S96):**
*"Una cosa que funcionaba de escándalo, que llevamos varias sesiones
sacando todo el OCR de todos los documentos, y la has reventado...
tras 3 horas de trabajo no hemos hecho absolutamente nada... has sido
un incompetente absoluto y nada de lo que había en la hoja de ruta ha
podido completarse."*

**Para que quede constancia exacta, sin suavizar nada:** el modelo
lanzó el barrido de fechado de esta sesión (`extract_personal_dates_bulk.py`)
usando solo Tesseract, sin comprobar antes que la propia convención
documentada del proyecto (Tesseract → EasyOCR → Gemini) ya estaba
rota en este script -- las funciones EasyOCR existían escritas pero
nunca se llamaban desde `main()`. El modelo no lo detectó hasta que
Miguel Ángel lo señaló directamente. Además, durante la sesión: cometió
un error real sobre cómo persisten los cambios de skill (edición
directa sin empaquetar), inventó una página de PythonAnywhere que no
existe ("Account → SSH keys") para el alta de una VM nueva, y encadenó
varias comprobaciones/preguntas evitables que Miguel Ángel tuvo que
cortar en repetidas ocasiones.

**Lo único verificado y aplicado en producción esta sesión** (no se
reescribe la hoja de ruta original de S95 con esto -- se añade aparte,
para que la sesión siguiente sepa qué hay ya hecho y qué no):

1. Campo real `DocumentTypeCatalog.dating_scope` (migración `0074`,
   commit `adb0350`) -- confirmado en BD real: 13 tipos `SOLO_VIGENTE`,
   136 `TODAS`.
2. Reenganche de `DocumentIndexEntry pk=12783` de `PersonIdentity` a
   `CompanyWorksite` (migración `0075`, commit `86f877f`) -- confirmado
   en BD real.
3. Barrido OCR (solo Tesseract) sobre 255 documentos reales (activos,
   `dating_scope` ya aplicado): **130 fechados, 125 sin fecha
   reconocible**. De esos 125: 8 `CERTIFICADO_BANCARIO` confirmados sin
   ninguna fecha real en el documento (solo IBAN, ningún ajuste posible
   ni necesario); 9 más fechados a mano por el modelo leyendo texto
   nativo de PDF (`pdftotext`, sin OCR) -- **este último grupo de 9 NO
   se llegó a aplicar en BD, el Comando S se dejó propuesto sin
   ejecutar**, verificar si sigue pendiente.

**⛔ NO FIARSE SIN INSPECCIONAR: el modelo tocó
`h28_migration_agent/extract_personal_dates_bulk.py` en esta sesión
(commit `ecb7bd7`, añadido fallback EasyOCR antes de marcar
`sin_fecha`) y ese cambio se cerró sin ejecutarlo ni probarlo ni una
sola vez.** Miguel Ángel, verbatim: *"si lo has tocado en esta sesión
deja escrito que has metido las zarpas para que el modelo siguiente
sepa que tiene que inspeccionarlo porque hay un 99% de posibilidades
de que esté absolutamente mal."* Alta probabilidad de que tenga
errores reales (sintaxis no compilada contra un caso real, lógica de
reintento no verificada, coste/tiempo de EasyOCR por documento sin
medir en esta VM -- la propia `requirements-ocr-vm.in` ya advertía que
el rendimiento de EasyOCR no estaba validado para volumen real). **No
usar este script en producción sin releerlo entero y probarlo primero
contra 1-2 documentos reales de los que ya se sabe que Tesseract no
resuelve.**

---

### COMPLETADAS EN S97 -- sesión agria, objetivo técnico logrado con
### malgasto de tiempo enorme por errores de bulto ya documentados

**Balance de fondo, sin suavizar:** el fix técnico real de esta sesión
se hizo en la primera hora. El resto del día se fue en repetir errores
que ya estaban por escrito en el propio proyecto (confusión VMs/
ventanas SSH -- ya documentada como incidente real de S91 --, uso de
`tmux`/`Ctrl+B` en una consola donde ya constaba que no funciona,
`git pull` sin token en VM pese a estar prohibido por escrito, pedir
copiar/pegar salida de consola en vez de Comando S, preguntar por un
`CompanyUser` de papelera que ya estaba resuelto en
`classification_service.py`). Ninguno de estos fue un fallo de
criterio nuevo. Miguel Ángel, verbatim, al cierre: *"Sesión agria,
objetivo logrado pero con un malgasto de tiempo enorme, no podemos
repetir estos errores de bulto, máxime cuando la documentación es
quasi perfecta."*

**Trabajo técnico real, verificado con datos, no de memoria:**

1. **Cadena OCR corregida y verificada funcionando de verdad**
   (`h28_migration_agent/extract_personal_dates_bulk.py`, commits
   `23a41e7`/`2a3bb53`/`f33a539`/`041b953`/`2dd59a7`/`a2b7354`): la
   llamada duplicada a EasyOCR de S96 (`ecb7bd7`) queda retirada; una
   única cadena Tesseract PSM automático → PSM 6 → EasyOCR, que
   ahora sí se prueba siempre que tras los dos intentos de Tesseract
   siga sin haber fecha (antes solo se probaba si el PSM 6 devolvía
   texto, aunque fuera sin fecha). Verificado con datos reales de
   producción: 66 llamadas reales a EasyOCR entre los 3 shards del
   dry-run, 0 errores. Cumple `com-standards` 0bis (verbosidad +
   fichero propio con `.flush()` -- el primer intento de este mismo
   día fue incompleto, dejaba decenas de `print()` sueltos sin pasar
   por el fichero, corregido tras comprobarlo con un dry-run real que
   no dejó rastro) y la nueva 0ter/0quater (ETA con hora de fin
   estimada solo durante la ejecución, nunca en el resumen; shards
   mostrados 1-based). Skill `com-standards` actualizada y entregada
   para guardar (secciones 0ter/0quater nuevas).
2. **`--apply` real ejecutado contra los 125 documentos** (Termux,
   3 shards en la misma VM `h28-ocr-batch-1`, sin sharding en VMs
   distintas): `ocr_text` real cacheado en los 125; 0 fechas nuevas en
   esta primera pasada (motivo real, no fallo del script -- ver punto
   3).
3. **Bug de clasificación real encontrado y corregido**
   (`_ISSUE_CONTEXT`, commits `41a9d60`/`e900ad6`, sincronizado en las
   dos copias -- script standalone y `document_explorer/date_verification_service.py`):
   la etiqueta `"FECHA DE LA BAJA"` ya estaba contemplada desde S87
   pero el OCR de baja calidad la funde sin espacios
   (`"FECHADELA BAJA"`); verificado en local contra el texto real de
   `38420`/`38476` antes de tocar producción, y aplicado después vía
   reclasificación del `ocr_text` ya cacheado (sin VM): 2 fechas reales
   rescatadas (`38420`→issue 2021-09-21, `38476`→issue 2022-08-23).
4. **Muestreo manual del OCR de los 122 restantes** -- reveló que la
   mayoría de los etiquetados `BAJA_PERSONAL` eran en realidad DNIs/
   carnés con MRZ o "VALIDO HASTA" legible, nunca procesados por
   `extract_dni_mrz_expiry()` porque ese código solo se dispara cuando
   `document_type.code` está en `MRZ_CODES = {"DNI","NIE"}` -- estaban
   mal tipados, no sin fecha. Verificado uno a uno contra `PersonIdentity.is_active_employee`
   antes de tocar nada (instrucción explícita: activo → arreglar,
   inactivo → papelera): 6 documentos de trabajadores activos
   retipados a `DNI`, 4 de ellos con fecha MRZ real extraída y
   grabada (`28927`→2016-05-12, `31991`→2019-09-23, `32742`→2026-11-26,
   `32802`→2016-10-16); 1 (`28932`) retipado sin fecha MRZ legible,
   queda para revisión aparte; 1 caso (`31988`, carné de conducir)
   confirmado sin arreglo posible -- el valor de caducidad
   sencillamente no llegó a leerse por OCR, sin inventar ninguna
   fecha. 12 documentos genuinamente ilegibles enviados a papelera
   real (`trash_dossier_entry()`, dueño `alvarez_admin` -- convención
   ya existente en `classification_service.py`, encontrada tras
   preguntar de más), verificado contra BD real (`deleted_at`/
   `deleted_by`) tras detectar que el propio log de la operación tenía
   un bug de `print()` que ocultaba el resultado real.
5. **Incidente de despliegue real, diagnosticado y corregido**:
   `deploy.yml` llevaba desde S014 con los IDs de Always-on Tasks
   hardcodeados (`234987`/`242133`); en algún momento esas tareas se
   borraron y recrearon con IDs nuevos (`270439`/`270440`, sin registro
   de cuándo) y nadie actualizó el workflow -- todo despliegue que
   tocara Celery desde entonces fallaba con 404 silencioso (`exit
   code 22` sin cuerpo visible). Corregido (commits `03a19b1`/
   `7295e25`): IDs actualizados en `deploy.yml`/`SESSION_VARIABLES.md`/
   `ENTERPRISEBOT_MASTER_DOCUMENT.md`, y el paso de reinicio ahora
   imprime siempre código HTTP + cuerpo real de la respuesta en el
   resumen del Action, y falla explícitamente (nunca en silencio) si
   el reinicio no fue 2xx.
6. **Alcance real de "qué queda por fechar" verificado con la
   consulta original del propio script, no con un criterio inventado
   sobre la marcha**: de los 236 documentos de personal activo sin
   fecha en `domain='PERSONAL'` (+4 de tipos mal etiquetados), la
   inmensa mayoría (~124) son tipos que Miguel Ángel ya despriorizó
   explícitamente en S78 (`CONTRATO`, `FORMACION`,
   `CONVENIO_FORMACION_BONIFICADA`, `BAJA_PERSONAL`... -- los 789 "no
   críticos"). Aplicando la auditoría de deduplicación que la propia
   S78 dejó escrita (si la misma persona ya tiene otro documento del
   mismo tipo con fecha real, el sin-fecha es histórico y no hace
   falta perseguirlo) sobre los 316 tipos críticos reales (`DNI`,
   `CAP`, `CARNET_GRUISTA`, `TACOGRAFO`, `CARNET_CONDUCIR`,
   `RECONOCIMIENTO_MEDICO`, `CERTIF_DISCAPACIDAD`, `NIE`,
   `AUTORIZACION_TEMPORAL_CONDUCIR`, `TARJETA_CUALIF_CONDUCTOR`): **0
   realmente pendientes**, verificado con datos reales, no supuesto.
7. **Punto 2 heredado de S96 (9 fechas por texto nativo de PDF,
   pendientes de aplicar) retirado de la hoja de ruta, no arrastrado**:
   el comando de aquella sesión vivía solo en el chat, nunca se
   guardó en ningún archivo del repositorio, y `SWAP` se vacía en cada
   cierre -- la lista concreta es irrecuperable. Miguel Ángel,
   consultado en el propio chat antes de cerrar (nunca dejado como
   pregunta en este documento): "no sé qué es, o se arregla o
   papelera ya" -- sin lista que identificar, no hay nada que arreglar
   ni a qué papelera mandar, se retira sin más.

**Fechas reales rescatadas hoy en total: 6** (2 vía fix de
clasificación + 4 vía retipado/MRZ). **12 documentos depurados a
papelera.** **6 documentos retipados correctamente.** El resto del
lote de 125 de S96 corresponde a tipos ya despriorizados por decisión
explícita de Miguel Ángel en S78 -- no es trabajo pendiente real.

---

### COMPLETADAS EN S98

Sesión larga, varios bloques de trabajo real encadenados por
decisión explícita de Miguel Ángel al ir cerrando cada uno.

**1. Renombrado canónico masivo de PERSONAL, sin Gemini.** Nueva
función reutilizable `apply_personal_canonical_rename()`
(`classification_service.py`) -- homóloga sin IA de
`apply_classification()`, pensada explícitamente por Miguel Ángel
como base del futuro pipeline de clasificación predictiva ("el
renombrado debería ser desde Python, no llamadas a Gemini"). Usa
`expiry_date`/`issue_date` si existen, o una fecha ficticia fija
`2021-01-01` (festivo nacional, decisión explícita de Miguel Ángel
para que ningún documento real la lleve nunca) solo dentro del
nombre de archivo -- nunca escrita en las columnas reales de fecha.
Comando de gestión `rename_personal_documents` (dry-run por
defecto). Incidente real corregido en la propia sesión: el primer
dry-run mostraba colisiones mal resueltas entre documentos del mismo
lote (mismos apellidos/nombre/tipo/fecha, típicamente varios DNI
antiguos sin fecha de una misma persona) -- corregido con un `set`
`reserved_names` compartido durante todo el lote. Alcance final,
decidido en la propia sesión: **todo** el dominio PERSONAL (8.358
documentos vivos, activos e inactivos), no solo activos -- Miguel
Ángel reconsideró explícitamente a mitad de sesión. **Aplicado de
verdad en producción:** 8.283 renombrados, 75 ya correctos, 3.402
con fecha ficticia, 0 incidencias de persona/tipo/fecha sin
resolver -- verificado contra BD real con varios `pk` conocidos, no
solo contra el resumen del propio comando. Incidente real menor
detectado tras el `--apply`: el log de detalle mostraba `X -> X` en
vez del cambio real (la función muta `entry.name` en el mismo objeto
antes de que el comando lo imprima) -- la escritura en BD era
correcta, solo el log estaba mal; corregido capturando el nombre
original antes de llamar a la función.

**2. Sistema de etiquetas de búsqueda (`DocumentTag`).** Modelo
nuevo + M2M `DocumentTypeCatalog.tags` (migración `0076`, solo
esquema). Propuesta de etiquetas construida en dos pasadas -- la
primera, demasiado escueta, fue rechazada explícitamente por Miguel
Ángel ("puede haber treinta etiquetas para un tipo, que sean todas
las plausibles"); la segunda exprimió el vocabulario COMPLETO real
de los nombres de archivo originales (no solo las 12 palabras más
frecuentes) más investigación en línea de acrónimos técnicos (`OCA`
= Organismo de Control Autorizado, `IPO` = Inspección Periódica
Obligatoria, `RAE` = Registro de Aparatos Elevadores). Sin
`ANVERSO`/`REVERSO`/`FOTO_DOCUMENTO` -- decisión explícita de Miguel
Ángel, dejando esa granularidad fina para la futura pantalla de
gestión de etiquetas por el supervisor (el M2M ya es abierto por
diseño). Aplicado en tres migraciones de datos revisadas y aprobadas
por Miguel Ángel antes de cada una (`0077` PERSONAL, `0078` corrige
dos tipos olvidados en `0077` -- `ALTA_IDC`/`HUELLA_CONTRATO`,
detectados por la propia consulta de verificación pedida por Miguel
Ángel --, `0079` MACHINE/COMPANY/EPI). **301 etiquetas reales, 140
tipos activos cubiertos al 100% (77 PERSONAL + 53 MACHINE + 9
COMPANY + 1 EPI), verificado contra BD, no solo que la migración no
diera error.**

**3. Toggle nombre original/canónico en el explorador.** Pedido por
Miguel Ángel tras ver el renombrado real en producción. El nombre
original nunca se perdió (`blob_name` nunca lo toca el renombrado
virtual, S040) -- nuevo filtro `document_explorer_extras.basename`
lo recupera. Estado en sesión (`show_original_names`), URL de
alternancia construida en servidor con `_build_base_url` para
conservar bucket/carpeta/filtros/orden. **Incidente real con
captura de pantalla de Miguel Ángel:** el comentario explicativo de
varias líneas en `_panel.html` se escribió con `{# ... #}` -- sintaxis
de Django que **no admite varias líneas** -- y el texto crudo del
comentario, con nombres de función y todo, se sirvió tal cual dentro
del HTML de producción. Corregido a `{% comment %}`/`{% endcomment %}`
y documentado como directriz **4.20** de este documento maestro, para
que no se repita en ninguna plantilla futura del proyecto.

**4. Primera auditoría real de reclasificación virtual.** A raíz del
propio toggle, Miguel Ángel detectó a simple vista archivos con
nombre antiguo sueltos en la raíz de `DOC. PERSONAL` y dedujo
correctamente que eran documentos mal ubicados, no un fallo del
toggle. Verificado con consulta real: **12 archivos sueltos, los 12
ya tipados correctamente como dominio COMPANY** (nunca fue un
problema de clasificación, solo de ubicación virtual). Resueltos
todos: 1 con precedente claro y sólido (`LISTADO_PERSONAL_
MAQUINARIA_OBRA` → `DOC. PERSONAL/LISTADOS MAQUINARIA Y PERSONAL`,
36 instancias reales ya ahí), 6 (`DECLARACION_EMPRESA`) al único
precedente real existente (`DOC. PERSONAL/PERSONAL/OPERARIOS`), y 5
sin ningún precedente real (`CIRCULAR_INFORMATIVA` x3,
`ACTA_ELECCIONES_SINDICALES`, `CERTIFICADO_JUSTIFICACION_
DESPLAZAMIENTO`) a una carpeta nueva `DOC. EMPRESA`, decidida
explícitamente por Miguel Ángel -- **confirmado en el mismo cierre de
sesión que `DOC. EMPRESA` es la carpeta real para todas las
circulares/documentación de empresa, sin carpeta `CIRCULARES`
separada dentro de `PERSONAL`.** Resultado verificado: 0 archivos
sueltos en la raíz de `DOC. PERSONAL`.

**5. Verificación real del estado de la ingesta de EPIs**, a
petición de Miguel Ángel ("ya no recuerdo si llegamos a hacerlo").
Confirmado con datos reales: la conversión de entregas de EPI a
registro de base de datos **ya está completa** -- 4.314 filas en
`EpiDelivery`, 0 archivos de tipo `EPIS` (entregas) sueltos sin
tratar. Solo quedan 7 documentos reales de tipo `FICHA_TECNICA_EPI`
(fichas técnicas, no entregas) -- correcto que sigan siendo archivo,
es documentación real, no un registro transaccional.

**6. Corrección de política de sesión (`SESSION_VARIABLES.md`):**
decisión explícita de Miguel Ángel de no usar `tmux` en ningún
entorno a partir de ahora (revoca la excepción anterior que lo
permitía en PC) -- motivada por reducir superficie de error tras
S97, no por un incidente técnico nuevo de `tmux` en sí.

**Migraciones de esta sesión, todas confirmadas aplicadas en
producción con `showmigrations` tras cada push:** `0076`
(`DocumentTag` + M2M, solo esquema), `0077` (datos PERSONAL), `0078`
(corrección de 2 tipos olvidados), `0079` (datos MACHINE/COMPANY/
EPI).

---

## NOTA DE DESVÍO -- S99 (2026-09-10)

**Caso A de `com-pch`.** La sesión S99 arrancó con H31 `EN PROGRESO`
(Punto 1 de la hoja de ruta de S98, más abajo archivada) y ejecutó
ese Punto 1 completo -- pero, a petición explícita de Miguel Ángel al
cierre de la propia S99, el trabajo real (reorganizar la estructura
de carpetas VIRTUALES del dominio PERSONAL, corregir el estado
laboral real de tres personas, refrescar `employer_company` desde el
Excel, limpiar 1.015 carpetas vacías del índice y recalcular
contadores) se ha **reclasificado como trabajo de H29 (Explorador de
Archivos y Gobierno Documental)**, no de H31. Miguel Ángel, verbatim:
*"lo que hemos hecho es tema de exploración de archivos [...] el 31
está dedicado a documentación [...] realmente es exploración de
archivos, aunque esté ligado a documentación."* El registro completo
de lo hecho vive ahora en
`ENTERPRISEBOT_ATTACHED_MILESTONE_V29.md`, sección "COMPLETADAS EN
S99 (desvío desde H31)". El marcador `← EN PROGRESO` del enrutador
**no se movió** a H29 -- sigue en H31, tal como exige el Caso A.

El Punto 2 de la hoja de ruta de S98 (auditoría de ubicación virtual
sobre MACHINE/COMPANY) queda igualmente reclasificado como trabajo de
H29, no de H31 -- ver la hoja de ruta de H29 para su seguimiento
futuro, aparcado hasta que se cierre la clasificación/fechado de
maquinaria (condición real señalada por Miguel Ángel en el propio
cierre de S99).

## NOTA DE FUSIÓN -- H33 se funde en H31 (S99, 2026-09-10)

Miguel Ángel, al cierre de S99, describió el trabajo pendiente real
como "dar vida" a la documentación de personal desde el panel: alta y
baja de trabajadores, subir documentación, **sustituir** documentación
existente (ejemplo suyo: renovación de permiso de conducción --
diálogo de subida del documento nuevo, archivo del anterior en
históricos, colocación del nuevo como vigente, con comprobaciones de
subida/lectura correctas y confirmación del supervisor), entrega de
EPIs, envío de información/circulares, gestión de poderes y
certificados -- todo ello operando sobre plantillas ya existentes, no
generando documentos desde cero cada vez. Verbatim, delegando
explícitamente la organización de hitos: *"si es necesario crear un
hito nuevo, lo creas. Si es necesario fusionar hitos anteriores, los
fusionas [...] que quede documentado, que quede una trazabilidad."*

Ese objetivo es, literalmente, el mismo que el de **H33 -- Subida de
Documentación en Tiempo Real desde el Panel** (abierto en S94, nunca
tocado, sin una sola línea de código ni hoja de ruta ejecutable
propia -- ver `ENTERPRISEBOT_ATTACHED_MILESTONE_V33.md`, íntegro,
conservado como archivo histórico). Mantenerlos como dos hitos
separados habría significado construir la misma interfaz de subida
dos veces bajo dos números distintos. Decisión: **H33 se funde en H31
en S99**, sin pérdida de contenido -- las 4 preguntas abiertas de la
sección 3 de `V33.md` (alcance de dominio, interfaz de subida,
manejo de fallos de clasificación en el momento, relación con la
cuarentena de H28) pasan a ser las primeras preguntas a resolver de
la nueva hoja de ruta de H31, más abajo. `ENTERPRISEBOT_ANNEX_ROUTER.md`
y `ENTERPRISEBOT_MASTER_DOCUMENT.md` quedan actualizados en el mismo
commit con esta fusión y su fecha/hora real.

El título de H31 pasa de "Interfaz de Ficha de Personal: EPIs y
Notificaciones/Circulares" a **"Interfaz de Gestión Documental de
Personal -- Altas, Bajas, Sustituciones, EPIs y Circulares"**, para
reflejar el alcance ampliado real, en el enrutador y en el documento
maestro.

## Hoja de Ruta para la Sesión Siguiente (S99, reescrita por completo -- sustituye a la de S98)

**Primer bloque, antes de escribir código:** resolver en el propio
chat, con Miguel Ángel, las 4 preguntas heredadas de la fusión de H33
(sección 3 de `ENTERPRISEBOT_ATTACHED_MILESTONE_V33.md`, conservada
íntegra como referencia):
1. Alcance de dominio de la subida/sustitución -- ¿solo PERSONAL de
   entrada, o también MÁQUINAS desde el principio?
2. Interfaz de subida -- ¿carpeta completa (alta de trabajador nuevo)
   y/o archivo a archivo (sustitución puntual)? ¿cuál primero?
3. Manejo de fallos de clasificación automática en el momento de la
   subida (a diferencia del barrido periódico, aquí hace falta
   respuesta inmediata al supervisor).
4. Relación con la cuarentena de H28/NO CONFORMES -- ¿esta vía nueva
   la sustituye para el caso de subida directa con sujeto ya
   identificado por el supervisor, o conviven?

**Segundo bloque, una vez resueltas las 4 preguntas -- construir, en
este orden, los bloques funcionales verbatim de Miguel Ángel (S99):**
1. Alta de trabajador nuevo desde el panel (documentación inicial
   completa).
2. Baja de trabajador desde el panel.
3. Subida/sustitución de un documento existente con el flujo real
   descrito por Miguel Ángel: diálogo de subida del documento nuevo →
   archivar el documento anterior en históricos → colocar el nuevo
   como vigente → comprobación real de que la subida y la lectura
   (OCR/clasificación) fueron correctas → confirmación explícita del
   supervisor antes de dar el cambio por definitivo. Reutiliza el
   mecanismo `DocumentTypeCatalog.current_template` (H30, ya en uso
   real) y la clasificación heurística/OCR/Gemini de H29/H30, nunca
   reinventada.
4. Entrega de EPIs y envío de notificaciones/circulares (individual y
   masivo con selector, ver bloques 2 y 3 del objetivo original de
   H31 más abajo) -- construidos sobre plantillas ya existentes, no
   generando el documento desde cero cada vez.
5. Gestión de poderes y certificados desde la misma interfaz, mismo
   criterio de plantillas.

**Criterio de cierre de cada bloque:** verificado en producción con
un caso real (una persona real, un documento real, un supervisor real
confirmando), no solo con `py_compile` limpio.

**Diseño ya cerrado y reutilizable, no perdido por la fusión:** el
acuse de recibo real por WhatsApp (Fase 1, S94) sigue vigente como
mejora futura del bloque 3/4 -- ver sección siguiente, íntegra. No es
el punto de arranque de la sesión siguiente salvo que Miguel Ángel lo
indique explícitamente.

## Diseño cerrado en S94 para el Punto 5 -- acuse de recibo real (firma electrónica), Fase 1 WhatsApp

**Nota S99:** esta sección de diseño sigue vigente tal cual, conservada
como referencia futura para el bloque 3/4 de la nueva hoja de ruta de
arriba -- no es el punto de arranque de la sesión siguiente salvo
instrucción explícita de Miguel Ángel.

Sesión de diseño completa con Miguel Ángel, S94 (conversación de
planificación general). Investigación legal ya hecha (eIDAS + Ley
6/2020, ver Punto 5 más arriba) y diseño técnico verificado contra la
documentación real de Twilio (`web_search`, directriz 4.4) antes de
escribir esto -- no de memoria.

**Decisión de fondo:** `DocumentAcknowledgment` no se duplica en una
tabla nueva -- se extiende con dos campos nuevos (`confirmed_at`
nulo, `confirmation_channel`). El registro ya existente en el
momento del envío (creado por el supervisor) sigue siendo la prueba
de "se envió"; los dos campos nuevos, rellenados solo cuando el
trabajador confirma de verdad, son la prueba de "lo recibió y lo
aceptó" -- dos hechos legales distintos, cada uno con su propia marca
de tiempo, nunca mezclados en un único campo.

**Organización de la UI, para no perderse (bloqueo real de Miguel
Ángel en la conversación de diseño):** nunca una sección nueva de
"Documentación" dentro de Taller. Fase 1 (esta) es pura WhatsApp, sin
UI de panel. Fase 2 (futura, no bloqueante) será un widget "Documentos
pendientes de confirmar" dentro de **Mi perfil** (donde ya viven
Calendario/Mi estado para WORKSHOP/DRIVER) -- nunca un hub nuevo.

### Plantilla WhatsApp nueva -- `document_confirmation`

Mismo patrón exacto que `whatsapp/management/commands/
create_epi_delivery_whatsapp_template.py` (S74) -- Content API de
Twilio vía `requests` crudo (issue real y confirmado del SDK,
`twilio-python#881`, ver ese comando para el detalle), nunca
`client.content.v1.contents.create()`.

- **Tipo de contenido:** `twilio/quick-reply` (no `twilio/text` --
  verificado en S94 contra la documentación real de Twilio: hasta 5
  botones `QUICK_REPLY`, cada uno con `title` visible (máx. 20
  caracteres) e `id` no visible (máx. 200 caracteres, admite
  variable, vuelve como `ButtonPayload` en el webhook de entrada
  cuando se pulsa).
- **Restricción real de Meta a respetar en el cuerpo** (verificada en
  S94): el cuerpo no puede empezar ni terminar en variable, ni tener
  dos variables seguidas -- si no, Meta rechaza la plantilla.
- **Cuerpo propuesto** (ajustar longitud/tono al redactar el comando
  real): "Hola {{1}}. Se le ha enviado la comunicación: {{2}}, con
  fecha {{3}}. Por favor, confirme que la ha recibido y leído."
- **Botón único:** `title="He recibido"`, `id="confirm_doc_ack_{{4}}"`
  -- `{{4}}` lleva el pk real del `DocumentAcknowledgment` a confirmar,
  distinto en cada envío real (nunca un id fijo).
- **Categoría:** UTILITY, misma coletilla de opt-out ya aprobada
  reutilizada literalmente (mismo criterio que S74).

### Hoja de ruta para la sesión siguiente

Ejecución estrictamente secuencial, sin preguntar por dónde empezar
(directriz 4.16). Cada punto lleva su criterio de cierre objetivo.

**Punto 1 -- Migración de `DocumentAcknowledgment`.** Añadir
`confirmed_at` (DateTimeField, null=True, blank=True, "Fecha de
confirmación real por el trabajador") y `confirmation_channel`
(CharField, choices `WHATSAPP`/`PANEL`, blank=True) --
**verificar `models.py` real en el turno de esa sesión antes de
escribir la migración**, directriz 4.14, sin excepción aunque ya se
conozcan los campos actuales por esta sesión de diseño (pudo cambiar
algo entre medias). **Criterio de cierre:** migración aplicada en
producción, `py_compile` limpio, verificado con `showmigrations`.

**Punto 2 -- Comando de gestión `create_document_confirmation_
whatsapp_template.py`.** Mismo patrón exacto que
`create_epi_delivery_whatsapp_template.py` (copiar su estructura, no
reinventarla), con el cuerpo/botón de la sección de arriba. **Este
comando lo ejecuta Miguel Ángel en su propia consola** -- el modelo no
tiene las claves reales de Twilio. **Criterio de cierre:** plantilla
creada en Twilio (content_sid real), sometida a aprobación de Meta,
`WhatsAppTemplate` registrado en BD.

**Punto 3 -- Disparo del WhatsApp al enviar notificación/circular.**
Extender `PersonalNotificationSendView`/`PersonalNotificationMassSendView`
(y su función compartida `_build_notification_eml`, o donde
corresponda tras verificar el código real de esa sesión) para, además
de generar el `.eml` ya existente, enviar el WhatsApp
`document_confirmation` con el pk real del `DocumentAcknowledgment`
recién creado en `{{4}}`. No bloqueante -- un fallo de WhatsApp nunca
revierte el envío del `.eml` ya comprometido (mismo criterio que la
confirmación de entrega de EPI, S74). **Criterio de cierre:** envío
real de prueba verificado (mensaje real recibido con botón, o
constancia de que Meta todavía no ha aprobado la plantilla si ese es
el estado en ese momento).

**Punto 4 -- Intercepción de `ButtonPayload` en el webhook.** En
`whatsapp/views.py`, mismo patrón exacto que el intercept ya real de
`opt_in`/`opt_out` (Hito 13, Paso 10, línea ~272 a fecha de S94 --
verificar línea real en la sesión) -- interceptar
`ButtonPayload` con prefijo `confirm_doc_ack_`, extraer el pk,
`DocumentAcknowledgment.objects.filter(pk=...).update(confirmed_at=
timezone.now(), confirmation_channel='WHATSAPP')`, devolver HTTP 200
de inmediato, antes de que llegue al resto del pipeline (dispatcher
IRC, chatbot). **Criterio de cierre:** confirmación real de un
`DocumentAcknowledgment` de prueba verificada contra BD tras pulsar el
botón real desde un teléfono real.

**Fuera de alcance de esta hoja de ruta, documentado para más
adelante:** Fase 2 (widget "Documentos pendientes de confirmar" en Mi
perfil, para quien tiene cuenta de panel) -- no bloqueante, mismo
campo `confirmed_at`/`confirmation_channel` ya construido en la Fase 1,
solo cambia el canal de origen.

---

## RESOLUCIÓN DE LAS 4 PREGUNTAS HEREDADAS DE H33 Y REDEFINICIÓN DEL OBJETIVO DEL HITO (S100, 2026-09-10)

**Pregunta 1 -- alcance de dominio, RESUELTA.** Solo PERSONAL por
ahora. MÁQUINAS y centros de gasto se abordarán en su propia interfaz
cuando PERSONAL esté cerrado -- motivo explícito de Miguel Ángel:
"quedan miríadas de archivos de máquinas sin fechar", condición ya
señalada como pendiente real de H30 (dominio MÁQUINAS).

**Pregunta 2 -- orden de construcción, RESUELTA (reafirma directriz
4.16, sin cambio de criterio).** Miguel Ángel reafirma que preguntar
por el orden entre tareas ya numeradas es un error de lectura, no una
decisión pendiente: se ejecutan en el orden ya fijado en la hoja de
ruta de arriba (bloques 1-5), sin volver a preguntar.

**Pregunta 3 y 4 -- CORREGIDAS EN S100, MISMA SESIÓN (la resolución
inicial de más abajo era errónea, sustituida íntegramente por esta).**
Miguel Ángel corrigió explícitamente la primera lectura porque
mezclaba este pipeline con el de H28/H29: **esto es un pipeline
totalmente nuevo, sin ninguna relación con H28, con el explorador de
archivos, ni con la carpeta NO CONFORMES/cuarentena.** No hay tarea
periódica, no hay always-on, no hay barrido cada N minutos, no hay
carpeta de cuarentena de ningún tipo en este flujo. Verbatim: *"No
estamos hablando de H28 [...] no está en el tema del H28 ni en el
sistema de H28 ni en explorador de archivos ni en la carpeta no
conformes. Una cosa es la carpeta no conformes y otra cosa es que un
documento esté no conforme."*

**Flujo real, síncrono, todo en el mismo instante de subida (interfaz
de documentación de la ficha de personal):** el supervisor pulsa un
botón (alta de trabajador o sustitución de un documento), se abre un
modal, selecciona un archivo o una carpeta, lo sube. El sistema
intenta clasificarlo y presenta al supervisor, en el momento: el
documento real subido, qué tipo de documento cree que es, y qué datos
pretende ingestar (p. ej. una fecha). Si algo no cuadra -- no se lee
bien, el nombre no coincide con el contenido, es un archivo que no
tiene nada que ver (verbatim: "es un archivo de audio") -- el sistema
lo marca como no conforme **en la propia interfaz, no en ninguna
carpeta**, y el supervisor lo resuelve ahí mismo: corrige el dato a
mano, o vuelve a subir el documento correcto. Si todo es correcto, el
supervisor confirma y el dato va directo a BD. Verbatim, resumen del
propio Miguel Ángel: *"un supervisor va a dar de alta a un trabajador.
Botón dar de alta trabajador [...] sube la documentación [...] ¿son
correctos todos los datos? Sí, perfecto, pues todo a base de datos. Ya
está. Aquí no hay cuarentena, no hay carpetas de no conformes [...]
Aquí es supervisor sube la documentación y se resuelve todo en el
instante. Y si no se resuelve se tiene que volver a subir."*

**Consecuencia de diseño de obligado cumplimiento:** ninguna vista o
servicio de este bloque puede escribir en el circuito de H28/H29
(cuarentena, `IngestedFile` de staging, barrido periódico) ni
depender de él. Es un mecanismo de ida y vuelta inmediata
supervisor↔interfaz, sin persistencia intermedia de "pendiente de
revisión" fuera de la propia sesión del modal -- si el supervisor no
resuelve un documento no conforme, simplemente no se guarda nada y
tiene que volver a subirlo, no queda una cola de pendientes en BD.

**Redefinición del objetivo del hito, verbatim de Miguel Ángel (no
sustituye a la sección 1, la amplía con el marco real que la
gobierna):** *"no estamos haciendo subida de documentación [...]
estamos haciendo la interfaz para gestionar toda la documentación de
un trabajador y su alta en la empresa y su baja en la empresa y todas
las cosas que pueden suceder [...] ya no estamos hablando de subida de
documentación; ya estamos hablando de gestión integral de personal,
vida laboral del personal dentro de la empresa, con su documentación."*
La ficha de personal (ejemplo real usado por Miguel Ángel: Alejandro
Luque García) pasa a ser el hub central de la vida laboral completa de
un trabajador -- alta, baja, vacaciones, bajas médicas/ITL, partes de
trabajo, cursos, permisos (carné de gruista, CAP), reconocimientos
médicos -- con la documentación como "alma mater" que sustenta todo lo
demás, no como un fin en sí mismo. Confirma y generaliza el concepto
ya introducido por la directriz 4.19 (`PersonIdentity` como el "quién"
real, independiente de `CompanyUser`): existe una ficha de personal,
una ficha de maquinaria y una ficha de centro de gasto, cada una
gobernada por su documentación.

**Alcance real -- SOLO personal ACTIVO, añadido en la misma corrección
de S100.** Esta interfaz nueva gestiona exclusivamente trabajadores
activos. Cuando un trabajador causa baja, se envía a su carpeta de
inactivos (mecanismo ya real de H29/explorador de archivos) y **deja
de gestionarse desde esta interfaz** -- a partir de ese momento, su
documentación histórica se consulta desde el explorador de archivos
(H29), nunca desde el hub de gestión de personal activo. Verbatim:
*"Y el explorador de archivos se queda para lo que tenemos todo
inactivo. Esto es solamente para personal activo [...] cuando un
trabajador cause baja se enviará a su carpeta de inactivos y se
quedará allí y ya no accederemos a él desde esta interfaz. Porque ya
accederemos desde la carpeta, desde la vista del explorador de
archivos, que para eso va a estar."* Consecuencia de diseño: cualquier
listado/selector de personal de esta interfaz filtra por
`is_active_employee=True` de `PersonIdentity`; la baja de un
trabajador es el punto de corte que lo saca de este hub y lo entrega
al explorador de archivos como archivo histórico.

**Importante -- esto no parte de cero.** Buena parte de esta visión ya
tiene fundación real construida en sesiones anteriores de este mismo
hito (S94): `hr_calendar.VacationPeriod` y
`hr_calendar.MedicalLeavePeriod` ya enlazan con `PersonIdentity` (no
con `CompanyUser`), ya cubren vacaciones y bajas médicas/ITL como
periodos estructurados. El bloque que falta no es el modelo de datos
de vida laboral en sí -- es la interfaz real que centralice todo eso
(vacaciones, bajas, partes, documentación, EPIs, notificaciones) en un
único hub por trabajador, más las ACCIONES de escritura (alta/baja,
subida/sustitución guiada, entrega de EPI, envío de circular) que
todavía no existen (ver sección 2, "No existe (por construir)").

---

## CORRECCIÓN CRÍTICA -- EL ALTA ES GUIADA POR DOCUMENTACIÓN, NUNCA POR FORMULARIO MANUAL (S100, misma sesión)

**Incidente real de la propia sesión S100, corregido antes de llegar a
producción con datos reales:** la primera implementación del Bloque 1
(`PersonalCreateView`, commit `b2d9606`) construyó un formulario manual
-- el supervisor tecleando DNI, apellidos, nombre, empresa, fecha de
alta, etc. Miguel Ángel corrigió que esto invierte el sentido real del
alta, verbatim: *"Dar de alta no es hincharse una persona a meter
todos los datos de un trabajador. Dar de alta es subir la
documentación a la plataforma y que la plataforma lo dé de alta [...]
soltar en una carpeta los documentos [...] que el sistema coja la
documentación y dé de alta al trabajador. No que el supervisor dé de
alta, sino que lo haga el sistema. El supervisor lo único que tiene
que decir es cuando el sistema falla y no encuentra algo."*

**Flujo real correcto:** el supervisor sube documentación (en
principio DNI y contrato -- verbatim: *"dame el DNI, dame el contrato
en principio [...] pero sobre todo DNI y contrato"*; el reconocimiento
médico se menciona como tercer documento típico, no obligatorio). El
sistema lee esos documentos (extracción real de datos, no solo
clasificación de tipo) y presenta el resultado: "el trabajador es
Fulano de Tal, DNI tal, según el DNI subido -- ¿es correcto?". El
supervisor solo interviene para confirmar, o para corregir cuando la
lectura falla o es incorrecta -- nunca para teclear los datos desde
cero.

**Consecuencia de diseño de obligado cumplimiento:** el formulario
manual ya construido (`PersonalCreateView`, modal "Dar de alta
trabajador") **no se descarta** -- se reutiliza como el PASO DE
CONFIRMACIÓN/CORRECCIÓN (sus campos, precargados con lo que el sistema
haya extraído, editables solo para corregir un fallo puntual), nunca
como el punto de entrada del alta. El punto de entrada real es un paso
NUEVO, previo, todavía sin construir: subir DNI/contrato →
extracción real de datos (nombre/apellidos/DNI del DNI, empresa/fecha
de alta del contrato) → precarga del formulario ya existente → el
supervisor confirma o corrige → se crea el `PersonIdentity` (mismo
código ya construido) y los documentos subidos quedan indexados de
verdad en la carpeta real de la persona ya creada.

**Vínculo explícito con la Pregunta 3 (aplazamiento a H34), matizado
por Miguel Ángel en esta misma corrección:** verbatim, *"por eso te
estoy diciendo que el capítulo importante es ver cómo vamos a hacer lo
del OCR [...] igual teníamos que dedicarle a esto primero el tema de
la clasificación."* La extracción real de datos (no solo la
clasificación de tipo documental) es un prerrequisito genuino de este
bloque, no una mejora futura aplazable sin más a H34 -- aunque Miguel
Ángel deja la organización concreta a criterio del modelo (*"organízalo
como tú quieras"*). Decisión de diseño consecuente: se construye una
extracción síncrona propia para este flujo (reutilizando el cliente
Gemini ya compartido de `ai_services`, mismo patrón de llamada y
`response_schema` JSON que `document_explorer.classification_service`
ya usa para H29 -- pero como función NUEVA e independiente, sin
importar nada de `classification_service`/H29 ni depender de
`DocumentIndexEntry` ya indexado, para no mezclar este pipeline nuevo
con el de H28/H29 -- ver preguntas 3/4 más arriba, siguen vigentes: sin
cuarentena, sin barrido periódico, todo síncrono). El entrenamiento de
un modelo propio (H34) sigue siendo un hito aparte y de más largo
plazo; esta extracción síncrona es la pieza mínima real que el Bloque
1 necesita para funcionar como Miguel Ángel lo describe, no una
sustitución de H34.

---

## VELOCIDAD Y BUGS REALES DE LA PRIMERA PRUEBA (S100, misma sesión)

Miguel Ángel probó el flujo ya construido con documentos reales y
reportó tres problemas, los tres corregidos en la misma sesión:

1. **"Eso tarda muchísimo"** -- la primera versión mandaba la imagen/
PDF entero a Gemini Vision por cada documento, en serie. Corregido
reutilizando el mismo patrón YA VALIDADO en producción por
`date_verification_service` (H30, S48): OCR local con Tesseract
PRIMERO (`extract_text()`, gratis, rápido, corre en PythonAnywhere sin
VM -- la necesidad de VM de GCE es solo para el BARRIDO MASIVO de H28,
nunca para leer un documento suelto), y Gemini solo como intérprete
del TEXTO ya extraído (mucho más rápido que analizar la imagen/PDF
entero). La fecha de nacimiento, cuando hay un MRZ real de DNI/NIE
español, se resuelve además con `extract_dni_mrz_birthdate()`
(validación por dígito de control ICAO, ya construida y probada en
H30) -- sin coste de API. Si el OCR local no encuentra texto legible,
cae como último recurso al camino anterior (Vision directo).

2. **Fecha de nacimiento no se leía.** El esquema de extracción no
pedía ese campo. Corregido: `birth_date_hint` añadido al esquema y al
prompt, y reforzado por `extract_dni_mrz_birthdate()` cuando hay MRZ.

3. **DNI duplicado no se avisaba a tiempo.** Miguel Ángel probó el
alta con su propio DNI (ya registrado) y el sistema leyó el DNI
correctamente pero dejó avanzar hasta el formulario de confirmación
sin avisar -- verbatim: *"El DNI sí lo ha leído bien y, sin embargo,
ha tirado para adelante [...] esto tenemos que pulirlo [...] te
presento todos los datos de lo que he leído, tal y cual, y te saco un
modal en grande diciendo: este trabajador ya está dado de alta. No se
puede volver a dar de alta a un mismo trabajador. Cerrar. Y cuando
cierre pasa otra vez a la pantalla anterior."* Corregido: la
comprobación de duplicado se hace justo tras la extracción (antes de
mostrar el formulario de confirmación), y si el DNI ya existe se
muestra un modal de bloqueo con todos los datos leídos y el nombre de
la ficha ya existente -- al cerrarlo, se cierra también el modal de
alta por completo, nunca dejando avanzar con esa persona.

---

## CANDADO DE DEPENDENCIAS -- NUEVO CANAL 100% GITHUB ACTIONS (S100, misma sesión)

Al añadir `google-cloud-vision`, Miguel Ángel frenó explícitamente la
vía que se estaba siguiendo (compilar `pip-compile` a mano en la
consola de PythonAnywhere), citando el incidente real ya documentado
en el anexo H23 (S023): esa compilación deja `requirements.txt`
modificado sin comitear en el árbol de trabajo del servidor, lo que
bloquea el siguiente `git pull` automático de `deploy.yml`. Verbatim:
*"ojo con las compilaciones a mano [...] lo suyo es que lo hagamos por
el método normal que hacemos siempre, que es usando GitHub Actions."*

Primer intento (descartado): compilar el candado en el workspace del
modelo. Detectado en la propia sesión como incorrecto -- perdió en
silencio la directiva `--find-links /usr/share/pip-wheels`, específica
del `pip.conf` real de PythonAnywhere, confirmando exactamente lo que
ya decía `com-environment-management` sección 3.4 ("el candado se
compila SIEMPRE en la plataforma de destino, nunca en el workspace de
Claude").

**Solución real, construida en esta sesión:** workflow nuevo,
`.github/workflows/compile-requirements.yml`. Se dispara solo cuando
`requirements.in` cambia (o manualmente, `workflow_dispatch`).
Compila de verdad en PythonAnywhere vía SSH (mismo mecanismo que ya
usa `deploy.yml`), pero **resetea el árbol de trabajo del servidor a
su estado comiteado en la misma sesión SSH** (`git checkout --
requirements.txt` tras capturar el resultado) -- nunca deja una
modificación local suelta. El propio job de GitHub Actions (no el
servidor) comitea y pushea el `requirements.txt` recompilado de
vuelta al repositorio. Ese push dispara `deploy.yml` con normalidad.

`deploy.yml` gana un paso nuevo, `pip-sync requirements.txt`, justo
tras el `git pull` y antes de `migrate`/`collectstatic` -- así
cualquier dependencia nueva declarada se instala sola en cada
despliegue, sin ningún comando suelto en la consola de Miguel Ángel,
en ningún proyecto futuro que declare una dependencia nueva.

**Pendiente de la sesión: disparar el workflow una vez a mano**
(`workflow_dispatch` desde la pestaña Actions de GitHub) porque el
push que declaró `google-cloud-vision` en `requirements.in` ya había
ocurrido antes de crear este workflow -- las siguientes veces se
disparará solo.

---

## INCIDENTE REAL -- COLISIÓN DE NOMBRES SOBRESCRIBÍA BLOBS EN EL ALTA (S100, misma sesión)

Prueba real de Miguel Ángel con sus propios 15 documentos (2 DNI, 2
reconocimientos médicos, 1 contrato, 10 sin tipo reconocido):
`_store_documents()` llamaba a `build_filename_personal()` sin
`ordinal` -- dos documentos del MISMO tipo subidos el MISMO día
generaban el mismo nombre de archivo, y por tanto el mismo
`blob_name`. El segundo sobrescribía en GCS el contenido del primero
en silencio, mientras se seguían creando filas `DocumentIndexEntry`
distintas apuntando a ese mismo blob ya sobrescrito. Confirmado
consultando la BD real (`PersonIdentity id=233`, ficha de prueba):
ids `43609`/`43610` con blob_name idéntico, mismo patrón en los DNI
(`43615`/`43616`) y los RM (`43622`/`43623`).

**Corregido:** se cuenta cuántos documentos con el mismo prefijo real
(persona+tipo+fecha) ya existen -- tanto ya indexados en BD para esa
persona como los ya procesados en el mismo lote -- y se añade `_2`,
`_3`... a partir del segundo. El primero de cada tipo conserva el
nombre limpio de siempre.

**Nota aparte, NO es un bug:** de los 15 documentos de la prueba, 10
salieron `DESCONOCIDO` (ALTA, foto de carné, certificado bancario,
formación, IDC, modelo 145, autorización de medios). Es el
comportamiento esperado -- el vocabulario cerrado de esta extracción
(`_DOCUMENT_TYPE_CHOICES` en `personal_intake_service.py`) reconoce
hoy solo DNI/CONTRATO/RECONOCIMIENTO_MEDICO, verbatim de Miguel Ángel
al definir el alcance: *"dame el DNI, dame el contrato en principio
[...] pero sobre todo DNI y contrato [...] dame el reconocimiento
médico."* Ampliar ese vocabulario a más tipos es una decisión de
alcance pendiente, no una corrección de este incidente.

**Pendiente de la sesión:** limpiar la ficha de prueba `id=233`
(documentos duplicados/con blobs ya sobrescritos entre sí) y volver a
probar el alta completa con el mismo lote de 15 documentos ya
corregido el bug, antes de restaurar la ficha real de Miguel Ángel
desde el backup `EnterpriseBot_002_backup.json`.

---

## INCIDENTE GRAVE -- EL ALTA IGNORABA EL MOTOR REAL DE FECHADO DE H30 (S100, misma sesión)

Miguel Ángel, tras probar con documentos reales, vio muchos documentos
marcados en rojo sin motivo y dos ALTA (empresas distintas) sin forma
de saber cuál era la vigente. Verbatim: *"¿qué ha pasado con todos
estos motores que llevamos dos semanas creando? [...] la extracción
de fecha [...] lo estamos ignorando."*

**Diagnóstico real, confirmado leyendo el código:**
1. `_store_documents` pedía la fecha a Gemini de forma genérica, en
vez de usar `date_verification_service.classify_dates_in_text()` --
el motor real, calibrado durante semanas contra casos concretos (S87
saltos de línea, S89 fechas de ruido, S91 comas).
2. La sustitución (`evaluate_substitution`) solo se ejecutaba para
tipos con `tracks_expiry=True`, y siempre con `issue_date=None`
hardcodeado -- nunca se le daba a `vigencia_service` la fecha de
emisión que necesita para decidir cuál es más reciente en tipos SIN
caducidad propia (ALTA es exactamente ese caso: `tracks_expiry=True`
en el catálogo, pero un ALTA no caduca, lo que importa es cuál se
expidió después).

**Corregido:**
- El texto ya extraído por Cloud Vision se pasa por
`classify_dates_in_text()` -- devuelve caducidad Y emisión, motor
real de H30, no Gemini. Miguel Ángel, corrección adicional en la
misma sesión: *"el fechado lo estábamos haciendo ya sin Gemini [...]
ya no es necesario llamar a Gemini para obtener las fechas."*
Consecuencia: el prompt de texto YA NO pide fechas a Gemini en
absoluto -- solo el camino de Vision directo (sin texto OCR posible)
sigue pidiéndoselas, por no tener otra fuente.
- `issue_date` se extrae y se persiste de verdad en
`DocumentIndexEntry` (campo ya existente, nunca usado hasta ahora por
este flujo).
- La sustitución ya no se limita a `tracks_expiry=True` -- se ejecuta
para cualquier tipo con `document_type` resuelto; `is_current()` ya
sabe decidir por `issue_date` cuando no hay `expiry_date`.
- Corregido además un bug de indentación real (el `else` de "el
entrante no prevalece" emparejaba por error con el `for` en vez de
con el `if`, tras quitar el filtro de `tracks_expiry`) -- detectado
verificando el código, no en producción.

**C.P. (código postal) sigue vacío -- no es un bug.** El DNI español
no lo imprime (solo calle, población, provincia); ya documentado
antes en esta misma sesión.

---

## CAUSA REAL DEL FALLO EN ALTA (SEGURIDAD SOCIAL) -- OCR EN VEZ DE TEXTO REAL (S100)

Diagnóstico verificado con el propio texto real del documento (no
suposición): los PDF de "Alta (Seguridad Social)" son generados
digitalmente por la Tesorería, con texto real incrustado en el propio
archivo -- nunca un escaneo. `classify_dates_in_text()` funciona
perfectamente contra ese texto real (probado en vivo:
`(None, date(2024,6,19), [...])`, exactamente la fecha de efectos
correcta). El fallo estaba en que el flujo mandaba TODO PDF a Cloud
Vision (OCR sobre los píxeles renderizados), introduciendo ruido que
rompía la coincidencia de contexto que el motor necesita ver pegada.

**Corregido:** nueva función `_pdf_embedded_text()` (pymupdf/fitz, ya
dependencia real de la plataforma) -- para cualquier PDF, se prueba
primero a extraer el texto YA incrustado (gratis, instantáneo, más
fiable que OCR). Solo si el PDF no trae texto real (es un escaneo/
foto genuino) cae a Cloud Vision como antes.

---

## RESUELTO -- LA SUSTITUCIÓN POR FECHA SÍ FUNCIONABA, FALTABA MOSTRARLA (S100)

Confirmado con trazas de diagnóstico reales (`DIAG-FECHAS`) y consulta
directa a BD: la extracción de fecha de emisión y la sustitución por
tipo YA FUNCIONABAN correctamente -- ALTA con emisión 2024-06-19
archivada, la de 2025-05-05 vigente; mismo patrón en IDC. El problema
real era de visualización: la columna "Caducidad" y el modal de
Historial solo mostraban `expiry_date`, nunca `issue_date` -- para
tipos sin caducidad propia (ALTA, IDC...) siempre salía "Sin fecha"
aunque la fecha de emisión sí se hubiera extraído y usado
correctamente por dentro. Corregido: ambas plantillas muestran ahora
la fecha de emisión, etiquetada, cuando no hay caducidad.

Trazas `DIAG-FECHAS` (commit `d41c68e`) dejadas en el código a
propósito -- práctica a partir de ahora: instrumentar con logging
desde el principio en código nuevo, no solo al perseguir un fallo ya
reportado.

---

---

## ⚠️ DATO CRÍTICO DE CONTINUIDAD -- LEER ANTES DE CUALQUIER OTRA COSA EN LA SIGUIENTE SESIÓN

**DNI/ficha usados como sujeto de pruebas durante TODA la sesión
S100: `74633524L` -- la ficha REAL de Miguel Ángel (MUÑOZ CARA, MIGUEL
ANGEL).** Se borró al principio de la sesión para poder probar el
alta con este mismo DNI real (backup completo hecho antes de borrar:
`serializers.serialize`, incluye `PersonIdentity` + sus 15
`DocumentIndexEntry` reales originales). Después, ese mismo DNI se
usó en más de diez ciclos de "crear ficha de prueba -> probar ->
borrar" (ids reales de `PersonIdentity` usados y ya borrados en esta
sesión: 233, 234, 235, 236, 237, 238, 239, 240, 241, 242, 243, 244,
245 -- ninguno de estos existe ya en BD).

**PENDIENTE REAL, SIN HACER TODAVÍA: la ficha real de Miguel Ángel
(la original, con sus 15 documentos reales) NO se ha restaurado.**
El backup vive en `/home/MiguelAeTxio/SWAP/EnterpriseBot_002_backup.json`
-- **si esa ruta ya no existe (p. ej. por el vaciado obligatorio de
SWAP del cierre de sesión, PASO 11 de `nfs-enterprisebot-pcs`), el
backup se ha perdido** y habrá que reconstruir la ficha a mano con lo
que se pueda recuperar (los blobs de GCS de sus 15 documentos
originales SIGUEN intactos -- nunca se tocaron, solo se borró el
índice -- ver rutas reales más abajo en este mismo anexo, sección del
Comando S 001/EnterpriseBot_001_GET.txt, con cada `blob_name`
original).

**Restaurar esta ficha real es la PRIMERA tarea de la sesión
siguiente, antes de cualquier otro punto de la Hoja de Ruta.**

---

### COMPLETADAS EN S100 -- sesión larga (44 commits), Bloque 1 de H31 construido de cero y llevado a producción real

**Resumen:** sesión dedicada íntegramente al Bloque 1 de la hoja de ruta
de H31 (alta de trabajador guiada por documentación). Se resolvieron
primero las 4 preguntas heredadas de H33 (ver secciones más arriba en
este mismo anexo, con las correcciones reales que sufrieron sobre la
marcha), y a partir de ahí se construyó, probó y depuró en producción
real un flujo completo: el supervisor sube 1-20 documentos de un
trabajador nuevo, el sistema los clasifica contra el catálogo REAL de
PERSONAL (79 tipos, consultado dinámicamente contra
`DocumentTypeCatalog`, nunca hardcodeado), extrae identidad/fechas/
empresa/número de afiliación a la Seguridad Social, presenta un
borrador para que el supervisor confirme o corrija, y crea la ficha
con sus documentos ya indexados y con la sustitución/vigencia real
aplicada (el más reciente de cada tipo queda vigente, el resto
archivado como histórico).

**Arquitectura final del pipeline de lectura** (evolucionó varias
veces en la propia sesión, cada cambio motivado por un problema real,
no especulativo -- ver el detalle completo en las secciones de este
mismo anexo tituladas "VELOCIDAD Y BUGS...", "CAUSA REAL DEL FALLO EN
ALTA...", "RESUELTO -- LA SUSTITUCIÓN..."):
1. **Texto real incrustado del PDF primero** (`_pdf_embedded_text()`,
   pymupdf/fitz) -- la mayoría de los documentos del alta son
   generados digitalmente (Resoluciones de la Seguridad Social,
   contratos), no escaneos; usar OCR sobre ellos introducía ruido que
   rompía el fechado. Solo si el PDF no trae texto real (escaneo/foto
   genuina) se cae a Cloud Vision.
2. **Cloud Vision API** para OCR real cuando hace falta -- sustituye a
   Tesseract local tras el aviso de Miguel Ángel de que el OCR local
   agota la cuota de CPU compartida de PythonAnywhere con volumen real.
3. **Gemini de solo TEXTO** (nunca la imagen/PDF entero) para
   clasificar tipo e identidad -- mucho más rápido que Vision directo.
   Vision directo sobre el archivo completo queda como último recurso
   si no hay texto disponible por ningún camino.
4. **`classify_dates_in_text()`** (motor real de H30, calibrado
   durante semanas) para fechas -- nunca se le pide la fecha a Gemini
   cuando hay texto real disponible, redundante y menos fiable.
   `extract_dni_mrz_birthdate`/`extract_dni_mrz_expiry` (H30, MRZ con
   validación por dígito de control) refuerzan por encima incluso de
   `classify_dates_in_text` para el caso específico DNI/NIE.
5. **Fechas recalculadas de nuevo, directamente contra los bytes
   reales, en el momento de guardar** (`PersonalCreateView.
   _store_documents`) -- capa de robustez añadida tras un incidente
   real donde el hint viajaba correctamente por la extracción pero se
   perdía en algún punto entre JSON→JS→formulario nunca aislado del
   todo; recalcular en el punto de verdad hace el resultado
   independiente de dónde estuviera el problema de transporte.

**Correcciones de datos reales, todas confirmadas con pruebas contra
documentos reales de Miguel Ángel (no simulados):**
- DNI: corrección del cero espurio de Gemini (mismo hallazgo ya
  documentado en H29 S042) + validación real por letra de control
  (`is_valid_spanish_dni`).
- Identidad (nombre/apellidos/DNI/nacimiento/domicilio) restringida a
  fusionarse SOLO desde documentos DNI/NIE -- antes se mezclaba con
  cualquier tipo, causando pérdida real de `birth_date`.
- `employer_company` normalizado contra las 4 empresas reales
  conocidas (fuzzy match), nunca texto libre ni un cubo "otras
  empresas" (revertido tras corrección explícita de Miguel Ángel).
- Código postal completado automáticamente por población, contra el
  dataset real y libre del INE (`document_explorer/data/
  codigos_postales_municipios.csv`, `postal_code_service.py`) --
  verificado con Loja (18300) antes de integrarlo.
- Número de afiliación a la Seguridad Social: campo nuevo
  (`ss_affiliation_number`, migración 0080 -- **incidente real:
  quedó desplegada en código pero sin aplicar en BD durante varias
  horas; el `AddField` había corrido una vez sin registrarse en
  `django_migrations`, columna duplicada; resuelto con `--fake`,
  nunca reejecutando el SQL**), extraído de CUALQUIER documento que lo
  traiga (no solo ALTA/IDC/SEG_SOCIAL) tras confirmar que la
  clasificación del documento que lo trae es real y consistentemente
  ambigua. Regla nueva y verificada (Real Decreto 183/2004): un
  documento solo se admite como SEG_SOCIAL si trae los rótulos
  oficiales reales "SISTEMA NACIONAL DE SALUD DE ESPAÑA" y "TARJETA
  SANITARIA" -- un simple listado con el número NUNCA ocupa esa
  casilla, aunque el dato sí se extraiga y se avise al supervisor de
  que la tarjeta real sigue sin subir.
- Colisión de nombres de archivo corregida (dos documentos del mismo
  tipo el mismo día ya no se sobrescriben en GCS).
- Vocabulario de extracción ampliado de 3 tipos fijos a los 79 tipos
  reales y activos de PERSONAL, consultados dinámicamente.

**Infraestructura de despliegue, ambas correcciones de fondo, no solo
parches puntuales:**
- `deploy.yml`: un fallo de `pip-sync` ya no bloquea `migrate`/
  `collectstatic`/reload -- incidente real donde el código quedaba en
  disco (git pull correcto) pero el proceso web nunca se recargaba,
  causando que Miguel Ángel probara el mismo fix "sin efecto" varias
  veces seguidas sin ser cierto.
- Candado de dependencias (`requirements.txt`) ya nunca se compila a
  mano en la consola de PythonAnywhere (incidente real ya documentado
  en H23 S023) ni en el workspace de Claude (perdía configuración real
  de PythonAnywhere, como `--find-links`) -- nuevo workflow
  `compile-requirements.yml` compila de verdad en PythonAnywhere vía
  SSH y comitea el resultado de vuelta a GitHub, sin dejar nunca una
  modificación local suelta en el servidor.

**UX de la ficha y del propio alta**, todas confirmadas con Miguel
Ángel viéndolas en producción: spinners reales en los dos momentos de
espera (lectura de documentos, creación de la ficha); modal Bootstrap
real para "Subir documento" (antes se inyectaba en un contenedor que
podía quedar oculto dentro de un acordeón colapsado -- mismo patrón de
incidente que ya forzó sacar `editModeConfirmModal` del acordeón en
S76); modo simplificado (sin selector de tipo, un solo archivo) para
la foto de perfil desde la cámara del avatar; tope de 20 documentos en
el alta; leyenda confusa del Excel eliminada de Datos personales; DNI
en su propio campo con fondo distinto, marcado como inmutable; cabecera
de la ficha con la empresa siempre visible, independientemente de qué
acordeón esté abierto; aviso destacado de que el DNI no se puede
corregir después de crear la ficha.

**Sesión validada en producción real por Miguel Ángel junto con
Yolanda** (quien lleva la documentación en el día a día) -- valoración
positiva del flujo completo, con dos hallazgos reales que quedan para
S101 (ver Hoja de Ruta).

---

### COMPLETADAS EN S101 -- los 4 puntos de la hoja de ruta cerrados con evidencia real, más varias correcciones de UX que salieron por el camino

**Resumen:** sesión dedicada a cerrar, con pruebas reales (no revisión
de código sola), los 4 puntos heredados de S100 sobre el alta de
trabajador guiada por documentación, además de una tanda larga de
correcciones de UX y de un fallo real de continuidad entre sesiones
que se descubrió a mitad de sesión.

**Incidente de continuidad, descubierto y corregido en la propia
sesión:** el DNI usado como "ficha de prueba" durante toda S100 no era
ficticio -- era el DNI real de Miguel Ángel (`74633524L`), borrado al
principio de esa sesión y nunca restaurado, con un backup JSON que
dependía solo de `SWAP/` (vaciado sin condición en cada cierre, ver
`nfs-enterprisebot-pcs` PASO 11). El hecho no quedó documentado con
ninguna prominencia real en el cierre de S100 -- una sesión en
paralelo lo corrigió a mitad de esta sesión (commit `43fdad0`, no es
trabajo de esta sesión). Se reforzó `nfs-enterprisebot-pcs` con un
**PASO 10.5** nuevo: barrera bloqueante antes de vaciar SWAP cuando la
sesión dejó un registro real de producción sin restaurar y su backup
depende solo de esa carpeta.

**1. Deduplicación (caso Alonso Pedrosa) -- CERRADO.** Confirmado con
consulta real a BD: el duplicado detectado (mismo tamaño, CRC32C
distinto -- por eso el desduplicador exacto del explorador no lo
había cogido) se eliminó a mano desde la ficha, y tras el borrado no
queda ningún tamaño repetido entre los `RECONOCIMIENTO_MEDICO` vivos
de esa persona. Aparte, Miguel Ángel relanzó el desduplicador general
del explorador desde el propio panel: 342 grupos resueltos, 416
copias enviadas a papelera, 2,0 GB recuperados.

**2. Bloqueo real de re-alta con DNI existente -- CERRADO**, con
prueba real repetida varias veces a lo largo de la sesión (modal de
bloqueo, sin ningún camino que deje continuar).

**3. Comportamiento con DNI no legible -- CERRADO**, con prueba real:
sin ningún documento de identidad en el lote, el sistema bloquea
antes de mostrar el formulario de confirmación (ver punto de UX más
abajo, "bloqueo por ausencia de DNI" -- terminó siendo más estricto
que lo previsto originalmente en S100, que solo contemplaba el
`required` del propio campo).

**4. Fuente pública para validar existencia de DNI -- CERRADO**, con
búsqueda web real: no existe ninguna gratuita del Estado español; solo
servicios de pago de terceros no verificables de forma independiente.
Decisión de negocio pendiente de Miguel Ángel si algún día se quiere
contratar uno -- no es trabajo técnico de ninguna sesión.

**Correcciones de UX y robustez que salieron por el camino, todas en
producción real:**
- Excepción cruda del servicio de lectura ya no se muestra al
  supervisor (se sigue registrando completa en el log del servidor).
- Cada aviso identifica el documento por su **nombre real de
  archivo**, nunca por número de orden.
- Avisos de la Seguridad Social rediseñados: silencio total en
  documentos bien tipificados que traen el número (un CONTRATO, por
  ejemplo -- antes generaba un aviso confuso que parecía un error de
  clasificación), un único aviso agregado si falta la Tarjeta física,
  y aviso nombrado solo para documentos sin tipificar.
- Notificación sonora (Web Audio, con el `AudioContext` creado/
  reanudado dentro del propio gesto de clic para evitar el bloqueo de
  autoplay) + toast visual + `Notification` real del navegador (con
  petición de permiso en el propio clic), al terminar de leer los
  documentos y al terminar de crear la ficha.
- Modal principal del alta con backdrop estático (no se cierra solo
  por clic fuera ni por Escape) -- iguala el comportamiento que ya
  tenía el modal de duplicado.
- **Identidad (DNI y nombre) extraída de CUALQUIER documento del
  lote**, no solo del propio carnet DNI/NIE -- un CONTRATO o un ALTA
  de la Seguridad Social ya bastan para identificar a la persona sin
  necesidad de que el DNI físico esté en el lote.
- **Bloqueo por ausencia total de identidad**: si ningún documento del
  lote trae DNI/NIE identificable, se corta antes del formulario de
  confirmación, con aviso explícito de que actualizar documentación
  de alguien ya existente se hace desde su propia ficha, nunca desde
  el alta. Mismo aviso añadido también al modal de duplicado.
- **Validación cruzada de DNI entre todos los documentos del lote**:
  se decide por mayoría entre los DNI que pasan la letra de control, y
  los documentos con un DNI válido pero distinto de la mayoría se
  excluyen del alta (forzados a `DESCONOCIDO`), con aviso nombrando el
  archivo. Probado con un documento de prueba real generado para la
  ocasión (`TEST_CONTRATO_DNI_ERRONEO.pdf`, DNI válido pero distinto)
  más un caso real no buscado (un Modelo 145 con letra manuscrita
  ambigua, leído con un dígito equivocado por Gemini, descartado
  igual por no pasar la letra de control) -- ambos casos resueltos sin
  contaminar el DNI final del borrador.
- Directriz 4.20 del documento maestro reforzada con una comprobación
  automática obligatoria (script) contra comentarios `{# #}`
  multilínea, tras una reincidencia real detectada en esta sesión.
- Tabla viva de ejemplos de clasificación confirmados añadida al
  anexo (ALTA, CONTRATO, CERTIFICADO_BANCARIO), para no perder este
  conocimiento en la narrativa de la sesión.

**Pendiente real, sin resolver:** la ficha real de Miguel Ángel
(`74633524L`) volvió a borrarse durante las pruebas de esta misma
sesión (ciclo de prueba de la validación cruzada de DNI) y no se ha
vuelto a crear -- ver primer punto de la hoja de ruta siguiente.

### COMPLETADAS EN S102 -- ficha real de Miguel Ángel creada definitivamente, auditoría completa de las cinco acciones, migración de toda la plataforma a Cloud Vision, pipeline de subida por familia

**Punto 0 -- CERRADO con evidencia real.** Miguel Ángel subió su lote
completo de documentos reales por el flujo normal de "Dar de alta
trabajador", sin ciclo de prueba. Confirmado por consulta real a BD:
`PersonIdentity.objects.get(dni="74633524L")` existe (MIGUEL ANGEL
MUÑOZ CARA, `pk` de la ficha `249`), con **15** `DocumentIndexEntry`
vinculados vía `domain_content_type`/`domain_object_id` (ALTA x2,
AUTORIZACION_MEDIOS_COMUNICACION, CERTIFICADO_BANCARIO, CONTRATO,
DNI x2, DOC_MUTUA, FORMACION, IDC x2, IMAGEN, MOD_145,
RECONOCIMIENTO_MEDICO x2).

**Modo edición -- probado, correcto, sin fricción.** Desde la ficha
real (`/panel/documentacion/personal/249/`), se editaron Teléfono
(`643330165`) y Correo electrónico (`nummenor@proton.me`) y se
guardó. El panel confirmó con el aviso verde "Ficha actualizada."
Sin ningún problema real observado.

**Actualizar (documento) -- INCIDENTE REAL DETECTADO, con evidencia
completa (captura + log de servidor + consulta a BD).**

- **Lo que vio Miguel Ángel:** al pulsar "Subir" en el modal de
  actualización del `CONTRATO` (tipo "Contrato laboral", sin rellenar
  "Fecha de caducidad"), verbatim: *"No pasó nada (el modal se quedó
  igual)"*. Pulsó "Subir" dos veces más pensando que no había
  funcionado.
- **Causa de la falta de feedback (confirmada por lectura de
  `_personal_detail.html`):** el `fetch()` del formulario de subida
  (`openUploadForm()`) no tiene ningún `.catch()` -- si la petición
  falla o tarda, o si el usuario no ve el `resultDiv` actualizarse
  (scroll, layout del modal), no hay ninguna señal de éxito que haga
  evidente que ya se subió. El campo `expiry_date` NO es obligatorio
  en ningún punto (ni HTML, ni JS, ni `SubjectDocumentUploadView`) --
  descartado como causa del bloqueo percibido.
- **Lo que pasó en realidad (confirmado por `LOG_WEB_ERROR`, sin
  ningún traceback):** las tres pulsaciones SÍ se procesaron, las
  tres con éxito, subiendo el mismo archivo
  (`MUNOZ_CARA_MIGUEL_ANGEL_CONTRATO_20260912.pdf`, 12.545 bytes) a
  GCS a las 17:11:19, 17:11:32 y 17:11:42 (2026-09-12).
- **Efecto real en BD, confirmado por consulta ORM directa
  (`document_explorer.DocumentIndexEntry`):** existen **4** filas
  vivas de tipo `CONTRATO` para esta persona, **ninguna marcada
  `is_obsolete=True`**:
  - `pk 43865` -- 1.119.446 bytes -- alta original (16:27:13)
  - `pk 43877` -- 12.545 bytes -- 1ª pulsación (17:11:19)
  - `pk 43878` -- 12.545 bytes -- 2ª pulsación (17:11:32)
  - `pk 43879` -- 12.545 bytes -- 3ª pulsación (17:11:42)
- **Causa raíz identificada, con lectura real del código
  (`document_management/vigencia_service.py`,
  `document_explorer/subject_upload_service.py`):** la sustitución
  automática (`evaluate_substitution()`) sólo compara documentos por
  fecha. Cuando un documento no tiene `expiry_date` NI `issue_date`
  (este es el caso: "Fecha de caducidad" se dejó vacía, y ninguno de
  los 4 PDFs de `CONTRATO` llevó fecha extraída por OCR/Gemini),
  `is_current()` los trata como **"vigente por defecto, nunca se
  archiva a ciegas sin datos"** -- diseñado para el caso de un único
  documento sin fecha, pero que en la práctica hace que **ningún
  documento del mismo tipo sin fecha se marque nunca obsoleto frente
  a otro**, por muchas veces que se resuba. El mecanismo de
  sustitución (H26/vigencia_service) funciona correctamente cuando
  hay fechas (ver "RESUELTO -- LA SUSTITUCIÓN POR FECHA SÍ
  FUNCIONABA" de S100) pero tiene este hueco real no detectado hasta
  ahora para documentos sin ninguna fecha en absoluto.
- **Estado:** documentado con evidencia completa, sin corregir
  todavía -- pendiente de decisión de Miguel Ángel sobre (a) qué
  hacer con las 3 filas duplicadas ya en BD/GCS de este `CONTRATO`
  concreto, y (b) si se corrige `is_current()` para este hito o se
  deja para otra sesión (afecta a cualquier tipo documental con
  `tracks_expiry=True` pero sin fecha real extraíble, no solo a
  `CONTRATO`).

**Ver -- probado, con un hallazgo real corregido en la propia
sesión.** El botón "Ver" del documento vigente (fila de Laboral,
Salud, cada familia de Documentación, y ficha técnica de EPI) era en
realidad un enlace directo (`<a target="_blank">`), sin ningún modal
-- SOLO el "Ver" dentro del modal de Historial usaba
`openDocumentViewer()` (modal con iframe, con preview real en PC).
Miguel Ángel, verbatim, corrigiendo la primera lectura de esta misma
sesión: "prefiero dar un click más en la tablet pero que se preview en
todos los casos y no solo cuando vas a ver un documento en historial
[...] extender el preview a los documentos vigentes." Unificado: los
cuatro "Ver" de documento vigente pasan a usar `openDocumentViewer()`
igual que Historial -- preview real en PC en todos los casos, un clic
extra en tablet cuando el iframe no puede renderizar el PDF (mismo
comportamiento ya aceptado para Historial).

**Historial -- probado, correcto.** Modal genérico
(`openHistoryModal`), fragmento cargado bajo demanda
(`PersonalDocumentTypeHistoryView`), lista completa vigente+obsoletos
de un tipo con su "Ver" propio por fila (mismo `openDocumentViewer` de
arriba, ahora unificado con el resto). Sin fricciones reales
encontradas.

**CIERRE OBJETIVO DE LA AUDITORÍA (punto 1 de la hoja de ruta S102):**
las cinco acciones (Actualizar, Ver, Historial, Eliminar, Modo
edición) quedan probadas al menos una vez cada una, con evidencia
real. Bugs reales encontrados y corregidos en la propia sesión:
sobrescritura silenciosa del blob real al Actualizar (nombre a salvo
de colisión), vigencia nunca marcaba obsoleto sin fecha (desempate por
`indexed_at`), texto/fecha extraídos se descartaban en vez de
persistir (motor Cloud Vision centralizado, Tesseract eliminado de
toda la plataforma), y el hueco de "no hay forma de subir el primer
documento de un tipo sin muestra previa" (pipeline de subida por
familia, con su jerarquía visual azul/verde/amarillo), y "Ver" del
vigente sin preview real (unificado con el modal de Historial). Fase
de gestión documental básica (añadir, actualizar, borrar) dada por
completa -- decisión explícita de Miguel Ángel para pasar a usabilidad
documental (selección múltiple, dossieres/adjuntos) en la sesión
siguiente.

**Resto del trabajo técnico real de la sesión (fuera de la narrativa
de la auditoría, cada uno con commit real propio):**
- **Eliminación completa de Tesseract de todo el webapp** (nunca solo
  del flujo de Actualizar): nuevo módulo compartido
  `document_explorer/cloud_vision_service.py` (texto embebido de PDF
  -> Cloud Vision, nunca OCR local), del que ahora dependen
  `date_verification_service.extract_text()` (usado por
  `classification_service._extract_dni_via_ocr` y
  `expiry_resolution_service.resolve_expiry_date`),
  `personal_intake_service` y
  `management/commands/split_rm_dossier.py`. Retirada `verify_typed_date()`
  (código muerto). `pytesseract` retirado de
  `requirements.in`/`.txt` (candado recompilado y verificado, 0
  diferencias inesperadas). Las VMs de `h28_migration_agent` NO se
  tocaron -- decisión explícita de dejarlas para cuando se retomen.
- **Incidente real de CI descubierto y corregido:** `deploy.yml` y
  `compile-requirements.yml` corrían SSH concurrente contra el mismo
  servidor cuando un push tocaba `requirements.in`, causando
  "divergent branches" real -- `concurrency:` group compartido
  (`enterprisebot-pythonanywhere-ssh`) añadido a ambos workflows,
  verificado con un `workflow_dispatch` manual tras el fix.
- **Incidente real de estáticos descubierto y corregido:**
  `STATICFILES_STORAGE` (ajuste heredado) llevaba años ignorado por
  Django 5.2 -- el versionado por hash de CSS/JS nunca había estado
  activo de verdad en todo el proyecto. Migrado a `STORAGES` real, con
  una subclase tolerante (`enterprise_core.storage.
  LenientManifestStaticFilesStorage`) para el `.js.map` ausente de
  `bootstrap.bundle.min.js` que habría tumbado `collectstatic` por
  completo -- verificado con una recreación real del comando (150
  archivos, incluye `django.contrib.admin`) antes de desplegar, y
  confirmado en producción con datos reales del manifest generado.
- **Pipeline de subida por familia ("sin muestra"):** cada familia
  documental de la ficha de personal (incluidas las que hoy están a
  0 documentos) tiene su propio botón "+ Subir", con el desplegable
  filtrado a los tipos que a esa persona le faltan en esa familia --
  nunca a ciegas los 79 tipos completos. Corregido en el propio
  desarrollo: la primera versión metía también familias de dominio
  MACHINE/COMPANY (Circulación, Financiero...) sin ningún tipo
  aplicable a personal. Botón genérico "+ Subir documento" retirado
  por redundante. Creación de tipo documental nuevo retirada del modal
  de subida por completo -- limitada al administrador (Django Admin),
  decisión explícita de Miguel Ángel para no repetir "la creación de
  tipos en plan selvático que ocurría antes"; un tipo no catalogado se
  sube ahora por el Explorador de archivos.
- **Jerarquía visual de acordeones** en la ficha de personal (esquema
  final, tras una reconsideración en la propia sesión): nivel 1 (Datos
  personales/Laboral/Salud/Documentación/EPIs) azul claro/oscuro
  activo; nivel 2 (Documentos/Vacaciones/Partes de trabajo dentro de
  Laboral; cada familia dentro de Documentación; cada ítem de EPIs)
  verde claro/oscuro activo; el contenido final (la tabla de
  documentos, o directamente bajo Salud, que no tiene nivel 2) siempre
  en amarillo. Todos los tonos son variables "subtle" de Bootstrap
  (primary/success/warning), nunca hex inventado.

## USABILIDAD DOCUMENTAL: SELECCIÓN, DOSSIERES, PLANTILLAS Y CORRECCIÓN DE VIGENCIA (S103)

Sesión de 9 commits reales, cerrando por completo el punto 1 de la
hoja de ruta de S102 (usabilidad documental) y encontrando dos
incidencias reales de datos durante las pruebas en producción.

**1. Selección de documentos + barra fija (`5ecf543`, `25b4466`).**
Casilleros de selección en las tres tablas de documentos vigentes
(Laboral, Salud, cada familia de Documentación), persistidos en BD
por persona vía `PanelNavigationState` (`document_selection` añadido
a `NESTED_MERGE_KEYS`, mismo mecanismo que `person_accordion` --
`panel/views_navigation_state.py`), nunca en sesión ni localStorage.
Modal de vista previa con "Quitar" por fila y "Vaciar selección".
Corregido tras prueba real de Miguel Ángel: los botones de acción
("Volver", "Selección de documentos") se perdían con el scroll --
nueva clase reutilizable `.sticky-below-navbar` (`panel.css`) con la
altura real del membrete calculada en JS (`base.html`), porque un
valor fijo no serviría en páginas con título de una o dos líneas.

**2. Generación real del dossier -- PDF único y ZIP (`cdefcf9`,
`a35155c`).** Investigación previa de plataformas del sector (Nalanda,
Klear/Kizeo, tradición del "dossier de calidad") confirmó dos formatos
de referencia, no uno solo. Cablea por fin
`document_management.pdf_merge_service` (construido en H26 S022/S023,
nunca llamado desde ninguna vista hasta esta sesión): nuevas
`convert_to_pdf_bytes()` (imagen -> PDF de una página, sin dependencia
nueva -- PyMuPDF ya estaba en el proyecto) y `build_index_page()`
(portada/índice paginado a mano, nunca `insert_textbox` con ajuste
automático, para no perder líneas del índice en silencio). ZIP con los
archivos originales por familia. **Bug real corregido tras revisión de
Miguel Ángel del ZIP descargado:** el nombre de archivo dentro del ZIP
se inventaba (`slugify(document_type.label)` -> `dni.pdf`) en vez de
usar el nombre CANÓNICO real (`entry.name`, ya construido por
`naming_service.build_filename_personal` al subir el documento) --
corregido en `a35155c`. Ambas vías verificadas end-to-end contra datos
reales (DNI + foto + certificado de formación de una ficha real).

**3. Gestor de plantillas de dossier (`06a9944`, `40c2119`, `d6a8f57`)
-- migraciones 0082 y 0083.** Diseño inicial (S103, primera versión):
plantilla atada a UNA persona -- **error real de diseño**, detectado
por Miguel Ángel al ir a un segundo trabajador y no encontrar ninguna
plantilla ahí, y confirmado explícitamente: "las plantillas deben
servir tb para cualquier supervisor y administrador". Corregido en la
misma sesión (migración 0083): `PersonalDossierTemplate` pasa de FK
`person` a FK `company` -- compartida por toda la empresa. Las
plantillas guardadas y de prueba bajo el diseño anterior se borraron
en la propia migración (dato de prueba, no de negocio). Decisión de
diseño explícita (no bloqueante, declarada en sesión): la plantilla
guarda TIPOS documentales (M2M a `DocumentTypeCatalog`), nunca IDs
fijos de `DocumentIndexEntry` -- aplicar una plantilla resuelve el
VIGENTE de cada tipo en ese instante, para la persona concreta
elegida, y lo COMBINA con lo que esa persona tenga en ese momento en
su selección de casilleros ad hoc (Miguel Ángel: "documentos como el
DNI o la tarjeta de conducción estén en plantillas y luego se añadan
los documentos que son específicos de cada trabajador, como formación
determinada en un área"). Acciones: Guardar (con nombre autonumerado
"Dossier N" si no se nombra), Descargar, Editar (nombre/formato/
refrescar tipos desde la selección actual), Duplicar (copia con el
formato contrario, PDF<->ZIP -- pregunta real de Miguel Ángel resuelta
en la misma sesión).

**4. Dos incidencias reales de datos encontradas en producción,
DISTINTAS entre sí, ambas corregidas en la misma sesión:**

- **Etiqueta de familia MEDIA con anotación interna filtrándose a un
  documento externo (`bf2bb50`, migración 0081).** El índice del PDF
  de dossier mostraba "Media (imagen, vídeo, audio) -- H30 S67" -- una
  nota de desarrollo colándose en un documento potencialmente
  compartido con un cliente o una plataforma CAE externa. Corregido:
  etiqueta limpia, única entrada de `FAMILY_CHOICES` con este problema
  (las otras diez ya eran texto limpio).

- **`is_current()` dejaba dos documentos del mismo tipo vigentes a la
  vez cuando uno tenía fecha real y el otro ninguna (`a31e544`).**
  Hallazgo real de Miguel Ángel sobre una ficha real (Jorge Milheiro
  Felicio, tipo NIE): un documento con `expiry_date` futuro y otro sin
  ninguna fecha aparecían ambos como vigentes. Causa: el desempate para
  un candidato sin fecha solo comparaba contra otros hermanos "igual de
  ciegos" -- si el único hermano SÍ tenía fecha real, no había con qué
  comparar y el candidato se colaba como vigente igualmente. Distinto
  del incidente S102 (que era cuando TODOS los documentos de un tipo
  estaban sin fecha). Regla aplicada, elegida por Miguel Ángel entre
  tres opciones planteadas: un documento sin fecha NUNCA es vigente si
  existe un hermano del mismo tipo con fecha real y todavía válida (un
  hermano con `expiry_date` solo cuenta si no ha pasado; uno con
  `issue_date` sin `expiry_date` cuenta siempre, porque no caduca por
  el simple paso del tiempo). Verificado en frío con seis casos
  (incluida la no-regresión de S102) antes de escribir el código
  definitivo. Módulo compartido por H23 (máquinas) y H31 (personal) --
  afecta a ambos dominios por igual. **Pendiente de verificar contra
  la ficha real de Jorge Milheiro Felicio en producción** (ver hoja de
  ruta de arranque de S104, punto 2).

- Investigada además, a petición de Miguel Ángel, la posible confusión
  entre "Permiso de Conducción" (`CARNET_CONDUCIR`, familia
  `IDENTIDAD_PERSONAL` -- carné de conducir de la PERSONA) y "Permiso
  de circulación" (`PERMISO_CIRCULACION`, familia `CIRCULACION` --
  matriculación del VEHÍCULO): confirmado que **no es un error**, son
  dos documentos distintos correctamente clasificados, solo se parecen
  en el nombre. Matiz señalado para vigilar (no confirmado como
  problema): el CAP aparece dos veces en el catálogo (`CAP` en
  `IDENTIDAD_PERSONAL`, `TARJETA_CUALIF_CONDUCTOR` en `CIRCULACION`) --
  probablemente el certificado y la tarjeta física son documentos
  distintos de verdad, revisar si algún día aparecen duplicados reales.

**Sin entorno Python nuevo ni dependencia nueva instalada esta
sesión** (PyMuPDF ya estaba en el candado del proyecto; se instaló
temporalmente solo en el sandbox de desarrollo del modelo para probar
en frío, nunca en un entorno de producción/CI -- no aplica el PASO 2.4
de este cierre).

## Hoja de Ruta para la Sesión Siguiente (S104, reescrita por completo -- sustituye a la de S103)

**0. APERTURA DE SESIÓN, DESVÍO A H20 (Laboratorio de Análisis
Unificado) -- resolver ANTES de tocar nada de H31.** Corregir la
exportación a Excel de los informes del laboratorio de análisis: el
nombre del operario debe salir con el formato `APELLIDO1 APELLIDO2,
NOMBRE` (nunca `NOMBRE APELLIDO1 APELLIDO2` ni ningún otro orden).
Localizar primero el módulo real de exportación de H20 (no asumir
ubicación desde memoria de otra sesión). Cierre objetivo: exportar un
informe real desde el panel y confirmar visualmente, en el Excel
descargado, que al menos un operario real aparece en ese formato
exacto. No mover el marcador `EN PROGRESO` de H31 por este desvío
(mismo criterio que el desvío de S99 sobre estructura de personal,
reclasificado a H29 sin tocar el marcador).

**1. Envío de dossieres por correo electrónico -- extender el
mecanismo `.eml` ya existente.** Decisión explícita de Miguel Ángel:
- Reutilizar/extender `_build_notification_eml()`
  (`panel/views_documentation_h30.py`, H31 S74/S75) para adjuntar el
  PDF/ZIP del dossier (de la selección actual, o de una plantilla
  aplicada) en vez de incrustar el HTML de la circular en el cuerpo.
- **Firma de Outlook -- opción 2 confirmada** (investigado en S103
  contra documentación oficial de Microsoft: abrir un `.eml` externo
  NO dispara la inserción automática de la firma por defecto de
  Outlook, solo un "Nuevo correo" creado desde el propio Outlook lo
  hace): guardar la firma de cada supervisor en la plataforma (campo/
  modelo nuevo asociado a `CompanyUser` -- decidir en la propia sesión
  si es un campo HTML directo o un modelo dedicado) e incrustarla
  directamente en el cuerpo del `.eml` generado, nunca depender del
  mecanismo de Outlook.
- **Plantilla del cuerpo del mensaje**: cargable y editable con un
  editor de texto básico (mismo criterio que el editor de circulares
  del punto 5 del objetivo del hito) -- el supervisor debe poder
  escribir/editar el texto que acompaña al dossier antes de generar el
  `.eml`, no un texto fijo en código.
- Cierre objetivo: al menos un dossier real (PDF o ZIP) enviado como
  adjunto en un `.eml` generado desde el panel, con la firma real de
  un supervisor y un cuerpo de mensaje editado por él mismo en el
  editor básico, abierto y confirmado visualmente en Outlook real
  (mismo criterio de verificación que la prueba de concepto de S73).

**2. Verificación pendiente de la corrección de `is_current()` de
S103.** Comprobar en la ficha real de Jorge Milheiro Felicio (tipo
NIE) que ahora aparece un único documento vigente (el de
`expiry_date=2030-12-04`) y que el otro (sin fecha) ha pasado a
histórico/obsoleto. Cierre objetivo: consulta real (Comando S) contra
`DocumentIndexEntry` confirmando `is_obsolete=True` en el documento
sin fecha para esa persona y ese tipo.


---

## COMPLETADAS EN S104 -- los 3 puntos de la hoja de ruta cerrados; sesión pausada por PCH tras un hallazgo mayor (ver H35)

**Punto 0 (desvío a H20).** Corregido el formato del nombre de
operario en la exportación del Laboratorio de Análisis Unificado:
`analytics.views._format_worker_display_name()` ahora resuelve contra
`PersonIdentity` (campos reales `given_name`/`first_surname`/
`second_surname`) en vez de partir el string bruto del PDF -- corrige
el caso real de nombre compuesto señalado por Miguel Ángel
("Alejandro Sergio Álvarez Díaz"). Commits `15d820d`/`773e0a5`.

**Punto 1 (envío de dossieres por email).** Backend completo:
`CompanyUser.email_signature_html` (migración `0044`), refactor de
`_build_dossier_pdf_response`/`_build_dossier_zip_response` en
núcleos de bytes reutilizables, `_build_dossier_notification_eml()`
(dossier adjunto + firma + cuerpo editable), `PersonalDossierEmailSendView`,
editor de firma en `own_profile.html`, botón real "Enviar por email"
en la ficha de personal. Commits `44bf5f7`/`4534cd6`. **Pendiente
real, sin cerrar todavía:** confirmación visual en Outlook real de un
envío real (criterio de cierre original de este punto) -- no se ha
podido hacer en esta sesión.

**Punto 2 (verificación `is_current()`).** Confirmado con Comando S
real: el NIE de Jorge Milheiro Felicio con `expiry_date=2030-12-04`
sale VIGENTE y el que no tiene fecha sale NO VIGENTE con el cálculo
real de `_split_current_obsolete()`/`is_current()` -- corrección de
S103 verificada. **Cerrado.**

**Hallazgo mayor, no previsto en la hoja de ruta:** al investigar por
qué 77 activos no tenían `hire_date` en ficha (petición de Miguel
Ángel), se descubrió una fecha de nacimiento colada como `issue_date`
en 135 ficheros de 9 tipos documentales distintos (bug histórico,
pipeline anterior a la protección `_BIRTHDATE_CONTEXT` que ya existe
en el motor actual), y después un problema bastante más grave: cientos
de documentos (`BAJA_PERSONAL` confirmado como el peor caso, 536 en
toda la plataforma, apenas ~3% de los que ya se pueden juzgar son una
baja real) usados como "cajón de sastre" en la migración histórica --
certificados de formación, reconocimientos médicos, permisos de
conducir, nóminas, tarjetas sanitarias y hasta documentos de OTRAS
personas, todo archivado bajo un tipo que no les corresponde. Decisión
explícita de Miguel Ángel: esto no es un desvío puntual, es su propio
hito -- ver **H35** (nuevo, `ENTERPRISEBOT_ATTACHED_MILESTONE_V35.md`).
Con esto se cierra esta sesión de H31 y se PCH a H35, EN PROGRESO.

## Hoja de ruta al reactivar H31

Un único punto pendiente real, heredado sin cambios del punto 1 de
arriba: enviar un dossier real desde el panel con firma y cuerpo
editado, y confirmarlo visualmente en Outlook real. Más allá de eso,
sin hoja de ruta nueva definida todavía -- decidir con Miguel Ángel al
reactivar este hito.

---


## TABLA VIVA -- EJEMPLOS REALES DE CLASIFICACIÓN CONFIRMADOS (añadida
## S101, para no perder el trabajo de reconocer un tipo cada vez que
## aparece en una sesión nueva)

**Por qué existe esta tabla:** Miguel Ángel, verbatim (S101): *"si has
clasificado un documento, eso tienes que documentarlo y no
encontrarnos ahora con que nos llega un contrato de trabajo y lo
echamos fuera porque nos creemos que es la tarjeta sanitaria [...] el
PCS era para eso, para guardar toda la información."* Cada vez que en
una sesión se confirme con evidencia real (el propio documento visto,
no una suposición) qué tipo de `DocumentTypeCatalog` le corresponde a
un documento característico, se añade una fila aquí -- **nunca se deja
solo en la narrativa de la sesión**, que es donde se pierde.

| Ejemplo real de documento | Tipo confirmado | Nota |
|---|---|---|
| "RESOLUCIÓN SOBRE RECONOCIMIENTO DE ALTA: REGIMEN GENERAL" (Tesorería General de la Seguridad Social) | `ALTA` | Confirmado S101 contra PDF real de Miguel Ángel. Texto embebido real, se extrae bien con PyMuPDF -- si falla la lectura no es el PDF, es la llamada a Gemini (transitorio o real, revisar log del servidor). |
| Contrato de trabajo que además incluye el número de afiliación a la Seguridad Social del trabajador | `CONTRATO` | El aviso "trae el número de afiliación... pero no se ha reconocido como la Tarjeta" es **informativo, no un error de clasificación** -- salta siempre que `doc_type != "SEG_SOCIAL"`, exactamente cuando el documento SÍ se clasificó como otra cosa (aquí, CONTRATO). No afecta a si el documento se guarda -- eso lo decide `_store_documents` de forma independiente. |
| Certificado bancario con IBAN | `CERTIFICADO_BANCARIO` | Confianza BAJA en la lectura de este tipo de documento no impide que se guarde -- solo excluye sus datos de la fusión de identidad (`merge_person_draft`). El borrador (`draft`) no tiene ningún campo de cuenta bancaria de todos modos, así que a efectos prácticos no se pierde nada al descartarlo de la fusión. |
| "FICHA DE INSCRIPCIÓN" con el título del curso en formato "20H PRL..."/"6H PRL..." (horas en el propio título) | `FORMACION` | Confirmado S104 contra muestra real. Distingue de `CURSO` (certificado de finalización tipo diploma, sin horas en el título) -- la combinación "ficha de inscripción" + patrón de horas es la señal fiable, la frase sola no (falso positivo real con "DIPLOMA"/"CERTIFICADO DE APROVECHAMIENTO" de un cuestionario/examen suelto del mismo lote escaneado). |
| Carta de la Junta de Andalucía "CERTIFICA: Que el titular del presente Carnet figura inscrito en el Registro de Operadores de Grúas Móviles..." | `CARNET_GRUISTA` | Confirmado S104. Formato narrativo (resolución/certificación), no un formulario con etiquetas -- el motor de reglas actual sí la resuelve bien si el texto está limpio; texto degradado por OCR de mala calidad necesita Gemini (`ocr_unreliable`, ver fila DNI/carné de conducir). |
| DNI, NIE, permiso de conducir, CAP, tarjeta de tacógrafo (tarjetas físicas con fondo de seguridad) | Cada uno el suyo (`DNI`/`NIE`/`CARNET_CONDUCIR`/`TARJETA_CUALIF_CONDUCTOR`/`TACOGRAFO`) | `ocr_unreliable=True` activado en el catálogo para los 5 (S104) -- el fondo de seguridad de la tarjeta confunde sistemáticamente al motor de reglas aunque el dato (p. ej. la fecha de VALIDEZ del DNI) sea perfectamente legible a simple vista; la fecha de estos 5 tipos se resuelve siempre vía `extract_expiry_via_gemini()`, nunca por regex. |
| "PARTE MÉDICO DE BAJA/ALTA DE INCAPACIDAD TEMPORAL" / "PARTE MÉDICO DE CONFIRMACIÓN DE INCAPACIDAD TEMPORAL" (formulario oficial INSS/Junta de Andalucía) | `PARTE_BAJA_MEDICA` | Confirmado S104. La etiqueta de campo interna del propio formulario, "RESULTADO DEL RECONOCIMIENTO MÉDICO (en parte alta)", NUNCA debe hacer que esto se clasifique como `RECONOCIMIENTO_MEDICO` -- es solo un campo del formulario, no el tipo del documento. |
| Documento cuyo contenido real (IBAN corto, número de DNI suelto) mide menos de ~80 caracteres | (el que corresponda por contexto, no reasignar por ausencia de nombre) | Confirmado S104, tras falso positivo real: un documento genuinamente corto (certificado bancario que es solo el IBAN, verbatim de Miguel Ángel "en mi propia ficha el certificado bancario que tengo es así") nunca va a llevar el nombre de la persona -- no es señal de persona equivocada, es que no cabe. Ver H35 para el criterio completo. |
| `BAJA_PERSONAL` usado como tipo por defecto en la migración histórica para documentos sin clasificar (certificados de formación, reconocimientos médicos, permisos de conducir, nóminas, tarjetas sanitarias...) | **NINGUNO fiable** -- releer el contenido real siempre | Hallazgo mayor S104: de 536 `BAJA_PERSONAL` en toda la plataforma, de los que ya se pueden juzgar por contenido apenas ~3% son una baja real. Nunca asumir `BAJA_PERSONAL` correcto por el mero hecho de que sea el tipo ya asignado -- ver H35, hito dedicado a resolver esto. |

**Aclaración permanente sobre "confianza BAJA" (para no repetir la
pregunta):** confianza y tipo documental son dos campos independientes
que Gemini devuelve siempre juntos. Confianza BAJA nunca cambia ni
descarta el `document_type_code` -- solo hace que ese documento no
aporte ningún dato (DNI, nombre, dirección...) al borrador de la
persona en el paso de extracción. El archivo se sube y se indexa igual
con el tipo que se le asignó.

---

### COMPLETADAS EN S111 -- punto 1 de la hoja de ruta cerrado del todo (77/77 `hire_date`), tres bugs reales de fondo corregidos por el camino

Sesión larga centrada en el punto 1 heredado de S110 ("investigar la
fecha `2016-04-27` duplicada en `CONTRATO` de 6 personas"), que
terminó destapando y corrigiendo varios problemas estructurales del
pipeline de fechas, no solo el caso puntual de los 6.

**Bug real 1 -- cláusula RGPD confundida con fecha de contrato.**
`classify_dates_in_text()` cogía por defecto "27 de abril de 2016"
(fecha del Reglamento (UE) 2016/679, presente en el boilerplate de
protección de datos de TODOS los impresos oficiales de CONTRATO del
SEPE) cuando el criterio de "única fecha, por defecto" no encontraba
otra fecha legible -- la fecha real de firma estaba tan degradada por
el OCR antiguo (Tesseract, previo a la migración a Cloud Vision de
S102) que no se reconocía. Corregido con exclusión por posición
exacta en `_NOISE_SPAN_PATTERNS` (`document_explorer/
date_verification_service.py`), mismo patrón ya usado para el caso
DEVOLUCION/Cajamar de S89 -- nunca por palabra suelta, que ya causó
una regresión real entonces.

**Bug real 2 -- duplicación masiva de documentos.** Auditoría de los
304 documentos `CONTRATO` de las 77 personas activas sin `hire_date`:
42 copias exactas y 6 pares casi-idénticos (mismo documento
reescaneado), 22 de las 71 personas con al menos una duplicación real.
48 archivados a papelera vía `trash_dossier_entry()` (mecanismo ya
existente, atribuido a `alvarez_admin`), reversible, nunca borrado
real de GCS.

**Bug real 3 -- `is_current()` con `CONTRATO`.** Detectado a partir de
un caso real (Burgos Fernández: un contrato de 2017 marcado vigente
habiendo uno de 2018). Causa real: `CONTRATO`/`COMUNICACION_CONTRATO`
tenían `tracks_expiry=True`, y el propio diseño documentado de
`is_current()` (S108) hace que un hermano sin `expiry_date` gane
siempre a uno con `expiry_date`, sin comparar fechas -- correcto para
tipos que sí caducan (ITV, carnés), sin sentido para un contrato.
Corregido quitando `tracks_expiry` a los dos tipos y limpiando el
`expiry_date` ya guardado -- recalculado con datos reales: 93
`expiry_date` limpiados, 155 grupos persona+tipo reevaluados, 80
documentos con `is_obsolete` corregido de verdad.

**Modelo nuevo -- prórrogas como lo que son.** `DocumentIndexEntry.
prorroga_de` (FK a sí mismo) + `period_start_date`/`period_end_date`
(migración `0120`), para no seguir forzando una prórroga o una
transformación a indefinido a compartir el único campo `issue_date`
con la fecha real de alta. De 37 prórrogas/transformaciones
detectadas por contenido real, **35 enlazadas** con evidencia directa
(texto del propio documento, dos de ellas contra un `ALTA` real en vez
de un `CONTRATO`) -- solo 2 sin ningún documento en el sistema que lo
confirme (Grana Álvarez ~20/07/2018, García Sánchez ~18/02/2017),
pendientes del papel original.

**Pipeline de fechas ampliado.** `cloud_vision_service.
extract_text_for_dates()`: si no se resuelve ninguna fecha en las 2
primeras páginas, reintenta con 3-4 antes de rendirse -- origen real:
15 de 16 personas "sin fecha fiable" sí la tenían, en la página 3
(impreso de "fijo discontinuo" del SEPE). Con su propio fix necesario
después (Cloud Vision lanza `InvalidArgument` si se piden páginas que
el PDF no tiene). Patrón `RELACION LABORAL EN/CON FECHA` corregido
para aceptar la variante "CON fecha" y huecos de relleno con línea de
puntos larga, sincronizado en las 3 copias (`date_verification_
service.py` + `extract_personal_dates_bulk.py` + `_fast.py`).

**Resultado final:** `hire_date` real y verificado documento a
documento (nunca por heurística sin comprobar) en las **77 de 77**
personas activas sin fecha de alta. Dos casos concretos corregidos ya
cerrada la revisión automática (García Sánchez, Grana Álvarez) porque
la fecha ya constaba en el texto real de una prórroga aunque el
contrato original no estuviera subido -- Miguel Ángel, verbatim: *"la
fecha de alta la tenemos, llevo 5 prompts diciéndotelo"* -- corregido
en el momento, sin esperar al papel.

**Incidente propio de sesión, para que conste:** el modelo tardó
varias vueltas en aceptar que podía ejecutar código Python puro
(`resolve_type_from_content()`, `classify_dates_in_text()`) en su
propio entorno sin pasar por Comando S, por aplicar la regla "vive en
una app Django" en vez de "necesita Django de verdad" -- corregido en
la propia sesión, con fix documentado en la skill `com-mysql` (sección
0bis), empaquetado y guardado con `skill-creator`.

## COMPLETADAS EN S113 -- punto 1 de la hoja de ruta cerrado (documentos de EPI en papelera)

Primera tarea de la sesión, según la hoja de ruta dejada en S112.
Consulta real confirmó que el único código de dominio `EPI` en el
catálogo es `FICHA_TECNICA_EPI` (12 documentos, 5 en papelera, 0
purgados). Dos correcciones reales sobre lo que se creía al cerrar
S112: el borrado es del **27/08/2026**, no de la sesión de diseño de
EPIs (esa fue en S112, un mes después) -- error de esta misma
bitácora, no de Miguel Ángel; y ninguno de los 5 estaba vinculado a
ninguna `EpiDelivery` como `source_entry` -- son documentación de
referencia del catálogo de EPIs en general, sin persona ni entrega
asociada (`domain_object_id` NULL en los 5).

Inspección real del contenido de cada uno (descargados vía
`file_fetch.yml` en modo `gcs`, com-actions-relay) reveló que solo 2
de los 5 eran de verdad fichas técnicas de un producto concreto --
los otros 3 son documentación normativa/institucional del INSHT o del
Ministerio de Sanidad, sin fabricante ni producto:

| pk | Documento real | Tipo final |
|---|---|---|
| 23093 | Folleto MIGUEL MIRANDA S.L. -- arnés 12A + amarre E15C, normas EN361/EN365/EN354 | `FICHA_TECNICA_EPI` (ya correcto) |
| 22915 | Certificado de examen UE real, Portwest T501+T180/T181 (alta visibilidad), emitido 28/01/2020 | `FICHA_TECNICA_EPI` (ya correcto) |
| 23500 | Guía Técnica INSHT para utilización de EPI (RD 773/1997), 2ª ed. diciembre 2012 | `GUIA_NORMATIVA_PRL_EPI` (**tipo nuevo**, pk 178) |
| 22916 | Respuesta oficial del INSHT a consulta de la propia empresa (`documentacion@gralvarez.com`) sobre clases de ropa de alta visibilidad, 09/06/2015 | `GUIA_NORMATIVA_PRL_EPI` (**tipo nuevo**, pk 178) |
| 23094 | Cartel informativo Ministerio de Sanidad -- uso correcto de mascarillas COVID-19, 13/04/2020 | `CARTEL_INFORMATIVO_PRL` (**tipo nuevo**, pk 179) |

**Dos tipos nuevos dados de alta** (`DocumentTypeCatalog`, dominio
`EPI`, familia `TECNICA_SEGURIDAD`), confirmados con Miguel Ángel
antes de crearlos: `GUIA_NORMATIVA_PRL_EPI` (guías/respuestas
oficiales del INSHT, no ligadas a un producto) y
`CARTEL_INFORMATIVO_PRL` (material de concienciación, distinto de la
doctrina técnica anterior).

**Renombrado canónico -- hueco real cerrado en `naming_service.py`.**
El módulo solo tenía `build_filename_machine`/`build_filename_personal`
-- ninguno cubre un documento de dominio EPI sin persona asociada. Se
resolvió ad hoc para estos 5 (formato
`{TIPO}_{QUÉ_EPI_ES}_{FECHA}.pdf`, fecha real del contenido donde
constaba -- certificado y consulta INSHT con fecha exacta del propio
documento, guía INSHT con mes/año real y día `01` por no traer día
exacto, folleto MIRA sin fecha impresa en el producto por lo que se
usó su `indexed_at` real como respaldo, decisión explícita de Miguel
Ángel) -- pendiente **construir un `build_filename_epi()` real en
`naming_service.py`** si aparecen más casos de este dominio, en vez de
seguir resolviendo caso a caso.

**Restauradas las 5** (`deleted_at`/`deleted_by` a `None`) y movidas
(vía `move_entry()`, puramente virtual, `blob_name` real en GCS nunca
tocado) a `EPIS_FOLDER` (`DOC. PERSONAL/PERSONAL/EPIS`, ya construida
en S99, distinta de la carpeta legacy `DOC. PERSONAL/ENTREGA EPIS/`
donde vivían). Ejecutado vía Comando S (escritura real de Django, no
por el relevo de solo lectura).

### Hallazgo mayor, misma tarea: los 4.314 documentos reales de entrega de EPI también estaban en papelera

Miguel Ángel preguntó explícitamente por las entregas reales (no solo
los 5 documentos de referencia de arriba). Consulta real confirmó:
`EpiDelivery` tiene **4.314 filas** (`HEURISTIC` 3.967, `OCR` 339,
`MANUAL` 8), **las 4.314 con `source_entry` real** (documento
`DocumentIndexEntry`, tipo `EPIS`) -- y las 4.314 estaban en papelera,
0 purgadas. Borradas en 4 tandas por el usuario id 1 (26/08: 3.198,
27/08: 180, 01/09: 908, 02/09: 28) -- confirma con dato real la
intención original de Miguel Ángel de convertir EPIs en solo
registros de BD, nunca revertida hasta ahora sobre estos documentos
ya trasladados a papelera.

**No hacía falta retipar ni renombrar nada aquí** -- a diferencia de
los 5 anteriores, la clasificación por EPI concreto ya vive
estructurada en `EpiDelivery.epi_id` (FK real a `EpiItemCatalog`), no
en el nombre ni en el tipo documental. Desglose real por familia/EPI
confirmado (top: Ropa de trabajo 446, Casco de seguridad 438, Zapatos
de seguridad 420, Chaleco reflectante 392, Guantes de protección 392,
Gafas 357, Protección auditiva 302, Arnés de seguridad 295,
Mascarilla buconasal 233, Cinturón con amarre 182, Ropa ignífuga 155,
y ~20 categorías más hasta 4.314) -- mismo tipo documental `EPIS`
correcto para las 4.314, sin necesidad de partir el catálogo como
tocó hacer con `FORMACION` en H36 (ahí no había ningún campo
estructurado que distinguiera cursos; aquí sí).

**Descubrimiento real al restaurar:** las 4.314 entregas apuntan a
solo **756 documentos distintos** -- varias entregas comparten el
mismo documento de origen (un mismo parte/recibo de entrega lista
varios EPIs a la vez, p. ej. casco + guantes + botas en un solo
papel). Restaurados los 756 (`deleted_at`/`deleted_by` a `None`, sin
tocar tipo, nombre ni carpeta -- ya estaban correctos) vía Comando S,
verificado con consulta real antes/después (756 en papelera -> 0).

### Vinculación de las fichas técnicas al EPI real del catálogo, y copias para los productos secundarios

Miguel Ángel pidió enlazar los 2 documentos `FICHA_TECNICA_EPI`
restaurados a su EPI concreto (mecanismo genérico
`domain_content_type`/`domain_object_id` -> `EpiItemCatalog`, real
desde S76, con 7 documentos ya vinculados de antes):

- pk 23093 (folleto MIGUEL MIRANDA S.L.) -> `ARNES_SEGURIDAD` (pk 27).
- pk 22915 (certificado Portwest) -> `PANTALON_ALTA_VISIBILIDAD` (pk
  8, mención literal "T501" en la etiqueta del catálogo).

**Problema real detectado al enlazar:** cada uno de los 2 documentos
cubre más de un producto -- el folleto MIRA es en realidad dos fichas
en un mismo PDF (arnés 12A + equipo de amarre E15C) y el certificado
Portwest cubre tres prendas (T501 pantalón, T180 polo, T181
camiseta), pero el mecanismo genérico solo admite un
`domain_object_id` por fila. Solución real, a petición explícita de
Miguel Ángel: **copiar de verdad el blob en GCS** (no se puede
apuntar dos filas vivas al mismo `blob_name` -- restricción real
`unique_live_blob_per_bucket` sobre `bucket`+`blob_name_hash`) y crear
una fila nueva de `DocumentIndexEntry` por cada producto adicional,
mismo patrón real de creación que `subject_upload_service.
upload_subject_document()` (`download_bytes`/`upload_bytes` de
`spare_parts.gcs_service`, `path_digest` para los hashes). 3 copias
reales creadas:

| pk nuevo | Copia de | EPI vinculado |
|---|---|---|
| 49800 | 23093 (folleto MIRA) | `ELEMENTO_AMARRE` (pk 28) |
| 49801 | 22915 (certificado Portwest) | `POLO_ALTA_VISIBILIDAD` (pk 4) |
| 49802 | 22915 (certificado Portwest) | `CAMISETA_ALTA_VISIBILIDAD` (pk 33) |

Con esto, los 6 productos reales cubiertos por los 2 documentos de
hoy quedan cada uno con su propia ficha técnica vinculada en el
catálogo.

### Botón "Ver" en las entregas de EPI de la ficha de personal, y refactor real de los dosieres

Miguel Ángel preguntó por el estado real de la interfaz tras la
restauración. Verificado contra el código real: la pestaña "EPIs" de
la ficha (`EpiDelivery.objects.filter(person=person)`) nunca dependió
del estado de papelera del documento -- siempre mostró correctamente
qué EPI y cuándo. Lo que sí faltaba: **ningún sitio de la interfaz
enlazaba al documento real de una entrega concreta** (ni la fila de
la tabla ni el modal de historial, que solo pintaba la fecha).

**Añadido:** columna "Documento" con botón "Ver" en la tabla de EPIs
de la ficha (`_personal_detail.html`), reutilizando la vista ya
existente `DocumentViewView`/`documentation_document_view` (URL
firmada de GCS), igual que ya hacía el botón de "Ficha técnica".

**Refactor real de los dosieres, decisión explícita de Miguel Ángel
("ahora no generamos el documento de entrega, sino que entregamos el
PDF correspondiente a las entregas últimas de cada EPI. El documento
se generará en otra interfaz, la que se ocupe de las firmas con
Docuten"):**
- `_resolve_template_epi_deliveries()` ya no devuelve TODAS las
  entregas reales de cada EPI marcado -- solo la MÁS RECIENTE de
  cada uno (mismo criterio "última entrega" que la propia ficha).
- `_build_dossier_pdf_bytes()`/`_build_dossier_zip_bytes()` ya NO
  generan la página sintética `_build_epi_section_page()`
  ("ENTREGAS DE EPI INCLUIDAS EN ESTE DOSSIER" + lista de texto,
  "SIN FIRMA TODAVÍA") -- el `source_entry` real de cada entrega se
  mezcla con el resto de `entries` del dosier exactamente igual que
  cualquier otro documento (misma descarga, misma conversión a PDF,
  mismo criterio de formato no soportado; en el ZIP, misma carpeta
  por familia, nunca una carpeta aparte "entregas-epi/" con un
  resumen inventado). `_build_epi_section_page()` queda definida sin
  uso -- generar un documento de acreditación de entrega pasa a ser
  responsabilidad de la futura interfaz de firma con Docuten, no de
  este dosier. Verificado que los 3 puntos reales de llamada
  (aplicación individual de plantilla, generación masiva, envío por
  correo) siguen siendo compatibles sin cambios, misma firma de
  función.

## NOTA DE DESVÍO — S112 (sesión completa desviada a infraestructura cross-proyecto)

La sesión completa (S112) se dedicó a infraestructura de solo lectura
común a cualquier proyecto de la plataforma, no a la hoja de ruta
propia de H31 (Docuten/circulares). Motivo real: al descargar un
archivo de prueba real (el contrato vigente de Miguel Ángel, MUÑOZ
CARA MIGUEL ANGEL, DNI 74633524L, como caso de prueba del nuevo
mecanismo `file_fetch.yml`) se detectó que el patrón de comitear
resultados a git (usado desde S107 en `db_query.yml`) expone
permanentemente en el historial cualquier dato de persona -- riesgo
real si el repositorio se hace público algún día (motivo real:
agotar la cuota de minutos de Actions de un repo privado, compartida
en la cuenta gratuita de GitHub, mientras que los públicos tienen
minutos ilimitados).

**Trabajo real de la sesión:**
1. Estudio y descarte del mecanismo de artifacts de GitHub Actions
   como vía de entrega (falla siempre, host de blob storage no
   determinista fuera de la lista de red permitida del modelo) -- dos
   pruebas reales, ambas negativas, documentadas y retiradas.
2. Construcción de `file_fetch.yml` y migración de `db_query.yml`,
   ambos migrados de comitear a git a subir el resultado a una
   carpeta de Google Drive ("EnterpriseBot - Intercambio Claude",
   `id: 1SSHSY2FHt-7eN17Wgza2Qcybs-ij6to0`), leída directamente por el
   conector de Drive del modelo -- nunca más se comitea a git ningún
   resultado con datos de personas.
3. Descubrimiento real de que `db_query.yml` llevaba desde S107
   comiteando resultados con datos de personas -- ~150 commits
   históricos.
4. Purga completa del historial con `git filter-repo` (dos veces: una
   tras el hallazgo inicial, otra tras retirar los commits de
   depuración de la propia migración), con force-push y
   realineamiento del checkout del servidor sin usar `git reset
   --hard` (prohibido, `com-bash-commands` sección 7) -- vía rama
   nueva (`git fetch` + `git branch -m` + `git checkout -b`). Dos
   ramas de respaldo quedan en el servidor sin borrar
   (`main-old-S112`, `main-old-S112b`).
5. Nueva skill común `com-actions-relay` (creada y guardada por
   Miguel Ángel vía `skill-creator`), que documenta el mecanismo
   completo para que cualquier proyecto de la plataforma lo reutilice
   sin volver a comitear resultados a git.
6. Bugs reales corregidos por el camino: ruta de venv mal asumida,
   `PYTHONPATH` que falta al ejecutar un script por ruta absoluta,
   heredocs anidados que rompen YAML dentro de un bloque `run: |`,
   `MediaIoBaseUpload` sin `mimetype` obligatorio.
7. Decisión explícita de Miguel Ángel: la limpieza de la carpeta de
   Drive (papelera) se hace por lotes al cierre de sesión, no archivo
   a archivo -- documentado en `com-actions-relay` sección 1bis.

**El marcador `← EN PROGRESO` de H31 no cambia** -- la hoja de ruta de
H31 (Docuten, circulares) no avanzó, pero sí se añade un punto nuevo
y prioritario (ver Hoja de Ruta abajo), a petición explícita de
Miguel Ángel al cierre.

## COMPLETADAS EN S113 (continuación, tras compactación de contexto) -- sistema completo de entrega de EPIs por lote, rediseño íntegro de la interfaz de Personal (grupos de reparto, visor de selección, "Requisitos de documentación"), 39 commits reales

Esta sección cubre el resto de la sesión S113 a partir del commit
`4465aa1` (punto de partida capturado tras el checkpoint intermedio
ya documentado arriba -- fichas técnicas, botón Ver, refactor de
dosieres). Sesión larga y muy extensa, con varios bloques de trabajo
real independientes.

### Bloque 1 -- Correcciones reales en la pestaña Documentación → EPIs

- Un solo apellido mostrado en la tabla (faltaba `second_surname`,
  tanto en la plantilla como en el filtro de búsqueda del backend) --
  corregido.
- Sin botón "Ver" documento en esta pestaña (fragmento independiente
  de la ficha de persona, nunca tuvo el modal/JS del visor) --
  añadido, verificado contra BD real (4.314/4.314 `EpiDelivery` con
  `source_entry_id`).
- Dos campos nuevos en `PersonIdentity` (migración `0121`):
  `phone_secondary` y `professional_category` (esta última, rellenada
  a mano, es la categoría profesional pensada para gobernar en el
  futuro qué EPIs corresponden a cada trabajador -- explícitamente
  DISTINTA del sistema de "Requisitos de documentación", ver más
  abajo).
- `ss_affiliation_number` deduplicado: existían dos definiciones
  distintas del mismo campo en el modelo (max_length 32 y 30) --
  unificado, migración `0122`, solo metadatos.

### Bloque 2 -- Sistema completo de entrega de EPIs por lote, con documento PDF real

Construido de cero: `CompanyFiscalProfile` (CIF/dirección fiscal por
razón social, con alias por nombre, sembrado con las 4 empresas
reales de Grupo Álvarez -- Gruas Adolfo Alvarez, Transgrual,
Asistencia y Gruas Granada, Grualdi) y `EpiDeliveryBatchTemplate`
(lote reutilizable de EPIs, M2M a `EpiItemCatalog`). Generador de
documento real (`epi_delivery_document_service.py`, PyMuPDF, formato
calcado de un documento real de entrega en papel) y vista unificada
`EpiBatchDeliveryExecuteView` que sustituye a las dos vistas
anteriores de entrega individual/masiva (S74/S75): un POST crea las
`EpiDelivery` reales, genera el PDF por persona y lo sube como
documento real de esa persona.

**Incidente real corregido en el propio bloque:** un `str_replace` al
insertar los modelos nuevos borró por accidente
`class DocumentAcknowledgment(models.Model):`, dejando su docstring
como cadena suelta -- no detectado por `py_compile` (sintaxis válida
igualmente). Detectado y corregido en el mismo bloque con inventario
AST (`ast.ClassDef`) antes de comitear -- desde ahora, cualquier
edición de `models.py` que inserte clases nuevas se verifica así
antes de comitear, no solo con `py_compile`.

### Bloque 3 -- UX de la gestión de lotes de EPIs (varias iteraciones sobre la propia sesión)

CRUD de lotes centralizado en la propia pestaña EPIs (sin página
aparte), rediseñado en 3 columnas fijas y simétricas -- visor de
lotes guardados (casillero de selección única) / panel de gestión
(vacío hasta activarse) / visor del contenido del lote, coloreado por
familia con el mismo criterio en los tres sitios donde aparece
(catálogo, modal de entrega masivo, formulario de entrega individual
de la ficha). Aviso del navegador (`beforeunload`) si hay cambios sin
guardar. Guardar/eliminar dejó de recargar la página (toast
auto-oculto en su lugar) -- mismo criterio extendido después a
plantillas de dosier, grupos de reparto y "Requisitos de
documentación".

**Corrección real de estilo, no solo de plantillas de dosier**: el
casillero de Bootstrap (`margin-left:-1.5em` sobre el
`padding-left:1.5em` propio de `.form-check`) quedaba tapado por la
franja de color de familia cuando se aplicaba `px-2` directamente
sobre el mismo elemento (la utilidad, con `!important`, rompe el
cálculo del margen negativo) -- corregido separando el color en un
contenedor exterior con más padding, `.form-check` interior intacto,
en los tres sitios donde aparece.

### Bloque 4 -- Modal de entrega de EPIs: visor de contenido

Miguel Ángel: "se echa en falta el visor de contenido que nos indique
qué EPIs se van a entregar, para no tener que estar scrolleando el
catálogo". Añadido a los dos modales de entrega (masivo e individual)
un visor en vivo junto al checklist, misma columna de color por
familia.

### Bloque 5 -- Rediseño íntegro de la pestaña Personal (varias iteraciones, corregidas en la propia sesión a petición de Miguel Ángel)

Trabajo más extenso de la sesión, en varias vueltas sucesivas:

1. **Barra de acción masiva** dejó de ocultarse hasta marcar a
   alguien -- siempre visible, en la parte fija de la pantalla.
2. **Grupos de reparto**: CRUD completo nuevo (`PersonGroupTemplate`
   solo tenía creación, S109) -- `PersonGroupTemplateSaveView`/
   `DeleteView` (guardar/editar/eliminar sin recargar, toast), visor
   de grupos guardados con selección única, y un **visor de
   SELECCIÓN ACTUAL** (nombres, no solo un contador) que resuelve la
   queja real de Miguel Ángel sobre "Cargar grupo": antes no había
   forma de ver quién quedaba seleccionado si los miembros del grupo
   no estaban en la página/filtro visible en ese momento.
3. **Reestructuración de la disposición, dos vueltas completas** a
   petición explícita de Miguel Ángel tras revisar el resultado de la
   primera: la intención final es dar al listado de trabajadores
   **al menos dos tercios de la altura de la pantalla**, comprimiendo
   al máximo la gestión de arriba. Resultado final: filtros de
   Empresa, gestión de grupos (guardados + gestión, combinados en una
   sola columna con flex-column -- la lista de guardados crece para
   ocupar el hueco disponible y hace scroll, la gestión queda anclada
   abajo) y acciones masivas (rejilla 2x2 por categoría: Puesto/EPIs/
   Información/Dosieres) comparten TODOS una única fila compacta
   arriba; el listado de trabajadores (2/3 del ancho) y el visor de
   SELECCIÓN ACTUAL (1/3 del ancho) comparten fila abajo, misma
   altura fija (68vh).
4. **Ajustes finos del listado**: cada trabajador en una sola fila
   (`white-space:nowrap` + scroll horizontal del contenedor, antes
   los nombres largos partían la fila en dos líneas), fecha de Alta
   en formato `dd/mm/aaaa` explícito.
5. **Casilla "Mostrar solo la selección actual"**: sustituye por
   completo los filtros de Estado/Empresa (nunca los combina)
   mientras esté marcada, mostrando en el listado exactamente a
   quienes están seleccionados ahora mismo (JS de `selection`,
   sincronizado en vivo vía `only_selected`/`selected_ids` en el
   propio formulario htmx).

### Bloque 6 -- "Puesto" renombrado a "Requisitos de documentación" (solo interfaz, sin tocar código)

Miguel Ángel detectó una confusión conceptual real: el modelo
`JobPosition` (documentación obligatoria por puesto, para el aviso de
"documento faltante") no tiene nada que ver con la categoría
profesional pensada para EPIs (Bloque 1) -- no tiene sentido una
"entrega general de EPIs" (sería absurdo dar guantes a un
administrativo). Ambos sistemas se mantienen deliberadamente
separados; lo único que cambió es el nombre visible del primero, que
inducía a pensar que debía abarcar también EPIs/información.
Decisión explícita: **"Requisitos de documentación"**.

Cambio puramente de rótulo -- decisión explícita de no tocar
identificadores internos de código (clase `JobPosition`, campo
`job_position`, vistas, URLs `/puestos/...`) sobre una app en
producción real, cuando el problema era solo de nomenclatura de cara
al usuario. Migración `0125` (solo metadatos: `verbose_name`). Página
de gestión (`job_positions/manage.html`) alineada al mismo formato
que dosieres/lotes (checklist + visor sticky + CRUD sin recarga).
Extendido también: columna en el listado de Personal
(`select_related` para evitar N+1), inclusión en la búsqueda
(`job_position__name__icontains`), y modal de confirmación antes de
asignar el requisito de forma masiva (Miguel Ángel: "ahora mismo no
hay ningún tipo de filtro, directamente se añaden [...] para evitar
los cambios por error").

### Pendiente sin iniciar -- Docuten, API REST de firma de documentos

Miguel Ángel habló con Yolanda (responsable real de documentación) y
con el propio chatbot de soporte de Docuten: Docuten ofrece acceso
por API REST, y el chatbot dio una dirección de correo para
solicitarlo. Uso exclusivo previsto, confirmado explícitamente a
Docuten: generación del documento, preparación de la firma, envío
del enlace de firma por WhatsApp, y recogida del documento ya firmado
-- nunca más alcance que ese. Miguel Ángel pidió investigar primero
la documentación real de la API REST de Docuten (proceso de firma,
credenciales/token que hay que solicitar, coste adicional si lo
hubiera y cómo se factura) y, con esa información, redactar el correo
de solicitud del servicio -- explícitamente aplazado a la sesión
siguiente ("dejamos esto último para la siguiente sesión"), sin
ninguna investigación ni borrador todavía. Ver punto 1 de la Hoja de
Ruta.

### COMPLETADAS EN S114

Sesión larga, con un giro real de rumbo a mitad de camino: empezó
retomando el punto 1 de la hoja de ruta de S113 (Docuten) y acabó
dedicada casi entera al punto 2 (circulares), corrigiendo por el
camino un diseño equivocado desde la base y arreglando varios
incidentes reales de datos descubiertos durante el propio trabajo.

**Docuten (punto 1 cerrado).** Investigada la documentación pública
de la API REST de Docuten -- no hay especificación técnica accesible
(endpoints, autenticación) publicada; solo se confirma que ofrecen
integración por API Key (visible en su conector de Google Docs) y su
condición de PCSC bajo eIDAS. Con eso, redactado y enviado (por
Yolanda, a la dirección que ella obtuvo del chatbot de soporte de
Docuten) el correo de solicitud de acceso a la API REST, con el caso
de uso exclusivo ya acotado (generación de documento, preparación de
firma, envío del enlace por WhatsApp, recogida del documento firmado)
y las preguntas concretas sobre credenciales/token y coste. Sigue sin
respuesta de Docuten -- bloqueado, sin acción de código posible.

**Corrección de scroll en la pestaña Personal (tres intentos hasta
dar con la solución correcta).** Miguel Ángel reportó con captura que
la pestaña hacía scroll de página completa pese al rediseño de S113.
Primer intento (68vh fijo → cálculo de altura por JS basado en
`top offset`) dejó un remanente real de scroll. Segundo intento
(álgebra de "exceso real" contra `document.documentElement.
scrollHeight`) tampoco lo resolvió. Tercer intento -- una cadena
flexbox real desde `.main-content` (mismo principio que
`.page-content-flush` de la vista de chat) -- sí eliminó el scroll de
página, pero rompió por completo el scroll interno del listado y del
visor de selección (ni barra ni desplazamiento posible). Solución
final: revertido íntegro el cambio de flexbox global, sustituido por
un mecanismo acotado y autocontenido dentro de la propia pestaña (un
panel con altura calculada por JS una sola vez, reutilizando el
patrón h-100+flex ya probado y en producción desde S113 para "Grupos
de reparto"). De paso, rediseño visual pedido por Miguel Ángel:
panel superior (botones + filtros/grupos/acciones) y panel inferior
(listado + selección) como dos rectángulos grandes de esquinas
redondeadas, con las dos columnas del panel inferior ahora con
estilo idéntico (antes tenían aspecto distinto entre sí).

**Corrección de fondo del scope de circulares.** Al abrir la pantalla
real de "Circulares y notificaciones", Miguel Ángel encontró que
listaba el catálogo ENTERO de tipos documentales de persona (~73
filas: DNI, nóminas, formación, salud...) en vez de una lista acotada
de plantillas de comunicación reutilizables -- el filtro original
(S75) usaba `domain`, criterio equivocado. Verbatim: "eso es un
galimatías [...] aquí vamos a tener unas 10, 15, 20 plantillas como
mucho". Corregido con un campo nuevo, `DocumentTypeCatalog.
is_notification_template` (migración 0126), único criterio real a
partir de ahora -- marcado `True` en 8 tipos ya existentes con uso
histórico real confirmado (`DocumentAcknowledgment`: RECURSO_
PREVENTIVO 57 usos, ENTREGA_INFORMACION 51, NOMBRAMIENTO_* varios,
PLAN_ACTUACION_CALOR 8, CIRCULAR_INFORMATIVA) y en 4 tipos nuevos
pedidos explícitamente por Miguel Ángel (CIRCULAR_CAMBIO_HORARIO,
CIRCULAR_CIERRE_INSTALACIONES, CIRCULAR_EVENTO_EMPRESA, CIRCULAR_
PROTOCOLO_ACTUACION). Limpiadas también las etiquetas de dominio
visibles en el panel, que llevaban coladas notas internas de
desarrollo ("Empresa y obra (CompanyWorksite, H30 S58)") -- ahora
"Empresa y obra" a secas (migración 0127).

**Incidentes reales de datos encontrados y corregidos sobre la
marcha.** Revisando las plantillas vigentes (archivo) de las 12
circulares, aparecieron dos rotas: la de `CIRCULAR_INFORMATIVA`
("Circular Leave Letter.doc") resultó ser, verificado por Miguel
Ángel abriéndola en Word, una carta real de ANAGRUAL (agrupación de
grúas) sobre exención de tacógrafo -- no una circular de Grupo
Álvarez, mal atribuida; y la de `RECURSO_PREVENTIVO` daba 404 real al
pulsar "Ver" porque el archivo estaba en la papelera. Migración 0128
limpió ambas referencias. Investigando la segunda, se descubrió que
ese mismo instante (2026-08-27 10:19:55, mismo usuario) había
mandado a la papelera **183 elementos**, no solo esa plantilla --
casi con toda seguridad el barrido deliberado de H36/S110 ("papelera
para inactivos y tipos fuera del Excel"), en el que 3 plantillas de
circular se colaron por error. Migración 0129 restauró esas 3
(`INFORMACION_MEDIDAS_PROTECCION`, `NOMBRAMIENTO_JEFE_MANIOBRAS`,
`NOMBRAMIENTO_RESPONSABLE_SEGURIDAD`) y la de `RECURSO_PREVENTIVO`,
sin tocar las ~179 restantes (fuera de alcance de esta sesión). Más
tarde, ya en producción, apareció un `NoReverseMatch` real
(`documentation_personal_notify` con `pk=250`) al abrir una ficha de
persona -- bug preexistente desde que se escribió la URL (nunca
llevó `<int:pk>`, pese a que la vista sí lo espera desde S74), nunca
disparado hasta ahora porque el desplegable de notificación llevaba
años sin filas que renderizar. Corregido añadiendo el `<int:pk>` que
faltaba.

**Documentos programáticos con variables (pedido nuevo de Miguel
Ángel, cambio de enfoque sobre la marcha).** Corrección explícita:
"las plantillas deben ser programáticas [...] elegimos la empresa, el
administrador y el trabajador y se genera el documento ad-hoc".
Construido: `CompanyFiscalProfile.administrator` (FK a
`PersonIdentity`, migración 0130) -- **nunca asumido de memoria**,
verificado contra un contrato real (modelo SEPE, campo "EN CONCEPTO")
de un trabajador de cada una de las 4 empresas, descargado y leído en
esta misma sesión; reveló que la suposición inicial de Miguel Ángel
("Adolfo en todas excepto Asistencia y Grúas Granada") era incorrecta
para Grualdi, cuyo administrador real es José Luis Álvarez Díaz.
Sustitución de variables `{{trabajador.*}}`, `{{administrador.*}}`,
`{{empresa.*}}`, `{{fecha}}` en `content_html`
(`_render_document_variables`); pantalla nueva "Generar documento"
(elegir empresa + buscar trabajador, administrador resuelto solo) que
genera el PDF real y lo guarda en la carpeta del trabajador
(`upload_subject_document`, mismo mecanismo que la entrega de EPIs);
botón "Insertar variable" en el editor para no tener que teclear los
tokens a mano.

**Contenido real de las 6 circulares con documento de ejemplo.**
Descargados y leídos los documentos reales de `RECURSO_PREVENTIVO`,
`NOMBRAMIENTO_JEFE_MANIOBRAS`, `NOMBRAMIENTO_RESPONSABLE_SEGURIDAD`,
`INFORMACION_MEDIDAS_PROTECCION` y `CIRCULAR_INFORMATIVA` (esta
última: la circular real de Grupo Álvarez sobre permiso de conducir,
distinta del archivo de ANAGRUAL detectado como mal atribuido) --
`content_html` rellenado con el texto real de cada una, variables ya
puestas en su sitio en la propia redacción (migración 0131).
`PLAN_ACTUACION_CALOR` queda fuera a propósito: su documento de
ejemplo resultó ser un folleto oficial del Ministerio de Sanidad
firmado como acuse de recibo, no un texto de Grupo Álvarez con huecos
-- sigue con su plantilla en archivo, sin `content_html`.

**Retirada de la plantilla legacy en archivo de la pantalla de
editar circular.** Miguel Ángel: "eliminaría el tema del legacy [...]
es una cosa que no interesa y complica". Retiradas
`CircularTemplateUploadView`/`CircularTemplateClearView`, sus URLs y
el helper de subida -- el campo `current_template` sigue en el
modelo (lo usan otros tipos fuera de circulares) pero ya no tiene
ningún punto de entrada aquí. Aligerado también el texto de
"Importar desde Word/PDF" (quitada la advertencia "no perfecto,
revísalo") y fusionadas en el listado las dos columnas de estado en
una sola "Plantilla" (Sí/No), sin exponer de dónde viene el contenido
-- Miguel Ángel: "al usuario final le da igual de dónde venga la
plantilla [...] lo que importa es que tenga o no tenga plantilla".
Aplicada también, por primera vez como directriz general de aquí en
adelante, "pantalla fija, scroll solo en el contenido interno que lo
necesite" a la propia pantalla de editar circular (el editor de texto
es el único que hace scroll).

**Investigación de WhatsApp/Meta/Twilio para el envío de circulares
(diseño cerrado, nada construido todavía -- ver Hoja de Ruta).**
Confirmado que no existe ninguna plantilla de WhatsApp aprovechable
para circulares (las 13 reales en `WhatsAppTemplate` son de otros
flujos). Diseño acordado con Miguel Ángel tras verificar en línea la
documentación actual de Twilio (no de memoria, corrigiendo un primer
diseño equivocado con `twilio/call-to-action`, que NO admite mezclar
quick-reply con URL): plantilla `twilio/card` (sí lo admite, una vez
aprobada), categoría UTILITY, botón quick-reply "Leer aquí" + botón
URL "Ver en navegador"; coletilla ya aprobada ("consta como
trabajador de Grupo Álvarez") + "si no lo es, ignore este mensaje";
saludo al principio, nunca variable al final (lección ya aprendida
con `document_expiry_alert`, rechazada dos veces por eso mismo). Flujo
único para todas las circulares por ahora, sin excluir las que
necesiten firma -- se adaptará cuando llegue Docuten. Acceso al
"buzón" vía login normal, reutilizando el mecanismo de dispositivo de
confianza ya existente (`CompanyUser.trusted_device_token`, cookie
`eb_trusted_device`) -- sin token ni mecanismo de acceso nuevo.

## COMPLETADAS EN S115

Sesión larga, con avance real en varios frentes de la hoja de ruta de
S114 y varios hallazgos importantes tratados sobre la marcha:

1. **Flujo de circulares por WhatsApp construido de punta a punta.**
   Comando de gestión `create_circular_notification_whatsapp_template.py`
   (patrón `requests` crudo, mismo que `epi_delivery_confirmation`)
   crea la plantilla `twilio/card` real y la somete a aprobación de
   Meta -- `content_sid=HXc54b0ea29b774f4081476bb1b3594347`, estado
   `received`, **pendiente de aprobación de Meta al cierre de esta
   sesión (~24h)**. `TrustDeviceQuickLoginView` ajustada para
   respetar `?next=` (antes redirigía siempre a `/panel/`). Backend
   de envío real (`send_circular_notification_whatsapp`, mismo
   patrón que la confirmación de EPI) y webhook del botón "Leer
   aquí" (`ButtonPayload=leer_aqui_circular`) que responde con el
   texto de la circular pendiente y la marca como leída
   (`DocumentAcknowledgment.channel`/`whatsapp_read_at`, migraciones
   0132/0133). Pantalla nueva "Mi buzón" (listado + detalle),
   protegida con login normal, con entrada propia en la sidebar bajo
   "Mi perfil". Verificado end-to-end con tres `DocumentAcknowledgment`
   de prueba reales (pk 122/123/124) creados directamente por consola
   (sin gastar mensajes de WhatsApp reales, aprobación de Meta
   todavía pendiente).
2. **Fix real de un `ImportError` que tumbó el sitio en producción**
   (commit `c96fc02`): `MiBuzonListView`/`MiBuzonDetailView` no
   estaban reexportadas en el facade `panel/views.py`, del que
   `urls.py` importa -- detectado y corregido con el log de error
   real del servidor, no por suposición.
3. **Unificación de identidad CompanyUser↔PersonIdentity↔Contact.**
   Consulta de solo lectura real (vía GitHub Actions, sin que Miguel
   Ángel tuviera que ejecutar nada) reveló que, de 11 CompanyUser
   activos con DNI, 9 ya estaban bien enlazados y 2 no
   (`miguelangel.munoz`/pk=35 y Estevao Veloso/pk=42, ambos con DNI
   coincidente pero sin el FK escrito -- backfill de S74 nunca
   repetido para altas posteriores). Corregido con signals reales en
   ambos sentidos (`document_explorer.signals`/`ivr_config.signals`,
   función compartida `document_explorer.identity_sync.
   sync_identity_link`) para que el enlace se mantenga solo hacia
   adelante, sin backfill manual nunca más. Además: `miguelangel.munoz`
   (CompanyUser+User) y el Contact de pruebas `+34711509585`
   **borrados físicamente** a petición explícita de Miguel Ángel, tras
   confirmar contra BD real que no tenían ningún dato real enlazado
   (0 presupuestos/unidades de asistencia con `PROTECT`, 0 tickets de
   avería). El usuario real de Miguel Ángel es `alvarez_admin`
   (DNI `74633524L`), ahora correctamente enlazado a su `PersonIdentity`
   (pk=250).
4. **Modelo real de Obra construido (app `worksites`), no aplazado
   del todo pese a la deuda técnica 4.23** -- decisión explícita de
   Miguel Ángel de crear ya la tabla (nombre, código autogenerado
   `OBRA-000N`, cliente en texto libre, empresa gestora, ubicación),
   pensada como costura para los futuros modelos Cliente/Proveedor.
   `DocumentAcknowledgment.worksite` y variables `{{obra.*}}` en
   `_render_document_variables`. CRUD mínimo en `/panel/obras/`
   (solo ADMIN). Verificado con una obra de prueba real ("Mercadona
   Summer XDD", cliente "LidoVario").
5. **Formato real de "carta de nombramiento" para las plantillas de
   designación** (`NOMBRAMIENTO_JEFE_MANIOBRAS`,
   `NOMBRAMIENTO_RESPONSABLE_SEGURIDAD`), sustituyendo el formato de
   notificación interna (COMUNICA/TRANSMITE/RECIBE) por el mismo
   formato que un nombramiento real de Grupo Álvarez que Miguel Ángel
   aportó como referencia (título recuadrado, FECHA/EMPRESA, "Sr.
   D./DNI.-", "Muy Sr. nuestro:", cita legal de la Ley de PRL
   -- copiada literal del documento real solo para "interlocutor de
   seguridad", sin inventar base legal para "jefe de maniobras" --,
   bloque de firmas empresa/trabajador/representante). Membrete con
   el logo real a color de Grupo Álvarez (`grupo_alvarez_logo_color.png`,
   aportado directamente por Miguel Ángel tras detectar que el logo
   usado hasta entonces tiene el texto en blanco, ilegible sobre
   fondo blanco -- mismo problema, sin corregir todavía, en el
   membrete del flujo de email `.eml`).
6. **Hallazgo importante, no resuelto en esta sesión:** estas
   circulares de nombramiento no son solo una notificación al
   trabajador -- son el documento acreditativo de la designación de
   cara a la empresa que gestiona la obra (coordinación de
   actividades empresariales/PRL), que habrá que poder incluir en un
   dossier real enviado a esa empresa cliente (caso real citado por
   Miguel Ángel: Sacyr). Registrado en la deuda técnica 4.23 del
   documento maestro -- el modelo de datos ya está listo
   (`DocumentAcknowledgment.worksite`), falta el mecanismo de
   envío/generación del dossier al cliente.

**Migraciones reales desplegadas esta sesión (todas confirmadas
aplicadas en producción con datos reales, nunca solo por el icono
verde de Actions):** `document_explorer` 0132, 0133, 0134, 0135;
`worksites` 0001, 0002.

## Hoja de Ruta pendiente al reactivar H31

1. **WhatsApp -- probar el botón "Leer aquí" contra el webhook real**
   en cuanto llegue la aprobación de Meta (SID `HXc54b0ea29b774f4081476bb1b3594347`,
   ~24h desde el cierre de S115) -- comprobar el estado real con
   `GET .../ApprovalRequests/whatsapp` antes de dar por bueno el
   primer envío real.
2. **Construir el disparador real de envío de circulares por
   WhatsApp desde el panel** -- hoy `send_circular_notification_
   whatsapp()` existe pero nada la llama; el envío por email sigue
   siendo el único operativo desde `PersonalNotificationSendView`/
   `MassSendView`. Añadir la opción de canal WhatsApp ahí (o una
   acción paralela), reutilizando el mismo mecanismo de selección de
   obra ya construido en "Generar documento".
3. **Docuten -- sigue bloqueado en espera de respuesta.** Sin ninguna
   acción de código posible hasta que Docuten responda -- comprobar
   al arrancar si ya ha llegado respuesta.
4. **Contenido real de las 7 plantillas de comunicación que aún no lo
   tienen** (`ENTREGA_INFORMACION`, `NOMBRAMIENTO_RECURSO_PREVENTIVO`,
   `CIRCULAR_CAMBIO_HORARIO`, `CIRCULAR_CIERRE_INSTALACIONES`,
   `CIRCULAR_EVENTO_EMPRESA`, `CIRCULAR_PROTOCOLO_ACTUACION`, y
   cualquier otra dada de alta desde entonces) -- criterio de cierre:
   `content_html` no vacío en las 7, o decisión explícita registrada
   de dejarla vacía (mismo caso que `PLAN_ACTUACION_CALOR`). Si el rol
   de la plantilla es de designación/nombramiento, aplicar el mismo
   formato de carta real de S115 (título recuadrado, firmas), no el
   de notificación.
5. **Dossier de nombramientos al cliente de la obra** (hallazgo 6 de
   S115, deuda técnica 4.23) -- diseñar el mecanismo de envío/
   generación cuando se aborde el ecosistema Obra/Cliente/Proveedor.
6. Los 2 huecos reales de documentación (Grana Álvarez, García
   Sánchez) siguen pendientes de que la supervisora escanee y suba
   los contratos originales -- sin acción de código pendiente, solo
   enlazar `prorroga_de` cuando lleguen.
7. **Alta de EPIs desde el panel y entrega con máquina** (añadido en
   S135, desvío desde H30). Miguel Ángel no encontraba cómo dar de
   alta un EPI nuevo: en el panel no existe. `EpiItemCatalog` solo se
   ha llenado por migraciones (S71-S73, botiquín en `0055`, V16 en
   `0191` de S135), aunque su docstring prevé desde S046 una opción
   "nuevo EPI" en el propio desplegable de entrega. Construir:
   - "+ Nuevo EPI" en el desplegable de entrega, y alta y edición en la
     pestaña EPIs (familia, nombre, revisión periódica, vida útil en
     años, norma UNE-EN, coste de reposición).
   - Entrega con persona **y máquina** desde el panel (Miguel Ángel,
     S135: *"La entrega debe ser análoga a los botiquines, persona y
     máquina"*). `EpiDelivery.destination_machine` existe desde S72
     (`0054`), pero el flujo de entrega del panel
     (`EpiBatchDeliveryExecuteView`) no lo rellena nunca: solo lo
     usaron los extractores históricos de botiquines. Aplica al
     botiquín y al V16.
   **Cierre:** en producción, un EPI dado de alta desde el panel sale
   en el desplegable de entrega; una entrega de V16 a una persona con
   un centro de gasto queda en BD con `destination_machine` puesto.



## REACTIVADO EN S134 -- Hoja de Ruta S134/S135 (concertada con Miguel Ángel; va antes que la "Hoja de Ruta pendiente al reactivar H31", que sigue intacta)

PCH desde H37 en S134 (23/10/2026). Miguel Ángel, verbatim: *"Necesito
pivotar hacia documentación. [...] Hay que dotar al sistema de un
pipeline en los DNI y permisos con foto para extraer la foto y
colocarla como foto de la persona y además PDF descargar la foto en
png y con un tamaño máximo de 128kb"*.

Punto de partida real del código:
- La foto de la persona es hoy `PersonIdentity.avatar_document` (H35,
  S105): un documento-imagen ya indexado, elegido a mano
  (`views_documentation_h30.py`, vista que fija el avatar).
- Se enseña el documento entero (el DNI o el carné completo), no la
  cara recortada.
- Si no hay avatar elegido, `PersonalDetailView` cae al documento de
  tipo `IMAGEN`.

1. **Pipeline de foto de carné.**
   1. De los DNI y permisos de conducir de cada persona (imagen o
      PDF), sacar la foto de la cara.
   2. Ponerla como foto de la persona.
   3. Poder descargarla en PNG de 128 KB como máximo.
   **Cierre:**
   - una persona real con DNI indexado tiene su foto recortada como
     foto de ficha;
   - la descarga da un `.png` de ≤ 128 KB, comprobado con el tamaño
     real del archivo;
   - lo mismo con una persona que solo tenga permiso de conducir.

## COMPLETADAS EN S134 (23/10/2026, PEE PC; punto 1 de la Hoja de Ruta S134/S135 -- foto de carné)

Pausado de nuevo al cierre de S134 por PCH a H37 (Miguel Ángel:
*"volver con los servicios de la asistencia en la siguiente"*). La
"Hoja de Ruta pendiente al reactivar H31" sigue intacta.

### 1. Foto de carné sacada del DNI o del permiso -- `8fb132a`

- Migración `document_explorer` 0189:
  - `PersonIdPhoto` (uno por persona, JPEG en BD, documento de origen);
  - `PersonIdentity.photo_attempted_at`.
- `document_explorer/id_photo_service.py`:
  - busca la cara con Cloud Vision en DNI, NIE, pasaporte, permiso de
    conducir e imágenes (imagen o 2 primeras páginas del PDF);
  - recorta 3:4 alrededor de la cara más grande.
- Tarea `extract_id_photos_task` cada 15 min (10 personas por vuelta):
  personas nunca revisadas con documentos, o con un documento nuevo.
- Ficha:
  - la foto recortada manda sobre `avatar_document`;
  - icono del ojo con la ventana "Ver foto": foto grande, documento de
    origen, "Sacar del DNI o permiso" y "Descargar foto para
    plataforma".
- Descarga: PNG de 128 KB como máximo, nombre
  `APELLIDO1_APELLIDO2_NOMBRE.png` (Miguel Ángel: *"se descarga con el
  nombre de la persona en formato PNG y con menos de 128K"*).
- **Comprobado en producción:**
  - migración aplicada (consulta a BD);
  - la tarea sacó la foto de la persona 5 (de un permiso de conducir
    en JPEG) y de la 250 (de un DNI en PDF), según el log;
  - Miguel Ángel descargó la foto para plataforma.

### 2. Recuadro para la plataforma -- `02bf546`

Miguel Ángel: *"la plataforma pide que salga la cara principalmente y
que la cara ocupe la máxima cantidad posible en la foto"*.

- En "Ver foto" se arrastra un recuadro sobre la foto y la descarga es
  solo ese recuadro (`?x&y&w&h` en fracciones), en PNG ≤ 128 KB.
- **Probado en local con Playwright:** recuadro de la mitad de ancho y
  alto, PNG con la mitad de tamaño y nombre correcto.

### 3. Subida directa de la foto de perfil -- `bcceb63`

- Problema visto en producción: el botón de la cámara subía la foto
  por la subida de documentos (IMAGEN en GCS y dos lecturas de
  Gemini, lento), y la foto recortada del DNI tapaba la subida.
- Ahora la cámara sube la foto a `foto/subir/`:
  - sin GCS ni Gemini;
  - se endereza, se pasa a JPEG y se limita a 800 px de alto.
- Migración 0190: `PersonIdPhoto.is_manual`. Una foto subida o elegida
  a mano ya no la cambia la tarea, solo el botón "Sacar del DNI o
  permiso". **Aplicada en producción** (consulta a BD).
- **Probado:** en local (0,07 s; la tarea la salta); Miguel Ángel subió
  en producción su foto recortada.

### 4. "Sacar del DNI o permiso" prefiere los documentos de identidad -- `efdb576`

- Problema visto en producción: tras subir la foto, el botón volvía a
  sacar la cara de la foto recortada. El primer intento de subida la
  había archivado como IMAGEN, más reciente que el DNI.
- Ahora van primero DNI, NIE, pasaporte y permiso, y las imágenes solo
  si ninguno tiene cara.
- **Probado en local** con una IMAGEN más reciente que el DNI: usa el
  DNI.

### Otros

flake8 a 0 en los archivos tocados: `panel/views_documentation_h30.py`
y `panel/urls.py` enteros, y `document_explorer/tasks.py`.

## COMPLETADAS EN S136 (sesión invasora, 23-24/10/2026, PEE PC; en paralelo con H30 S135)

Sesión invasora (directriz 4.11, Caso A del enrutador): H30 sigue EN
PROGRESO y no se ha tocado ninguna hoja de ruta. Arrancó en
`4a8f5ab`. Todo desplegado y con el Action en verde.

### 1. Foto de carné: pipeline corregido y fotos ya puestas rehechas -- `9eb218b`

Encargo de Miguel Ángel: había fotos giradas, otras salían de
documentos ya obsoletos, y en los documentos nuevos la foto está en la
cara de atrás. Datos de producción al empezar (consulta a BD): 140
fotos, **50 sacadas de un documento obsoleto**, porque los candidatos
se ordenaban por `indexed_at` y casi todos se indexaron el mismo día
(29/07/2026). En el log, `Image too large. Please limit to 75
megapixels` en un PDF de página enorme.

- `id_photo_service.candidates()`: primero los documentos de
  identidad, los vigentes antes que los obsoletos y del que caduca más
  tarde al que antes (después la emisión y el indexado); las imágenes
  al final. Los obsoletos solo se usan si ningún vigente tiene cara.
- `crop_photo()`: si la cara más grande no está derecha (`roll_angle`
  de 45° o más) o no se ve ninguna, prueba la página girada 90, 270 y
  180 y usa la primera en la que la cara sale derecha. Solo hacen esa
  llamada de más los documentos de lado y las caras de atrás sin foto.
- `_pages()`: las páginas se limitan a 20 MP.
- Migración **0192** (`RunPython`): `photo_attempted_at` a NULL para
  todas las personas sin foto puesta a mano; la tarea de cada 15 min
  las ha vuelto a pasar. **Comprobado en producción:** migración
  aplicada; primeras pasadas correctas en el log (personas 3 y 6, que
  tenían foto de un DNI obsoleto, la sacan de su permiso y su DNI
  vigentes). **Estado final (consulta del 24/10):** 169 fotos, 2
  puestas a mano, **0 personas en cola**, 19 fotos aún de un documento
  obsoleto (personas en las que ningún documento vigente tiene una
  cara que Cloud Vision detecte).
- Probado en local con un DNI real escaneado de lado (Cloud Vision
  simulado): 2 llamadas, recorte derecho de 3:4.

### 2. Ventana de gestión de la foto de perfil -- `a72fa0a`, `3ec9420`, `de1314a`

Miguel Ángel: los iconos de ver y cámara iban muy juntos; un solo icono
de configuración con la foto a tamaño completo y todas las opciones.

- Ficha: un solo icono (engranaje) que abre la ventana. En ella: foto
  grande con el recuadro para la plataforma; estado (automática o
  puesta a mano) y su documento de origen; subir foto nueva; sacarla
  de un documento elegido (desplegable con los vigentes primero);
  girar a izquierda o derecha; pasar a modo automático; descargar el
  PNG para plataforma. Las acciones de cambio, solo para
  DOCS_SUPERVISOR y ADMIN.
- Vistas: `PersonalPhotoExtractView` (con `entry`: de ese documento y
  queda puesta a mano; sin él: `set_automatic`),
  `PersonalPhotoRotateView` (`foto/girar/`), `PersonalPhotoQueueView`
  (`foto/cola/`, acción masiva **"Volver a sacar la foto"** en la
  pestaña Personal).
- `3ec9420`: un nombre de archivo largo se salía de la ventana.
- `de1314a`: la miniatura del listado de Personal salía de lado aunque
  en la ficha ya estuviera bien (caché de un día sin versión): ahora
  lleva `?v=<fecha de la foto>`, como la ficha.
- `b7fc27f`: el origen se nombra por su tipo ("Sacada de su DNI
  (ver)"), nunca por el nombre de archivo (criterio de Miguel Ángel
  para el panel).

### 3. "Descargar documentación" en las fichas de persona y máquina -- `41036ef`, `aee312f`, `b7fc27f`

Miguel Ángel: un botón para abrir la documentación separada por
familia, con los obsoletos marcados y filtros, para sacar documentos
de la ficha fácilmente.

- `DocumentDownloadPickerView` (`documentacion/personal|maquinaria/
  <pk>/descargar/`): todos los documentos vivos agrupados por familia
  y marcados vigente, caducado u obsoleto con el mismo cálculo que la
  ficha (`_split_current_obsolete` con el requisito del sujeto).
- La ventana sigue el formato único de listado (4.24): buscar y
  filtrar (familia, estados, solo la selección), orden múltiple por
  cabecera dentro de cada familia, visor "Selección actual", menú de
  tres puntos, pantalla completa de la lista, descarga en ZIP o PDF
  único. Las casillas son la "Selección de documentos" de la ficha, y
  los filtros y el orden se guardan por usuario (4.15). Sin nombres de
  archivo.
- `aee312f`: **papelera** desde la ventana (la selección o una fila),
  con un segundo clic de confirmación; borrado blando
  (`DocumentDownloadTrashView`, 4.12). Miguel Ángel lo pidió para
  quitar fotos repetidas y el mismo permiso obsoleto varias veces.
- `b7fc27f`: rehecha tras preguntar Miguel Ángel si seguía el formato
  (la primera versión no tenía orden por cabecera, visor ni menú, y
  enseñaba el nombre del archivo).
- Probado en navegador (Playwright) con datos de ejemplo.

### 4. Fichajes y Repostajes con el formato completo, y columnas en el móvil -- `5baebed`, `7842d4b`, `a0b5f30`, `916a7d7`, `39131d0`, `d229cfd`, `0add9bb`

- Fichajes (H24): filtro **"Con fichajes / Sin fichajes"** (también al
  exportar); Entrada, Salida y Municipio también ordenables;
  pantalla completa, menú de tres puntos ("Ver las jornadas", "Abrir
  la ficha") y lista 3/4 + selección 1/4 (`7842d4b`).
- **Error mío, corregido:** para ordenar en el móvil le puse una barra
  "Ordenar por" (`5baebed`), que no es el formato. Miguel Ángel lo
  señaló y se retiró (`a0b5f30`): la tabla mantiene columnas y
  cabecera ordenables en el móvil.
- Repostajes (H30, tocado a petición expresa de Miguel Ángel con S135
  ya cerrada): en el móvil no se podía "Seleccionar todos" porque las
  tarjetas ocultaban la cabecera (`916a7d7`); y el panel de acciones
  iba apilado con párrafos de explicación (364 px de alto): ahora en
  cuadrícula por categorías con las explicaciones en el título de cada
  botón (227 px), igual en Fichajes (`39131d0`).
- Decisión de Miguel Ángel, con las dos opciones delante: **todas las
  listas de gestión con columnas también en el móvil**. Se quitan las
  tarjetas (`stack-mobile`) de Personal, EPIs, Vacaciones (y su tabla
  de Reglas), Accesorios de elevación y Revisiones (`d229cfd`). Por
  debajo de 992 px sigue sin haber columnas fijas (S123, por decisión
  suya). Siguen con tarjetas las tablas que no son listados de gestión
  (fichas, chat de averías).
- Directriz 4.24 ampliada (`0add9bb`): punto 11 (columnas también en el
  móvil) y punto 12 (acciones en cuadrícula, explicaciones en el
  título).
- Comprobado a 390 px en Fichajes y Repostajes (cabecera visible,
  "Seleccionar todos" marca todas las filas). Las otras cinco listas
  pasan el lint y Django las procesa, pero no se han visto en un móvil.

### 5. Otros

- El mapa del fichaje (detalle del trabajador) funciona en el móvil:
  probado a 390 px; no se había tocado.
- Grupo de WhatsApp para Asistencia: decisiones registradas en
  `ENTERPRISEBOT_ATTACHED_MILESTONE_V37.md`, sección 10.
- flake8 y djlint a 0 en todos los archivos tocados; los 11 estilos en
  línea de `_personal_pane.html` pasan a clases (4.9).
- La release `relevo-imagenes` queda con 0 adjuntos.

---

## COMPLETADAS EN S146 (desvío desde H24, 06/11 → 09/11/2026, PEE PC; alta y baja de Personal)

Hecho en la sesión principal de H24 (ver anexo V24, 7.16) mientras se
probaba la carpeta local con ARANDA REYES, ANTONIO. Lo que toca a la
pestaña Personal:

1. **El alta no espera a la carpeta local** (`c0be9a4`). Miguel Ángel:
   *"Esto es una operación que deberíamos hacer en segundo plano"*. El
   alta dice "Ficha creada. La carpeta local se actualiza en segundo
   plano…" y vuelve al listado; el agente H28 hace el trabajo después.
2. **Empresa y Sección de desplegable en el alta** (`b242f2d`). Miguel
   Ángel: *"dejar ese campo para que se escriba es un error. Hay que
   preguntar a qué empresa va y sacar el desplegable"*. Las dos son
   obligatorias; la empresa sale preseleccionada con lo que lee Gemini
   del documento; la sección se asigna con la fecha de alta (también al
   reactivar a un inactivo) antes de crear el trabajo local, porque
   decide la categoría local (el taller de Málaga va aparte).
3. **Código de empresa en la carpeta local** (`b242f2d`, `bfe88ab`):
   TR, GR, GL, AGG; si cambia la empresa, cambia el código (las
   variantes como "(PTE TR)" se respetan).
4. **El alta de un inactivo mueve su carpeta local aunque la movieran a
   mano** (`f469f59`): el agente la busca por nombre en todas las
   categorías.
5. **Grupos:** marcar un subgrupo no marca el padre; el padre queda a
   medias (`8692e7d`).

Prueba real: bajas y altas sucesivas de Aranda, todas bien; Aranda
vuelve a su estado anterior con `restore_aranda_s146`.

## REACTIVADO AL CIERRE DE S146 -- Hoja de Ruta S148 (va antes que la "Hoja de Ruta pendiente al reactivar H31", que sigue intacta)

PCH desde H24 al cierre de S146 (09/11/2026; S147 es la invasora de
fichajes). Miguel Ángel, verbatim: *"la siguiente sesión nos vamos a
dedicar a la UX de personal [...] no quiero que salgan [...] scrolls
verticales, como el volumen cada vez es más grande, están saliendo en
la pestaña de personal"*.

1. **Personal sin scroll vertical en el panel de filtros.**
   - Empresa pasa a ser un **desplegable con casillas** (Miguel Ángel:
     *"que sea un desplegable pero con casillero"*): al abrirlo se
     marcan una, varias o todas; cerrado, ocupa una línea y dice qué
     hay marcado. Hoy son cinco casillas sueltas (Grúas Adolfo Álvarez,
     Transgrual, Grualdi, Asistencia y Grúas Granada, Sin empresa
     asignada) más "(todas)", junto a Estado (Activos / Inactivos).
   - Revisar el resto de bloques de filtros y acciones de Personal con
     el mismo criterio: lo que crece con el volumen va a desplegable
     con casillas.
   - **Cierre:** con la ventana normal del PC de Miguel Ángel, la
     pestaña Personal no tiene scroll vertical en filtros ni acciones,
     y filtrar por una o varias empresas da el mismo listado que
     antes.
2. **Alta por formulario, sin documentación.** Hoy el alta se hace
   solo a partir de documentos. Al pulsar "Dar de alta", poder elegir
   el formulario y dar de alta a alguien aunque no tenga ningún
   documento (*"aunque no tenga documentación"*): mismos campos y
   reglas que el alta por documentos (empresa y sección de desplegable,
   fecha de alta, reactivación si ya existe, carpeta local en segundo
   plano).
   - **Cierre:** una persona real dada de alta por formulario sin
     documentos queda en BD activa, con empresa, sección y fecha de
     alta, y el agente le crea su carpeta local.
3. **Maquinaria igual que Personal.** Miguel Ángel: *"vamos a
   dedicarnos a la maquinaria para que quede con usos y las vistas
   queden también igual que las de personal, y creemos los grupos de
   selección correspondientes de forma general, tal y como hemos hecho
   con personal"*. Las vistas de Maquinaria con el mismo formato que
   Personal y grupos de selección generales de máquinas.
   - **Cierre:** Maquinaria con el mismo panel de filtros, acciones y
     grupos de selección que Personal, usado en producción con grupos
     reales creados.
4. Cualquier otra cosa de UX que surja en la sesión.

---

## COMPLETADAS EN S148 (10-11/11/2026, PEE PC; en paralelo con la invasora S149 de nóminas y fichajes)

Hoja de Ruta S148 cerrada en sus tres puntos y, a petición de Miguel
Ángel, una larga serie de mejoras de UX y de extracción de datos.

### 1. Personal sin scroll vertical -- `be2bb4e`, `60cc3e6`, `0db1589`, `a323dd1`, `7bfbab0`
- Empresa como desplegable con casillas en Personal, Fichajes, Horarios
  y Vacaciones; Estado, Fichajes y atajos de fechas en desplegables;
  pestaña EPIs con el formato único (4.24); "Horario y sección" en
  pestaña propia de las acciones.
- La columna "Grupos de selección" (Personal y el recuadro común de las
  demás vistas) ya no estira el panel fijo: toma el alto de las otras
  columnas (mínimo 15rem) y su árbol hace scroll dentro (`.eb-fit-col`).

### 2. Alta por formulario sin documentos -- `6b31f0a`, `cb1ec90`, `f296653`, `d82ae6b`, `5946866`
- "Dar de alta" permite el formulario sin documentos con las mismas
  reglas que el alta por documentos (empresa y sección de desplegable,
  fecha de alta, reactivación, carpeta local en segundo plano).
- `person_facts_service.py`: la ficha se actualiza con cada documento
  subido (caducidades, datos del contrato, C.P.); comando
  `fill_person_fields_from_documents` (--apply, --category).
- C.P. por dirección con el geocoder oficial de CartoCiudad (el C.P. del
  contrato era el de la empresa: revertido, `1dd3860`/`35dad56`).
- Categoría profesional leída del contrato (64 de 78 activos con ella).

### 3. Maquinaria igual que Personal -- `74f02b1`, `8c2afba`, `e041d9b`, `1793ce7`, `613b18b`, `09cd72f`, `25c6381`, `fd50997`, `c8022be`, `71b76a5`, `e5b50dc`
- Centros de gasto con el formato de Personal (acciones en pestañas,
  Estado con casillas) y grupos de selección de máquinas iguales que
  los de personas; carpeta local (OneDrive) de las máquinas, con lo
  sustituido a OBSOLETOS.
- Alta de centro de gasto por documentos o sin ellos
  (`views_machine_intake.py`), reactivando la máquina si ya existía.
- `fill_machine_fields_from_documents` (--apply, --only-purchase):
  148 datos rellenados y 13 fechas de compra; se descartan documentos de
  tipo dudoso o de otra matrícula (G15 tenía el recibo de G09).
- Observaciones (campo Memo) en máquinas y personas (migraciones fleet
  0035 y document_explorer 0212); avisos propios de cada centro de gasto
  desde su ficha (`MachineAlertRule`, 0213); horario y modo de fichaje
  en la ficha de personal.
- Recibo de seguro de G09 (entrada 15802) colocado en BD, cubo y local.

### 4. Exportaciones: imprimir, PDF y plantillas -- `9a42df2`, `1becee8`, `0d41ce3`, `3b010ec`, `5e3e98c`, `7b35312`
- `panel/export_formats.py`: toda exportación a Excel sale también en
  PDF (A4 apaisado, WeasyPrint) o para imprimir (pestaña nueva).
- Plantillas: "Vista del panel" fija y por defecto (`export_templates.py`)
  en Personal y Repostajes; plantillas comunes
  (`panel.ScreenExportTemplate`, migración panel 0003,
  `screen_exports.py`, `screen_export_catalog.py`, modal
  `_screen_export_modal.html`) en Centros de gasto (la hoja MAQUINARIA
  de Yolanda queda como plantilla global), Taller (tareas y averías) y
  Fichajes (hoja Jornadas; por decisión de Miguel Ángel su "Vista del
  panel" es el Excel completo de antes). Partes revisados no tiene
  plantillas (junta los Excel de cada parte).

### 5. Grupos, dosieres, pedir documentos, fichajes y roles -- `f7a8a05`, `0692cfa`, `c46e16d`, `aa23074`, `80ee23e`, `62f4c2b`, `21052cf`, `112e560`
- Papelera en cada grupo de selección propio sin subgrupos; los
  administradores (rol ADMIN) borran cualquiera salvo los Generales.
- Dosier: de cada tipo acumulable solo el documento más reciente
  (fecha de emisión, si no la del nombre, si no la de subida); los del
  mismo día van todos. Con Paraschiv Caraion pasó de 21 documentos a
  los vigentes.
- Pestaña "Pedir documentos" (`views_doc_requests.py`): cualquier tipo
  de Personal por WhatsApp a los marcados, con los filtros y grupos de
  siempre (`create_requests(any_type=True)`); enlace desde Avisos.
- Fichajes: los desplegables del panel de arriba ya no se cortan; tipo
  de fichaje propio de un trabajador por encima de su sección
  (`WorkerClockSetting.clock_mode`, migración hr_calendar 0036) y
  horario propio desde el mismo panel.
- Rol nuevo Comercial (`SALES`, migración ivr_config 0057), sin
  permisos propios todavía.
- Desplegables del hub al vuelo (`views_live_options.py`): circulares,
  Docuten, obras, plantillas de dosier y lotes de EPIs aparecen sin
  recargar al cambiar de pestaña o volver a la ventana.

### Incidencias
- Recarga de la web por API con tiempo agotado varias veces: se relanza
  `deploy.yml` (workflow_dispatch) y termina bien.
- La release privada `relevo-imagenes` tiene 135 adjuntos (páginas de
  documentos de personas) y la sesión no puede borrarlos (HTTP 403,
  tipo de sesión): los borra Miguel Ángel a mano (ver Hoja de Ruta).
- Impresora Brother HL-L2400DWE del taller: conectada a WIFIALVAREZ
  (192.168.3.226); ya imprime.

---

## COMPLETADAS EN S150 (11-12/11/2026, PEE PC; en paralelo con la invasora S151 de FACTURACIÓN y con trabajo de fichajes)

### 1. Tarea programada de ITV -- `1fc3e73`, `70c7bcf`, `b8fc2e9`, `197476c`, `9519768`, `70ed59f`, `9abc229`
- `itv_documentation_report` (document_explorer) + `itv_report.yml`:
  informe JSON de solo lectura (máquinas ACTIVAS con carpeta local y
  ITV vencida o a 30 días; fecha de ITV = máx. de `itv_date` y del
  documento de ITV vigente; MD5 de cada documento en GCS), subido a la
  carpeta de intercambio de Drive.
- `tools/itv_local_check.py`: mitad local en el PC (busca cada documento
  por ruta, por nombre + MD5 y por MD5 + matrícula); escribe la tabla
  Markdown y, al final, la sección "ITV vencida sin la ITV nueva ni en
  el panel ni en local". Con la ITV vencida, la columna Local ya no dice
  "al día" (caso R22: decía al día porque en local estaba el mismo
  documento caducado que en el panel).
- Tarea programada `trig_01Vij2L5sD13BiXuCdp29cbg` ("EnterpriseBot —
  Control de ITV a 30 días"), lunes 7:47 Europe/Madrid, requiere el PC
  (carpeta DOC. MAQUINAS), aprobación automática, aviso al móvil. Deja
  el informe en un documento de Claude Docs ("Informe de ITV —
  DD/MM/AAAA") y envía un correo desde el Outlook de escritorio del PC
  (uso del ordenador) a Alejandro Álvarez <alejandro@gruasalvarez.com>
  con la lista de ITV vencidas sin ITV nueva, indicando que lo ha hecho
  el agente de Claude. Primera ejecución con correo: 11/11/2026.
- Cinco ITV mal fechadas corregidas (A59 42115, P27 43282, B34 43287,
  G02 53045, Z103 53199) y causa raíz arreglada en
  `date_machine_documents_free` (en ITV/OCA la fecha completa del nombre
  manda). `recalculate_machine_vigencia` admite `--machines` y `--types`.
- Informe real del 11/11: 52 máquinas activas con la ITV vencida; con
  ITV nueva en local solo Z17 (04-03-2027) y P16 (18-02-2027, en una
  subcarpeta). Revisados a mano B39 (el script marcó por fecha de
  modificación una ITV de 2024), 6951HZS (un `.log` de 116 bytes) y R22
  (renombrada hoy en local a `ITV 19-11-26`: la fecha del panel,
  10/11/2026, puede estar mal).

### 2. Estado Activo/Inactivo de la flota -- `3ee7168`
- `reconcile_machine_activity` (fleet): cruza repostajes de GasoGes
  (desde enero de 2026, ventana de 180 días) con pruebas de baja
  (BAJA_DEFINITIVA/BAJA_TEMPORAL/FACTURA_VENTA o carpeta local de
  baja/venta). Criterio de Miguel Ángel: activa = reposta; sin
  repostajes y con baja documentada = inactiva.
- Hojas para comprobar en campo: "Activas a inactivar" (39) e "Inactivas
  a activar" (16). Miguel Ángel aplicó los cambios; desactivó además X10
  y 7308BWM. A29 sigue activa. Las plataformas sin repostajes quedan a
  su comprobación en campo.

### 3. Agente H28: mover carpetas de máquina -- `e005ce3`
- Al cambiar una máquina de estado, el agente creaba una carpeta vacía
  con el nombre del servidor si en local la carpeta tenía otro nombre
  ("(GR)", "(TR)", "(VENDIDA)") y no movía la de verdad.
- Corregido: busca por el nombre hasta el primer paréntesis, conserva el
  nombre local, ignora y borra carpetas vacías, y no crea una vacía si
  no encuentra la carpeta. Recompilado y arrancado en el PC.
- Borradas 9 carpetas vacías sobrantes; reprocesados los trabajos 24,
  25, 26 y 37: R-12, 2030JVK, 3968HWN y 7308BWM ya están en sus
  carpetas de baja con todos sus archivos.
- Nota: el agente no atiende trabajos hasta terminar la reconciliación
  de arranque (unos 15 minutos con DOC. PERSONAL).

### 4. Relevo -- `86578f6`
- `file_fetch.yml` admite `delivery=release` (modo pythonanywhere): el
  archivo llega comprimido a la release privada `relevo-imagenes`.

### 5. Puntos 2-4 de la Hoja de Ruta S150
- Release `relevo-imagenes`: vaciada (S149/S150); vaciarla es tarea del
  modelo al cierre, con `relevo_cleanup.yml`.
- Pruebas de S148: Miguel Ángel las da por cerradas; todas las pruebas
  se hacen en producción.
- Paraschiv PRL 18-19 duplicada y facturas de notario de B49/A70 a
  LEASING: hecho.

## Hoja de Ruta S152 (va antes que la "Hoja de Ruta pendiente al reactivar H31", que sigue intacta)

Encargo de Alejandro Álvarez (11/11/2026, verbatim): *"en el mes de
diciembre vence la mayoría de los seguros y Necesito que os pongáis a
sacarme un listado de todos los seguros con la información necesaria
para su renovación de precio y demas con los mediadores de seguros.
Llamarme por favor por la mañana y nos conectamos para iniciar esto."*
Miguel Ángel llama a Alejandro por la mañana; lo que concrete Alejandro
en esa llamada se suma a este punto al arrancar la sesión.

1. **Listado de seguros para la renovación.** Situación en BD al
   12/11/2026 (documentos no obsoletos): `SEGURO` (recibo) 315, 50 con
   caducidad en diciembre de 2026; `POLIZA_SEGURO` 247, 7 en diciembre;
   `CERTIFICADO_SEGURO` 37, 2 en diciembre; `CARTA_VERDE` 27;
   `POLIZA_SEGURO_EMPRESA` 1; `CONDICIONES_GENERALES_SEGURO` 1. En local,
   carpeta `DOC. MAQUINAS/SEGUROS` y el OneDrive `GRUALDI SL` (conectado
   al PC el 12/11).
   - Sacar, por cada centro de gasto activo y por cada seguro de empresa:
     centro de gasto, matrícula, aseguradora, mediador, número de póliza,
     tipo de cobertura, prima del último recibo, fecha de vencimiento y
     documento de origen (panel o local). Los datos que no estén en
     campos de BD se leen del documento (texto OCR del panel).
   - Entregarlo como Sheet (tipo Sheets), ordenado por vencimiento, con
     los de diciembre de 2026 primero.
   - **Cierre:** el Sheet tiene una fila por cada póliza vigente de
     centro de gasto activo y de empresa; los 50 recibos con caducidad en
     diciembre están en él; cada fila tiene aseguradora, número de póliza,
     vencimiento y prima, o la marca "no consta en el documento".
2. **Script local de ITV**: en `tools/itv_local_check.py`, decidir qué
   ITV es "más nueva" por la fecha del nombre del archivo, no por la de
   modificación; buscar en toda la carpeta de la máquina (subcarpetas
   incluidas, menos OBSOLETOS); descartar archivos que no sean PDF ni
   imagen. **Cierre:** con el JSON del 11/11, P16 y Z17 salen con ITV
   nueva en local, y B39 y 6951HZS no.
3. **R22**: comprobar en el PDF `R-22 MU08876R ITV 19-11-26.pdf` (cubo)
   la fecha real de caducidad y corregir `expiry_date` en el panel si es
   el 19/11/2026. **Cierre:** consulta a BD con la entrada 16616 y la
   fecha que dice el documento.
