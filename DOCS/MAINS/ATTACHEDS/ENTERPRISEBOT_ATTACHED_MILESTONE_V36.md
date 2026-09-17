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

## 4. Hoja de ruta para la sesión siguiente (S110)

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
