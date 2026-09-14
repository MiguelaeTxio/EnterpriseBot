# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V35.md
# Anexo H35 — Retipado y Refechado Masivo de Documentación Histórica de Personal

---

**ABIERTO EN S104 (2026-09-14), PCH desde H31 en la misma sesión.**
Hito nacido de un hallazgo real durante una sesión de trabajo de H31
(punto 0, desvío al Laboratorio de Análisis) que, al investigar por
qué 77 trabajadores activos no tenían `hire_date` en ficha, escaló en
la misma sesión hasta descubrir un problema estructural mucho mayor.
Miguel Ángel, explícito: esto no es un desvío puntual dentro de H31,
es su propio hito.

---

## 1. Objetivo del hito

Releer el **contenido real** (nunca el nombre de archivo, nunca la
carpeta -- los dos demostrados indignos de confianza en esta misma
sesión) de la documentación histórica de Personal afectada por un
patrón de "cajón de sastre" en la migración original, resolver su
**tipo documental real** y su **fecha real**, y corregir en BD --
reutilizando el mecanismo ya construido en H31-S104
(`document_explorer/management/commands/run_personal_retype_and_date.py`),
con el diccionario de señales de contenido ampliado a los tipos reales
descubiertos en la muestra de esta sesión.

**Decisión explícita de Miguel Ángel sobre el orden de lectura para
este hito (verbatim):** "resolver en la siguiente sesión todo esto
mediante la máquina virtual, utilizando primero Tesseract y luego, si
no podemos resolver con Tesseract, utilizando Google Cloud Vision."
Esto es una excepción deliberada, **solo para este hito**, a la
decisión general de la plataforma (S102, "nunca Tesseract, siempre
Cloud Vision") -- aquí se prioriza el coste (las VMs de OCR ya están
pagadas y dimensionadas para lotes grandes) sobre la calidad de
extracción, precisamente porque el volumen esperado es alto.

---

## 2. Contexto técnico de partida (S104)

### El hallazgo, en cifras reales

- **135 ficheros** (9 tipos documentales distintos: `CONTRATO`,
  `FORMACION`, `ALTA`, `MOD_145`, `RECONOCIMIENTO_MEDICO`,
  `BAJA_PERSONAL`, `COMUNICACION_JORNADA`, `CAP`,
  `TARJETA_CUALIF_CONDUCTOR`) de **47 trabajadores activos** tenían la
  fecha de nacimiento de la persona colada como `issue_date`/
  `expiry_date` -- bug del pipeline histórico (H28), anterior a la
  protección `_BIRTHDATE_CONTEXT` que ya existe en
  `date_verification_service.classify_dates_in_text` (verificado en
  frío: el motor actual, releyendo el mismo texto ya cacheado, NO
  repite el error).
  - **20 de los 135** ya corregidos en S104 (texto cacheado, candidata
    limpia distinta de la fecha de nacimiento) -- ver commits de la
    sesión.
  - **19 con texto cacheado pero ambiguo** y **96 sin texto
    cacheado**: pendientes de este hito.

- **`BAJA_PERSONAL` como cajón de sastre.** Auditoría real (Comando S,
  S104) sobre **536 documentos** `BAJA_PERSONAL` en **toda la
  plataforma** (no solo activos): de los **158** que ya tienen
  `ocr_text` cacheado y se pueden juzgar sin gastar nada --
    - Solo **4** confirman ser una baja real.
    - **50** proponen abiertamente otro tipo por contenido:
      `CONTRATO` (19), `CARNET_CONDUCIR` (8), `RECONOCIMIENTO_MEDICO`
      (7), `NOMINA` (4), `PARTE_BAJA_MEDICA` (4), `IDC` (3), `CURSO`
      (3), `MOD_145` (1), `ALTA` (1).
    - **95** no dan ninguna señal con el diccionario de S104 --
      corresponden a tipos que ni siquiera están todavía cubiertos
      (ver más abajo).
    - **9** ambiguos (más de una señal a la vez).
  - **378 sin `ocr_text` cacheado todavía** -- alcance real
    desconocido hasta releerlos.

