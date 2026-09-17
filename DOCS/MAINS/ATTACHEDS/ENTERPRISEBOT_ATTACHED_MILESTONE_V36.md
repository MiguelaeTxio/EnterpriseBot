# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V36.md
# Anexo H36 — Retipado de Cursos de Formación

---

**ABIERTO EN S109** (PCH CASO C desde H31, desvío en la misma
sesión). Ver "NOTA DE APERTURA" más abajo para el detalle completo.

## 1. Objetivo del hito

Retipar, contra contenido real (nunca por nombre de archivo), los
documentos históricos que hoy llevan el tipo genérico `FORMACION`
hacia el tipo de curso real que les corresponde, de entre los 14
tipos nuevos sembrados en `DocumentTypeCatalog` durante S109
(migración `0097_seed_formacion_tipos_curso_s109`):

- `FORMACION_EXTINCION_INCENDIOS`
- `FORMACION_ELECTRICIDAD`
- `FORMACION_SUBESTACIONES`
- `FORMACION_PRIMEROS_AUXILIOS`
- `FORMACION_OPERADOR_CAMION_AUTOCARGANTE`
- `FORMACION_TRABAJOS_ALTURA`
- `FORMACION_PLATAFORMA_ELEVADORA`
- `FORMACION_PRL_ART_18_19`
- `FORMACION_OPERADOR_APARATOS_ELEVACION`
- `FORMACION_PRL_60H`
- `FORMACION_OPERADOR_MINIGRUA`
- `FORMACION_CARRETILLAS_TRASPALETAS`
- `FORMACION_GRUAS_ASISTENCIA_CARRETERA`
- `FORMACION_GRUA_HIDRAULICA_ARTICULADA`

(Conviven con `FORMACION_ITC_MINERA`/`FORMACION_PRL_GENERICA`/
`FORMACION_PRL_MAQUINARIA`, ya existentes antes de esta sesión --
ningún solape real con los 14 de arriba.)

**Alcance deliberadamente acotado a trabajadores ACTIVOS** --
decisión explícita de Miguel Ángel (S109), verbatim: *"los cursos de
formación sí están ya asignados a una persona. Debemos de tipar
única y exclusivamente los de personas activas. No nos vamos a
entretener en obtener el texto OCR de trabajadores inactivos [...]
esos se quedarán con el genérico de formación. Si en un momento dado
[...] hiciera falta, como los tenemos en la papelera, podríamos
buscarlos cuando los necesitemos."*

## 2. Alcance real confirmado (consulta real S109, `db_query.yml`)

| | Documentos | Personas |
|---|---|---|
| **Fuera de alcance** (`is_active_employee=False`) -- se queda en `FORMACION`, sin tocar | 414 | 95 |
| **Alcance real de este hito** (`is_active_employee=True`) | **1.182** | **67** |

De los 1.182 documentos en alcance: **342 ya tienen `ocr_text`
cacheado** (`DocumentIndexEntry.ocr_text`, `CHAR_LENGTH > 0`), **840
no tienen OCR todavía** y hay que pasarlo antes de poder tipar.

Verificado que ningún documento de FORMACION en todo el corpus lleva
el curso en el nombre de archivo -- el patrón es siempre
`APELLIDOS_NOMBRE_FORMACION_FECHA.pdf` (a veces con sufijo `_N` o
`(N)` por duplicado) -- nunca clasificar por nombre, siempre por
contenido real (`ocr_text` o releer el PDF directamente).

## 3. Mecanismo a reutilizar (mismo patrón que H35)

H35 (`ENTERPRISEBOT_ATTACHED_MILESTONE_V35.md`) ya construyó el
mecanismo de retipado masivo contra contenido real
(`run_personal_retype_and_date`, `document_management.
vigencia_service.date_verification_service`) -- este hito reutiliza
esa misma infraestructura, nunca una segunda implementación paralela.
Diferencia real con H35: allí el reto era decidir SI el tipo asignado
era correcto (¿es de verdad una baja?); aquí el tipo genérico
(`FORMACION`) es correcto en todos los casos -- el reto es decidir
CUÁL de los 14/17 tipos específicos de curso le corresponde a cada
documento, que exige releer el contenido real del curso (título,
horas, temario) en cada uno.

