# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V26.md

# Anexo de Hito V26 — Infraestructura Documental Compartida
# Proyecto: EnterpriseBot
# Fecha de inicio: 2026-07-16 (S022)

---

## 1. Visión General del Hito

Origen: al plantear la continuación de H23 (interfaz de Administración
para documentación de centros de gasto), Miguel Ángel señaló que lo que
existe hoy en `machine_documents` es un **pipeline de ingesta y
clasificación** (subir → Gemini clasifica → GCS → listado de solo
lectura embebido en el historial de máquina), no una **aplicación de
gestión documental** completa. Palabras de Miguel Ángel: "tenemos que
crear una aplicación completa para gestionar la documentación... con su
interfaz, siguiendo el mismo estilo de la plataforma, ubicada dentro del
panel, tanto para la documentación de la maquinaria como la
documentación de personal" — corregido por él mismo a continuación:
**dos aplicaciones de dominio** (centros de gasto = H23/`machine_documents`,
personal = H25), no una sola.

Dentro de esa idea, Miguel Ángel enumeró un conjunto de capacidades
pesadas (alertas, subida, borrado, sustitución, plantillas de correo,
fusión/generación de PDF) y preguntó si construirlas dentro de cada
dominio o como pieza aparte. Se le plantearon dos opciones (A: todo
dentro de cada hito de datos: B: hito dedicado a la infraestructura
compartida antes de construir cualquiera de las dos interfaces) y
**Miguel Ángel eligió la Opción B explícitamente**: "me inclino por la
B, porque evitamos [duplicar] en el de centro de gasto la lógica de
todo. Así la hacemos de forma general para ambas."

**Motivo de fondo (Claude, aceptado por Miguel Ángel):** ninguna de las
capacidades pesadas (fusión de PDF, generación de plantilla de correo,
motor de alertas, diálogo de sustitución) es específica de centros de
gasto ni de personal — construirlas dos veces rompería DRY, con el
mismo patrón de duplicación que ya causó el incidente de la taxonomía
de averías repetida en cuatro archivos (corregido en S017).

**Este hito NO construye ninguna interfaz de usuario todavía.** Es
infraestructura compartida (mismo patrón que `ai_services`/
`spare_parts/gcs_service.py`) que H23 y H25 consumirán cada uno desde su
propia interfaz de Administración, construida en su propio hito, después
de este.

---

## 2. Alcance — Capacidades a Construir (tal cual las dio Miguel Ángel, directriz 4.8)

### 2.1. Motor de alertas de vencimiento de documentos

Ya anticipado en H23 (anexo V23, "Decisiones cerradas en S021", punto
3): plantilla WhatsApp `document_expiry_alert` ya creada y en revisión
de Meta (`HX55da66276bb2025f691c378abff0123e`, estado `pending`
confirmado en S022 vía API de Twilio). Este hito construye el motor que
detecta documentos próximos a caducar (según la lógica de vigencia ya
diseñada en H23) y dispara el envío usando esa plantilla — la propia
tarea Celery periódica, no solo la plantilla.

### 2.2. Fusión/generación de PDF bajo demanda

Palabras de Miguel Ángel: "la documentación normalmente se aglutina en
un solo PDF para enviarla por correo." Acción bajo demanda (el usuario
pulsa "generar dossier"), **no automática ni disparada por ningún
evento** — confirmado explícitamente por Miguel Ángel en S022 al
preguntársele. Genera un único PDF combinando los documentos
seleccionados (de una máquina, o de un trabajador), pensado para
adjuntarlo a un correo.

### 2.3. Plantilla de correo — texto para copiar y pegar, NUNCA envío automático

Aclaración explícita de Miguel Ángel en S022, tras pregunta directa:
"simplemente generar una plantilla con el tipo de mail que se va a
enviar para copiar y pegar. Como, por ejemplo, 'adjunto remito la
documentación necesaria para que surta efecto y conste donde sea
pertinente' [...] y se genere el archivo, el dossier, para adjuntarlo."

**Fuera de alcance de este hito, explícitamente: cualquier integración
SMTP/API de envío de correo.** La plataforma solo genera el texto
(asunto + cuerpo) para que el usuario lo copie a su propio cliente de
correo, junto con el PDF del punto 2.2 para que lo adjunte él mismo.