- **Caso real de muestra completa: Jorge Ramírez García (DNI
  53696300V).** De sus **89** ficheros `BAJA_PERSONAL`, prácticamente
  ninguno es una baja real: certificados de formación PRL (formato
  "M.P.E. Servicio de Prevención de Riesgos Laborales... CERTIFICA"),
  reconocimientos médicos (formato "D./Dña. [nombre del médico],
  Médico Especialista en Medicina del Trabajo..."), permisos de
  conducir, tarjeta de conductor/tacógrafo, tarjeta sanitaria,
  designación de recurso preventivo ("DESIGNACIÓN DE RECURSO
  PREVENTIVO. En MALAGA a [fecha]..."), capacitación ("CAPACITACION
  POR PARTE DE LA EMPRESA DE LAS ACTIVIDADES QUE PUEDE REALIZAR EL
  TRABAJADOR"), autorización, solicitud de tipo de retención IRPF,
  entrega de EPIs, comunicación de contrato, e incluso **dos
  documentos de otra persona real** ("ANA REQUENA SOLER" -- un
  certificado bancario con IBAN y un justificante de intervención
  quirúrgica), archivados por error en la ficha de Jorge.

### Tipos documentales nuevos a añadir al diccionario de señales

Ninguno de estos está todavía en `CONTENT_SIGNALS` de
`run_personal_retype_and_date.py` -- confirmados contra la muestra real
de Jorge, hace falta extraer la frase distintiva exacta de cada uno
antes de añadirlos (evitar palabras sueltas, mismo criterio que el
resto del diccionario):

- Certificado de formación PRL genérico ("M.P.E. Servicio de
  Prevención de Riesgos Laborales... CERTIFICA: Que el trabajador que
  a continuación se relaciona...") -- distinto del `CERTIFICADO DE
  FORMACIÓN` ya cubierto por `FORMACION`/`CURSO`, este es un
  certificado de aptitud/vigilancia, probablemente `CERTIFICADO_EXAMEN`
  o `RECONOCIMIENTO_MEDICO` según el contenido exacto -- verificar.
- `RECURSO_PREVENTIVO` / `NOMBRAMIENTO_RECURSO_PREVENTIVO` --
  "DESIGNACIÓN DE RECURSO PREVENTIVO. En [ciudad] a [fecha]... Sr.
  D./Dña. [nombre]".
- `AUTORIZACION_GENERICA` -- "AUTORIZACIÓN... D. [nombre] con DNI...
  como representante de la empresa...".
- Capacitación de actividades -- "CAPACITACION POR PARTE DE LA EMPRESA
  DE LAS ACTIVIDADES QUE PUEDE REALIZAR EL TRABAJADOR" (tipo exacto a
  determinar contra el catálogo -- no hay un `CAPACITACION` en la
  tabla actual, podría ser `FORMACION_PRL_MAQUINARIA` o requerir tipo
  nuevo).
- `EPIS` (Entrega de EPIs) -- "ENTREGA DE EPI'S. FECHA: ...".
- `COMUNICACION_CONTRATO` -- "COMUNICACIÓN DEL CONTRATO DE...".
- `CAMBIO_IRPF` -- "SOLICITUD DE TIPO DE RETENCIÓN IRPF SUPERIOR AL
  CALCULADO REGLAMENTARIAMENTE".
- `TACOGRAFO` (Tarjeta de Conductor) -- "TARJETA DE CONDUCTOR... REINO
  [de España]", distinto de `CARNET_CONDUCIR` (permiso de conducción).

### Documentos de otra persona real (no solo IBAN corto)

El caso "ANA REQUENA SOLER" en la ficha de Jorge es distinto del caso
ya resuelto en S104 (documentos cortos tipo IBAN, que se dejan en paz
por longitud insuficiente) -- aquí el documento es largo y
perfectamente legible, y **sí** lleva el nombre de una persona real
que no es el titular de la ficha. Queda **sin decidir** el criterio de
remediación: ¿mover el documento a la ficha de esa persona si existe
en el sistema? ¿dejarlo en cuarentena/revisión manual? -- decidir con
Miguel Ángel al arrancar la sesión, antes de procesar en masa.

---

## 3. Herramientas ya construidas, reutilizables directamente

- `document_explorer/management/commands/run_personal_retype_and_date.py`
  (H31-S104): dry-run por defecto, `--apply` para escribir,
  `CONTENT_SIGNALS`/`CONTENT_WINS` para resolver tipo por contenido,
  `_person_name_missing()` (con umbral mínimo de longitud y
  comparación aproximada tolerante a ruido de OCR),
  `_text_encoding_is_broken()` (PDF con capa de texto interna rota),
  detección de PDF dinámico de Adobe (XFA), y ruteo a
  `extract_expiry_via_gemini()` para tipos `ocr_unreliable=True`.
  Motor de lectura actual: `date_verification_service.extract_text()`
  (Cloud Vision, nunca Tesseract) -- **este hito requiere añadir
  explícitamente la vía Tesseract/VM como primer intento**, algo que
  el comando actual no hace todavía.
- `h28_migration_agent/extract_personal_dates_bulk.py` y el resto de
  scripts de `h28_migration_agent/` (VMs `h28-ocr-batch-1..4`,
  suspendidas) -- candidatos reales para la vía Tesseract de este
  hito; revisar su estado y si clasifican tipo además de fecha antes
  de decidir si se reutilizan tal cual o se adaptan.
- `DocumentTypeCatalog.ocr_unreliable` (activado en S104 para
  `DNI`/`NIE`/`CARNET_CONDUCIR`/`TARJETA_CUALIF_CONDUCTOR`/
  `TACOGRAFO`) -- revisar si algún tipo nuevo descubierto en este
  hito también lo necesita.

---

## Hoja de Ruta para la Sesión Siguiente (S105)

**0. Decidir con Miguel Ángel, antes de procesar nada en masa:**
   - Criterio de remediación para documentos de otra persona real
     (caso "Ana Requena Soler") -- mover, poner en cuarentena, o
     revisión manual uno a uno.
   - Si además de `BAJA_PERSONAL` hace falta auditar otros tipos
     `LABORAL`/`SALUD_BAJAS_PERSONA` de volumen alto por el mismo
     patrón de cajón de sastre (la sesión S104 solo confirmó
     `BAJA_PERSONAL`, no descartó que otros tipos tengan el mismo
     problema).

**1. Estado real de las VMs de OCR.** Comprobar con `gcloud` si
`h28-ocr-batch-1..4` siguen existiendo (S104 las dio por
"suspendidas", verificar que no se hayan borrado) y reanudarlas.
Revisar `h28_migration_agent/extract_personal_dates_bulk.py` (y
scripts hermanos) para confirmar si ya resuelven tipo documental
además de fecha, o si hace falta extenderlos con
`CONTENT_SIGNALS`/`CONTENT_WINS` de `run_personal_retype_and_date.py`
(mismo diccionario, evitar mantener dos copias divergentes).

**2. Ampliar el diccionario de señales** con los tipos nuevos
listados en la sección 2 de este anexo -- confirmar la frase exacta
contra 2-3 muestras reales de cada uno antes de darla por buena (mismo
rigor que el resto de `CONTENT_SIGNALS`, nunca palabra suelta).

**3. Releer con Tesseract (VM) los 378 `BAJA_PERSONAL` sin `ocr_text`
cacheado**, más los 96 de la fecha de nacimiento colada sin texto
cacheado. Cachear el texto resuelto en `ocr_text` según se vaya
obteniendo (mismo campo/convención ya establecida). Lo que Tesseract
no resuelva con confianza, pasa a Cloud Vision (vía
`run_personal_retype_and_date.py`, añadiendo el brazo Tesseract como
intento previo al ya existente).

**4. Aplicar en producción** con el mismo criterio dry-run → revisión
→ `--apply` ya validado en S104 -- nunca escribir en masa sin una
muestra revisada primero, mismo patrón que toda esta sesión.

**5. Cierre objetivo de esta primera sesión de H35:** los 536
`BAJA_PERSONAL` de toda la plataforma retipados/refechados
correctamente (o marcados explícitamente para revisión manual con
motivo), y medida la extensión real del problema a otros tipos si el
punto 0 confirmó que hacía falta auditar más allá de `BAJA_PERSONAL`.