## 4. Hoja de ruta original de apertura (S109) — sustituida por la sección "Hoja de ruta para la sesión siguiente" al final de este anexo

Orden fijo, sin preguntar por dónde empezar:

1. **Pasar OCR sobre los 840 documentos sin `ocr_text` cacheado**, de
   los 67 trabajadores activos únicamente (nunca sobre los 95
   inactivos, fuera de alcance por decisión explícita de Miguel
   Ángel). Decisión de Miguel Ángel sobre el orden de lectura, mismo
   criterio que H35: primero relanzar las VMs de OCR ya existentes
   (`h28-ocr-batch-1`, ver `SESSION_VARIABLES.md`) con Tesseract; solo
   si Tesseract no resuelve un documento concreto, recurrir a Google
   Cloud Vision.
2. **Retipar contra contenido real** cada uno de los 1.182 documentos
   -- releer `ocr_text` (o el PDF si el OCR no basta) y decidir el
   tipo de curso real de entre los 14 sembrados (más los 3 ya
   existentes, si algún caso encaja mejor ahí). Cualquier documento
   cuyo contenido no encaje con ninguno de los tipos ya sembrados
   (curso real no contemplado en el Excel de partida) se reporta a
   Miguel Ángel antes de inventar un tipo nuevo sobre la marcha --
   mismo criterio de la directriz 4.22.
3. **Criterio de cierre:** los 1.182 documentos en alcance retipados
   contra contenido real, verificado con consulta real (`db_query.yml`)
   de que ya no queda ningún documento de un trabajador activo con el
   tipo genérico `FORMACION`.

## 5. NOTA DE APERTURA (S109) — PCH desde H31

Durante la ejecución del punto 2 de la hoja de ruta ampliada de H31
("agrupar formación por tipo de curso"), se sembraron primero los 14
tipos de catálogo (migración `0097`, verificada real en producción).
Al plantear el retipado del histórico correspondiente (directriz
4.22, "ningún tipo nuevo se deja sin retipar su histórico"), la
consulta real reveló un volumen -- 1.182 documentos tras acotar a
activos -- mayor que el que motivó H35 en su momento (536). Miguel
Ángel decidió explícitamente abrir esto como su propio hito en vez de
un punto más de H31, y trabajarlo "en caliente" en la misma sesión.

Trabajo de H31 en esta misma sesión (S109), antes del PCH -- ver
"COMPLETADAS EN S109" en `ENTERPRISEBOT_ATTACHED_MILESTONE_V31.md`
para el detalle completo: grupos de reparto (punto 1), triángulo de
alerta con detalle (punto 3), y la siembra de catálogo de este mismo
punto 2 (commits `f140ba5`, `c0bc55c`, `98d71a9`).

## COMPLETADAS EN S109 -- campaña de 12 shards ejecutada y verificada

**NOTA DE DESVÍO:** el resto de esta misma sesión, tras lanzar la
campaña de abajo, se dedicó a un bloque grande de mejoras reales sobre
H31 mientras los shards corrían de fondo (EPIs en plantillas de
dosier, puestos de trabajo, mecanismo de cambio de tipo de documento,
UI/UX) -- registrado en su propio anexo, `ENTERPRISEBOT_ATTACHED_MILESTONE_V31.md`,
sección "COMPLETADAS EN S109 (continuación -- desvío de sesión tras el
PCH a H36)". El marcador `← EN PROGRESO` de este hito (H36) no se
movió durante ese desvío.

**Infraestructura previa al lanzamiento:**
- Incidente real de stockout alternante E2/N2 en `europe-west1-b` para
  `h28-ocr-batch-1` -- resuelto cambiando el tipo de máquina a
  `e2-standard-2` (commit `cacc6fd`).
- `h28-ocr-batch-1` puesta al día y usada para congelar la imagen
  `h28-ocr-batch-image-v2` (commit `7f4202e`), origen de las 4 VMs
  efímeras `h28-ocr-temp-1/2/3/4` (`e2-standard-8`) que ejecutaron los
  12 shards.
- 3 tipos nuevos de catálogo sembrados sobre la marcha, tras revisar
  muestras reales de `FORMACION` genérico que no encajaban en ninguno
  de los 14 del catálogo original: `CUESTIONARIO_FORMACION`,
  `PACTO_PERMANENCIA`, `JUSTIFICANTE_PAGO_PERSONAL` (migración `0098`,
  commit `4891099`).

