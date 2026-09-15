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

**⛔ ALCANCE FIJO, SIN EXCEPCIÓN NI FLAG QUE LO RELAJE (S105, verbatim
Miguel Ángel): "única y exclusivamente trabajadores activos".** El
retipado de este hito nunca toca documentos de trabajadores
**inactivos** -- esos se quedan tal cual, se buscan y corrigen a mano
por el explorador de archivos si hace falta, nunca por un barrido
automático. `extract_personal_dates_bulk.py --retype` filtra siempre
por `PersonIdentity.is_active_employee=True`, sin ningún flag tipo
`--include-inactive` que lo desactive -- no crear uno sin que Miguel
Ángel lo pida explícitamente. Motivo, verbatim: no perder tiempo
ordenando documentación de gente que ya no está en la empresa.

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
que no es el titular de la ficha. **Criterio decidido en S104** (ver
Hoja de Ruta, punto 0): comprobado en el buscador de personal
(activos+inactivos, todas las empresas, incluido "sin empresa
asignada") que "Ana Requena Soler" no existe en el sistema -- por
tanto, a papelera. Regla general para el resto de casos que aparezcan:
si la persona nombrada existe como `PersonIdentity` real, mover el
documento a su ficha; si no existe, papelera.

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

**0. Criterio de remediación para documentos de otra persona real
(decidido en S104, verbatim tras comprobar en el buscador de personal
-- activos+inactivos, todas las empresas, incluido "sin empresa
asignada" -- que "Ana Requena Soler" no existe en el sistema):**
buscar primero si la persona nombrada en el documento existe ya como
`PersonIdentity` (activa o inactiva, cualquier empresa). Si existe,
mover el documento a su ficha real. Si no existe -- caso confirmado de
"Ana Requena Soler" -- el documento va a **papelera**
(`deleted_at`, mismo mecanismo ya usado por `trash_dossier_entry`),
nunca se deja archivado bajo una persona que no es la suya. Aplicar
este criterio sistemáticamente a cualquier documento de este hito
donde `_person_name_missing()` detecte un nombre real distinto del
titular de la ficha (no solo el caso de Jorge).

Queda además, como trabajo técnico normal (no decisión de negocio):
ejecutar la misma auditoría de contenido de S104 sobre el resto de
tipos de volumen alto de las familias `LABORAL`/`SALUD_BAJAS_PERSONA`
-- la sesión S104 solo confirmó el patrón de cajón de sastre en
`BAJA_PERSONAL`, sin comprobar si otros tipos comparten el mismo
problema. Cierre objetivo: para cada tipo de volumen alto auditado,
registrar en este anexo el mismo desglose que se hizo para
`BAJA_PERSONAL` (confirmados / proponen otro tipo / sin señal /
ambiguos / sin texto cacheado).

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

---

## Pendientes de revisión manual -- BAJA_PERSONAL (S105, cierre real)

**Nunca perder esta lista al borrar la VM que la produjo** -- vive
aquí, en el repo, no en un log de una VM efímera que se borra al
terminar la campaña (ver "MODELO DE CICLO DE VIDA DE LAS VMs" en
`SESSION_VARIABLES.md`).

De los 404 `BAJA_PERSONAL` de personal activo en toda la plataforma,
tras la campaña completa de `--retype` (con el motor corregido para
escalar de OCR mientras el TIPO no esté resuelto, no solo la fecha):
306 quedaron resueltos (tipo confirmado como baja real, o retipados a
su tipo real, o con fecha corregida). Quedan **98 sin resolver
automáticamente**, nunca forzados a un tipo que el contenido no
respalda:

**13 AMBIGUOS** (dos o más tipos reales mezclados en el mismo PDF --
contenido genuinamente mixto, no fallo de diccionario):
```
28930  ALVAREZ_SERRANO_ENRIQUE_BAJA_PERSONAL_20091110.pdf       [CONTRATO, PARTE_BAJA_MEDICA]
28964  ALVAREZ_VIEIRA_LEANDRO_JAVIER_BAJA_PERSONAL_20150417_3.pdf [CONTRATO, IDC]
29195  CRUCES_HEREDIA_JOSE_MANUEL_BAJA_PERSONAL_20170524_1.pdf   [CONTRATO, IDC]
30088  REBOLLO_MANZANO_JACINTO_BAJA_PERSONAL_20250113_3.pdf      [CONTRATO, IDC]
30354  ALVAREZ_SERRANO_ENRIQUE_BAJA_PERSONAL_20110721.pdf        [CONTRATO, PARTE_BAJA_MEDICA]
30356  ALVAREZ_SERRANO_ENRIQUE_BAJA_PERSONAL_20810613.pdf        [CONTRATO, PARTE_BAJA_MEDICA]
30358  ALVAREZ_SERRANO_ENRIQUE_BAJA_PERSONAL_20110721_1.pdf      [CONTRATO, PARTE_BAJA_MEDICA]
32001  MARTIN_GONZALEZ_JESUS_BAJA_PERSONAL_20150303_1.pdf        [CONTRATO, IDC]
32024  MARTIN_GONZALEZ_JESUS_BAJA_PERSONAL_20191026.pdf          [CARNET_CONDUCIR, TARJETA_CUALIF_CONDUCTOR]
32720  RAMIREZ_GARCIA_JORGE_BAJA_PERSONAL_20081217.pdf           [CONTRATO, IDC, PARTE_BAJA_MEDICA]
32731  RAMIREZ_GARCIA_JORGE_BAJA_PERSONAL_20181120.pdf           [CARNET_GRUISTA, RECONOCIMIENTO_MEDICO]
32779  RAMIREZ_GARCIA_JORGE_BAJA_PERSONAL_20081217_1.pdf         [CONTRATO, IDC]
32828  RAMIREZ_GARCIA_JORGE_BAJA_PERSONAL_20100212.pdf           [AUTORIZACION_USO_MAQUINARIA, CONTRATO, PARTE_BAJA_MEDICA]
```

**85 SIN SEÑAL** (ningún signal del diccionario coincide, ni tras
pasar por Tesseract→EasyOCR→Cloud Vision):
```
28245 28249 28251 28255 28256 28266 28271 28276 28937 28942 28955
28959 28960 28961 28962 28965 28966 28968 29194 30077 30078 30081
30083 30084 30085 30086 30087 30091 30347 30357 30582 30583 30584
30586 30598 30603 31972 31973 31978 31992 31995 32023 32732 32733
32736 32737 32739 32743 32760 32761 32765 32771 32776 32782 32783
32784 32785 32798 32800 32801 32829 32830 32832 32835 32837 32838
36737 36945 36947 37106 37339 37340 37341 37342 37527 37531 37532
37543 37794 37795 37796 37949 39829 40251 42793
```

**Casos ya inspeccionados visualmente dentro de este bloque, con
motivo real confirmado (no van a resolver con más diccionario):**
- `28245` (Grana Álvarez, Paloma): ficha ITV de un Volkswagen,
  matrícula 8534-BGX -- documento de un **vehículo**, mal archivado
  por completo bajo una persona. Encaja en el criterio de
  remediación del punto 0 (mover a donde corresponda -- en este caso
  ni siquiera a otra `PersonIdentity`, sino fuera del dominio
  personal), pendiente de ejecutar.
- `39829` (Rueda Escudero, Julio Alberto): factura de Correos por un
  burofax -- contenido real es una factura de mensajería, sin
  información de RRHH clasificable. Legítimamente sin tipo de
  personal real.
- `pk=41145`/`42128` (EPIS de Jorge Milheiro Felicio y Francisco
  Gómez Rivero, archivados bajo la ficha de Jorge Ramírez García,
  carpeta `_CUARENTENA`): confirmado en S105 que son documentos de
  **otra persona real** -- aplicar el criterio de remediación del
  punto 0 (mover a su `PersonIdentity` real si existe, papelera si
  no). Pendiente de ejecutar, no de diagnosticar.

**Todavía sin ejecutar de este bloque:** el criterio de remediación
completo del punto 0 (buscar sistemáticamente, con
`_person_name_missing()`, cualquier documento de otra persona real
entre los 85 "sin señal" restantes -- los 2 casos de arriba se
encontraron por inspección manual puntual, no por un barrido
sistemático).