### 2.4. Diálogo de sustitución de documentos

Aclaración explícita de Miguel Ángel en S022: "al subir un documento, si
ya tenemos un documento subido de las mismas características, hay que
comprobar fecha y avisar: 'este documento es anterior y ya no está
vigente', o 'este documento es vigente y debe prevalecer sobre lo que
tenemos'. Un cuadro de diálogo en el que se decida qué hacer con la
documentación, con facilidad para archivar el documento obsoleto y
dejar como vigente el entrante, o revertir la subida y anularla."

Flujo tal cual lo describió, a implementar sin reinterpretar (directriz
4.8):
1. El usuario sube un documento nuevo de un tipo para el que ya existe
   al menos un documento del mismo tipo (misma máquina, o mismo
   trabajador, según el dominio).
2. El sistema compara fechas entre el documento entrante y el/los
   existente(s) del mismo tipo (misma lógica de vigencia ya diseñada en
   H23, sección "Decisiones cerradas en S021", punto 1).
3. Se muestra un cuadro de diálogo con el resultado de esa comparación
   (cuál es más reciente) y dos acciones:
   - **Archivar el obsoleto, dejar el entrante como vigente** (caso
     normal: el nuevo documento es más reciente).
   - **Revertir la subida y anular el documento entrante** (caso: el
     nuevo documento resulta ser más antiguo que el vigente actual, o
     el usuario decide que no procede el cambio).
4. Nunca se sustituye ni se archiva nada automáticamente sin pasar por
   este diálogo — la decisión final es siempre del usuario.

---

## 3. Relación con H23 y H25

- **No bloquea la hoja de ruta ya construida de H23** (migración GCS,
  ya completada en S022). Sí bloquea/reordena los puntos pendientes de
  interfaz de Administración de H23 (vigencia visible, archivado,
  modal de alerta) — se construyen sobre este servicio, no antes.
- **H25 sigue igual de bloqueado** que ya estaba (pendiente de resolver
  sus 7 preguntas abiertas, ver anexo V25) — este hito no cambia ese
  bloqueo, solo asegura que cuando se construya su interfaz, reutilice
  este servicio en vez de duplicar lógica.
- **Confirmación de Miguel Ángel tras el cierre de S022** (ver anexo
  V25 sección "3.bis"): "las operaciones que vamos a realizar son
  prácticamente las mismas [entre H23 y H25], por no decir las
  mismas" — lo que cambia entre ambos dominios es volumen y variedad
  de tipos de documento, no la lógica de alertas/subida/archivado/CRUD
  que construye este hito. Refuerza la Opción B como acertada. Único
  matiz real a tener en cuenta al construir el diálogo de sustitución
  (sección 2.4): en personal no todos los tipos de documento
  participan en una relación de "sustitución" (ej. cursos de
  formación distintos no se sustituyen entre sí) — el diseño debe
  permitir marcar, por tipo de documento, si participa o no en ese
  diálogo, en vez de asumir que todo documento nuevo del mismo tipo
  sustituye al anterior.

---

## 4. Preguntas Abiertas — Resolver al Retomar Este Hito

1. **App/módulo destino** del servicio compartido — ¿nueva app Django
   dedicada (ej. `document_management`), o vive dentro de `ai_services`
   (ya transversal) o `spare_parts` (ya alberga `gcs_service.py`)? No
   decidido todavía, a confirmar con Miguel Ángel al empezar.
2. **Motor de fusión de PDF** — librería a usar (el proyecto ya tiene
   `PyMuPDF`/`pdf2image` instalados; verificar online, directriz 4.4,
   si son suficientes para fusión o hace falta una dependencia nueva
   vía `pip-tools`).