**Lanzamiento y ejecución real de los 12 shards** (`extract_personal_dates_bulk.py
--retype --document-type FORMACION --shard-count 12 --apply`, uno por
ventana SSH, 3 shards por VM efímera):

- **10 de 12 shards terminaron a la primera** (1, 2, 4, 5, 7, 8, 9,
  10, 11, 12).
- **2 shards (3 y 6) murieron con `pymysql.err.OperationalError
  (2013, Lost connection to MySQL server during query)`** -- causa
  real confirmada por orden de commits (`git log`): las 4 VMs
  efímeras se clonaron de la imagen v2, que se congeló **antes** del
  commit `5e46a43` (el propio fix de `conn.ping(reconnect=True)` ante
  esa consulta ad-hoc, hecho en esta misma sesión) -- las VMs
  efímeras nunca tuvieron el fix. Corregido sin relanzar la campaña
  entera: `git pull` (con token pedido de forma interactiva, nunca en
  la URL -- corrección real de un error propio del modelo, que había
  dado un `git pull` a secas en VM, exactamente el incidente ya
  documentado y prohibido desde S97) en `h28-ocr-temp-1`/`h28-ocr-temp-2`,
  y solo esos 2 shards relanzados -- los candidatos ya retipados no se
  reprocesan, la consulta de candidatos ya los excluye.

**Resultado final, verificado contra BD real (`db_query.yml`), nunca
sumando de memoria los 12 resúmenes pegados por Miguel Ángel:**

| | Documentos |
|---|---|
| Punto de partida (activos, tipo genérico `FORMACION`) | 1.182 |
| Retipados con éxito a un tipo específico esta campaña | **352** |
| Quedan en `FORMACION` genérico | **830** |

Los 830 restantes se reparten entre tres motivos reales, visibles en
los 12 resúmenes de shard: **tipo ambiguo** (más de un tipo candidato,
nunca se escribe sin certeza -- 137 en total), **sin nada resoluble**
(ni Tesseract, ni EasyOCR, ni Cloud Vision sacaron texto usable -- 71
en total) y, para una parte del resto, formación genérica real sin
curso más específico que le corresponda todavía en el catálogo -- un
resultado final válido, no un fallo.

**VMs efímeras cerradas al cierre de la campaña**, verificando primero
que sus 3 shards respectivos habían terminado: `h28-ocr-temp-3`/
`h28-ocr-temp-4` (shards 7-12, todos terminados a la primera) borradas
durante la sesión; `h28-ocr-temp-1`/`h28-ocr-temp-2` (shards 1-6)
borradas al cierre, tras confirmar los 12 resúmenes completos.

## Hoja de ruta para la sesión siguiente

**Sin preguntas abiertas.** Orden fijo:

1. **Revisar a mano los 137 documentos "tipo ambiguo"** de los 12
   logs de shard (rutas `~/EnterpriseBot/h28_migration_agent/extract_personal_dates_shard{0..11}.log`
   en las VMs, ya borradas -- si los logs no sobrevivieron, releer
   `ocr_text` real de los que sigan en `FORMACION` con más de un tipo
   candidato plausible por contenido) y decidir el tipo real de cada
   uno contra el contenido, ampliando `CONTENT_SIGNALS` en
   `personal_content_classification.py` con la evidencia real
   encontrada -- nunca añadir una señal nueva sin muestra real que la
   respalde (directriz 4.22).
2. **Revisar los "sin nada resoluble"** (71) -- confirmar si el
   documento es genuinamente ilegible (releer el PDF directamente,
   nunca solo el `ocr_text` cacheado) o si merece un reintento con
   Cloud Vision con mejor preprocesado.
3. **Criterio de cierre del hito:** consulta real (`db_query.yml`)
   `SELECT COUNT(*) FROM document_explorer_documentindexentry e JOIN
   document_explorer_documenttypecatalog t ON t.id=e.document_type_id
   JOIN document_explorer_personidentity p ON p.id=e.domain_object_id
   WHERE t.code='FORMACION' AND e.deleted_at IS NULL AND
   e.purged_at IS NULL AND p.is_active_employee=1` devolviendo `0` --
   hoy devuelve `830`.
