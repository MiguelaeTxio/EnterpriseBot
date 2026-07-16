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

1. Resolver las 5 preguntas abiertas de la sección 4 con Miguel Ángel.
2. Decidir la ubicación del servicio compartido (app nueva vs. app
   existente).
3. Construir, en este orden sugerido (a confirmar con Miguel Ángel, no
   asumido): diálogo de sustitución (bloquea cualquier subida nueva
   coherente) → fusión/generación de PDF → plantilla de email → motor
   de alertas (depende de que la plantilla WhatsApp de H23 esté
   aprobada por Meta, todavía `pending` a fecha de S022).
4. Solo después: construir las interfaces de Administración de H23 y
   H25 sobre este servicio.

---

## 6. Registro de Sesiones

| Sesión | Fecha | Trabajo realizado |
|---|---|---|
| S022 | 2026-07-16 | Hito creado durante la planificación de la continuación de H23: Miguel Ángel identificó la necesidad de una aplicación de gestión documental completa (no solo el pipeline de ingesta actual) y, tras plantearle las opciones, eligió construir la infraestructura pesada compartida (alertas, PDF, email, sustitución) como hito propio antes que las interfaces de H23/H25, para evitar duplicar lógica entre dominios. Especificación completa de las 4 capacidades capturada tal cual (sección 2). Sin código todavía — hito registrado como PAUSADO. Ver sección 4 (preguntas abiertas) y sección 5 (hoja de ruta) para el punto de partida de la siguiente sesión. |