3. **Contenido exacto de la plantilla de email** — Miguel Ángel dio un
   ejemplo de frase ("adjunto remito la documentación necesaria para
   que surta efecto y conste donde sea pertinente"), pero no una
   plantilla completa ni si varía por tipo de documento/situación —
   confirmar con él antes de dar la plantilla por definitiva.
4. **Motor de alertas — periodicidad y canal de disparo** — ¿tarea
   Celery periódica (Celery Beat, no usado todavía en el proyecto,
   verificar online antes de introducirlo) revisando vigencias a diario
   / semanalmente? Confirmar frecuencia con Miguel Ángel.
5. **Diálogo de sustitución — mismo tipo, ¿en qué ámbito?** Para
   centros de gasto, "mismo tipo" implica misma máquina + mismo
   `document_type`. Para personal (H25, sin modelo definitivo todavía)
   habrá que confirmar el equivalente cuando se cierre el diseño de
   H25.

---

## 5. Hoja de Ruta para la Sesión Siguiente que Retome Este Hito

**Las 4 capacidades base están construidas y desplegadas (S023) --
ver "COMPLETADAS EN S023" abajo para el detalle completo.** Este hito
no tiene trabajo propio pendiente ahora mismo -- lo que queda es que
H23 (siguiente sesión, S024) y más adelante H25 construyan sus
interfaces de panel consumiendo estos servicios:

- `document_management.vigencia_service` -- `is_current()`,
  `evaluate_substitution()`.
- `document_management.pdf_merge_service` -- `merge_pdfs()`.
- `document_management.tasks.send_document_expiry_alerts` -- ya
  desplegada en Celery Beat (3:00), pendiente de que exista alguna fila
  real de `DocumentAlert` para tener algo que enviar (las crea la
  futura interfaz de H23) y de que Meta apruebe la plantilla WhatsApp
  `document_expiry_alert` (~24h desde S021, debería estar resuelta
  para S024).
- `EmailTemplate` -- modelo listo, sin interfaz de edición todavía
  (decisión explícita de Miguel Ángel, S023: nunca construir una
  pantalla mínima desechable -- se construye cuando haga falta de
  verdad, o no se construye).

Si en el futuro una sesión vuelve a este hito porque H25 necesita algo
que hoy no está cubierto (p. ej. el ámbito del diálogo de sustitución
para personal, con tipos de documento que no participan en
sustitución -- ver sección 3), tratarlo como incidencia puntual sobre
este servicio, no como una reapertura completa del hito.

### COMPLETADAS EN S023

Sesión con H23 EN PROGRESO (nunca se movió el marcador -- desvío Caso
A desde H23, ver `ENTERPRISEBOT_ANNEX_ROUTER.md` y el propio anexo H23
"COMPLETADAS EN S023" para el incidente real que motivó parte de la
sesión). Miguel Ángel delegó explícitamente en el modelo la decisión
de por dónde continuar tras cerrar el incidente ("lo que consideres
mejor"), y se siguió la recomendación ya anotada en el anexo H23: abrir
H26 antes que H25.

**Las 5 preguntas abiertas de la sección 4, resueltas con Miguel
Ángel:**
1. App nueva transversal dedicada: `document_management` (nunca
   plegada en `ai_services` ni `spare_parts`).
2. Motor de fusión de PDF: `PyMuPDF` (`pymupdf==1.27.2.2`, ya
   instalado) es suficiente -- `Document.insert_pdf()` -- verificado
   online (directriz 4.4), sin dependencia nueva.
3. Plantilla de email: "cualquier cosa genérica y modificable desde la
   misma aplicación, luego que lo rellene la persona encargada de
   documentación" -- **nunca dijo "admin"**; el modelo lo interpretó
   mal una vez (Django admin, al que solo Miguel Ángel tiene acceso),
   corregido explícitamente por él antes de desplegar. Decisión final:
   modelo `EmailTemplate` sin ninguna interfaz de edición por ahora --
   "no vamos a hacer una interfaz pequeña para luego borrarla y poner
   la definitiva. No."
4. Motor de alertas -- periodicidad y disparo: `Celery Beat` **ya
   estaba en uso en producción** (`CELERY_BEAT_SCHEDULE` en
   `settings.py`, 3 tareas reales del canal WhatsApp + 1 de limpieza
   de chat) -- la nota de la sección 4 sobre "no usado todavía" estaba
   desactualizada, corregido al verificar el código real en vez de
   fiarse del anexo. Horario elegido: 3:00 -- reutilizando el hueco
   que dejó libre la tarea muerta `purge_old_chat_messages`
   (eliminada en H17, seguía programada; ver anexo H17), sugerencia
   del propio Miguel Ángel.
5. Diálogo de sustitución -- ámbito: confirmado, solo centros de gasto
   (H23/`MachineDocument`) por ahora; personal (H25) queda pendiente
   hasta cerrar su modelo de datos.

**Construido, verificado y desplegado (commits `29c333d`, `a28f6fb`,
`09fa8aa`, `bebb691`, `5e64a9f`):**
- App `document_management` (`INSTALLED_APPS`), modelos
  `EmailTemplate` y `DocumentAlert` (migración `0001_initial`).
  `DocumentAlert` vinculado genéricamente (Content Type framework) a
  cualquier documento de cualquier dominio -- nunca importa
  `MachineDocument` ni el futuro modelo de H25. Campos según
  especificación literal de Miguel Ángel: documento, fecha de
  caducidad, días de antelación, contacto(s) (M2M a `CompanyUser`),
  resolución.
- `document_label`/`subject_label` añadidos a `DocumentAlert`
  (migración `0002`) tras aclarar con Miguel Ángel que estos campos
  los rellena automáticamente la vista que crea la alerta (máquina y
  documento ya conocidos por contexto), nunca la persona a mano --
  evita que este módulo tenga que inspeccionar el objeto genérico.
- `vigencia_service.py`: `is_current()`/`evaluate_substitution()`,
  implementando el criterio de vigencia de H23 S021 con la lectura
  confirmada por Miguel Ángel (documentos con `expiry_date`: vigentes
  hasta que caduquen, sin compararse entre sí -- permite varios
  vigentes a la vez por periodo, ej. seguros trimestrales; documentos
  sin `expiry_date`: el más reciente `issue_date` de su tipo es el
  vigente). Verificado con 4 casos de prueba reales antes del commit.
- `pdf_merge_service.py`: `merge_pdfs()` con `PyMuPDF`. Verificado
  empíricamente generando PDFs reales y comprobando páginas/orden.
- `tasks.py`: `send_document_expiry_alerts`, reutilizando el patrón
  real ya en producción de `whatsapp.tasks.check_in_meeting_reminders`
  (mismo decorador `@shared_task(name=...)`, mismo mecanismo Twilio
  Content API/`content_variables`) -- verificado contra el código real
  antes de escribir, incluida una falsa alarma resuelta comparando el
  método de comprobación contra una tarea ya conocida en producción
  (`app.tasks` requiere `autodiscover_tasks(force=True)` para
  poblarse en un shell normal).
- Verificación de despliegue con datos reales (no solo semáforo verde,
  incluidas migraciones): `git log -1` + `showmigrations` +
  comprobación de registro de tarea Celery en el servidor real tras
  cada push relevante.

---

## 6. Registro de Sesiones

| Sesión | Fecha | Trabajo realizado |
|---|---|---|
| S022 | 2026-07-16 | Hito creado durante la planificación de la continuación de H23: Miguel Ángel identificó la necesidad de una aplicación de gestión documental completa (no solo el pipeline de ingesta actual) y, tras plantearle las opciones, eligió construir la infraestructura pesada compartida (alertas, PDF, email, sustitución) como hito propio antes que las interfaces de H23/H25, para evitar duplicar lógica entre dominios. Especificación completa de las 4 capacidades capturada tal cual (sección 2). Sin código todavía — hito registrado como PAUSADO. Ver sección 4 (preguntas abiertas) y sección 5 (hoja de ruta) para el punto de partida de la siguiente sesión. |
| S023 | 2026-07-16 | Desvío Caso A desde H23 (marcador nunca movido a este hito). Las 5 preguntas abiertas de sección 4 resueltas con Miguel Ángel (app nueva `document_management`, PyMuPDF suficiente para fusión, plantilla de email sin UI por decisión explícita, Celery Beat ya en uso — corrección de una nota desactualizada del propio anexo, sustitución solo centros de gasto por ahora). Las 4 capacidades construidas y desplegadas: modelos `EmailTemplate`/`DocumentAlert` (migraciones `0001`/`0002`), `vigencia_service.py` (verificado con 4 casos de prueba), `pdf_merge_service.py` (verificado con PDFs reales), `send_document_expiry_alerts` (verificado registrado en Celery del servidor real). Un error de rumbo propio corregido por Miguel Ángel en el momento (Django admin para `EmailTemplate`, nunca pedido). Ver "COMPLETADAS EN S023" arriba para el detalle técnico completo. |
