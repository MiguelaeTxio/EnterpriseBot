# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V35.md

## ⚠️ DATO CRÍTICO DE CONTINUIDAD, YA RESUELTO -- CERRADO EN S106, CONFIRMADO DE NUEVO EN S107

**Registro afectado:** `PersonIdentity`, DNI `74633524L`, Miguel
Ángel Muñoz Cara. **Cerrado en S106**, confirmación directa de Miguel
Ángel: su ficha recreada está bien, ningún `CONTRATO` es en realidad
una nómina. Sin ninguna acción pendiente -- este bloque se deja aquí
solo como constancia histórica del incidente real (fallo de ingesta
que motivó todo H35), no como tarea abierta. Detalle completo del
incidente original en el historial de commits de S104/S105 si hiciera
falta consultarlo.

---


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

## COMPLETADAS EN S105

**Resumen:** sesión larga dedicada casi por completo a H35 -- se
retomaron las VMs de OCR, se extendió el agente H28 con un modo de
retipado real por contenido, se amplió el diccionario de señales con
todos los tipos nuevos confirmados con muestra real, se corrigieron
dos bugs de fondo del propio motor de escalado de OCR, y se ejecutó
la campaña completa de `--retype` sobre `BAJA_PERSONAL`, `ALTA`,
`CONTRATO`, `IDC`, `RECONOCIMIENTO_MEDICO` e
`INVESTIGACION_ACCIDENTE`. De paso, se rediseñó por completo el
modelo de ciclo de vida de las VMs de OCR (incidente real de una VM
sin clave SSH a mitad de campaña), y se construyó una funcionalidad
nueva no relacionada con H35 pedida por Miguel Ángel a mitad de
sesión: generación de dosieres para varios trabajadores a la vez.

**Motor de retipado (`h28_migration_agent/extract_personal_dates_bulk.py`,
modo `--retype`):** nuevo, reutiliza sin duplicar el diccionario de
`run_personal_retype_and_date.py`, ahora extraído a un módulo
compartido sin dependencias de Django
(`document_explorer/personal_content_classification.py`) para que lo
importe también el agente standalone de la VM. Cadena de motores
Tesseract (PSM automático) → Tesseract PSM 6 → EasyOCR → Cloud
Vision, decisión explícita de Miguel Ángel para este hito (excepción
a la regla general de la plataforma, S102).

**Dos bugs reales de fondo corregidos en el motor, ambos con impacto
retroactivo en resultados de campañas ya corridas:**
1. El escalado de motor paraba en cuanto aparecía CUALQUIER fecha
   resoluble, aunque el TIPO siguiera sin resolver -- muchos
   documentos se daban por "resueltos" con solo fecha, sin llegar
   nunca a EasyOCR/Cloud Vision, que sí habrían encontrado la frase
   de tipo real. Corregido (`_type_settled()`, commit `3617346`):
   ahora se sigue escalando mientras el tipo no esté resuelto sin
   ambigüedad, tenga ya fecha o no.
2. Las frases de `CONTENT_SIGNALS` se comparaban contra el texto tal
   cual, sin normalizar saltos de línea -- una frase real partida en
   dos líneas por el OCR (p. ej. "ACTIVIDADES\nQUE PUEDE...") nunca
   hacía match aunque un humano la reconociera al instante. Corregido
   (commit `823b728`): normalización de espacios en blanco en el
   único punto donde se comparan frases.

**Diccionario `CONTENT_SIGNALS` ampliado**, todo confirmado contra
muestra real (nunca palabra suelta): `AUTORIZACION_GENERICA`,
`CAPACITACION`, `FORMACION_PRL_GENERICA`, `RECURSO_PREVENTIVO`
(códigos de catálogo nuevos, migraciones `0084`-`0086`);
`CAMBIO_IRPF`, `COMUNICACION_CONTRATO`, `AUTORIZACION_USO_MAQUINARIA`,
`TACOGRAFO`, `TARJETA_CUALIF_CONDUCTOR`, `EPIS` (códigos ya
existentes, solo les faltaba el signal); variantes de redacción reales
encontradas después (`OPERADOR DE GRUA MOVIL` singular, `HAN
REALIZADO EL CURSO`, artefacto de OCR "MA QUINARIA" con espacio
insertado); `INVESTIGACION_ACCIDENTE` y `EXPEDIENTE_DISCIPLINARIO`
(códigos ya existentes, signal nuevo). Dos reglas de desempate
(`CONTENT_WINS`) nuevas por falsos positivos sistemáticos de
formularios oficiales: `ALTA` gana sobre `PARTE_BAJA_MEDICA`
(formulario RETA de autónomos, cláusula de cobertura de incapacidad
temporal) e `IDC` gana sobre `CONTRATO` (el propio formulario IDC
trae "INICIO/FIN CONTRATO DE TRABAJO" como etiqueta de casilla).

**Campañas `--retype` completas, alcance fijo `is_active_employee=True`
únicamente (decisión explícita y sin excepción de Miguel Ángel --
nunca tocar documentación de trabajadores inactivos con este barrido):**

| Tipo | Total activos | Retipados | Fecha corregida | Ambiguos reales | Sin señal |
|---|---|---|---|---|---|
| `BAJA_PERSONAL` | 404 | ~166 | ~318 (solapado) | 13 | 85 |
| `ALTA` | 304 | 51 | 191 | 6 | 7 |
| `CONTRATO` | 449 | ~146 | -- | 6 | 4 |
| `IDC` | 250 | 74 (bloque) | -- | 3 | -- |
| `RECONOCIMIENTO_MEDICO` | 689 | 17 | 556 | 0 | 21 |
| `INVESTIGACION_ACCIDENTE` | 661 | 96 | 173 | 0 | 34 |
| `PAGO_CORRIENTE` | -- | -- | -- | fuera de alcance (dominio `CompanyWorksite`, nunca `PersonIdentity`) | -- |

Todas las listas completas de IDs pendientes (ambiguos + sin señal)
quedan comiteadas en las secciones "Pendientes de revisión manual" de
este mismo anexo, más abajo -- nunca solo en un log de una VM efímera
que ya no existe.

**Incidente real durante `IDC`:** la campaña de 3 shards de `IDC`
corrió con código previo al fix `IDC`/`CONTRATO` (la imagen
`h28-ocr-batch-image-v3` se había congelado antes de ese commit),
reportando 169 ambiguos falsos. Reclasificación directa del
`ocr_text` ya cacheado contra el diccionario corregido confirmó que
solo 3 son ambiguos de verdad -- verificado también que no quedó
ningún dato mal escrito en BD (los ambiguos nunca se escriben).

**Modelo de ciclo de vida de las VMs de OCR, rediseñado de raíz**
(incidente real: `h28-ocr-batch-3`, creada de la misma imagen que
`h28-ocr-batch-1/2` pero nunca usada, no tenía la clave SSH hacia
PythonAnywhere -- la imagen se había congelado antes de que esa clave
existiera en el disco de origen). Se abandona el modelo de "4 VMs
fijas siempre encendidas/suspendidas"; documentado completo en
`SESSION_VARIABLES.md` (sección de máxima visibilidad, principio del
bloque de VMs): `h28-ocr-batch-1` es la única VM con disco
persistente; para escalar, se pone al día, se para del todo (nunca
suspendida) y se congela una imagen nueva (`vN` incremental); el
paralelismo se consigue con VMs efímeras creadas desde esa imagen,
que se BORRAN siempre al terminar la campaña, nunca se quedan
suspendidas. Cuota real de CPU confirmada: `CPUS_ALL_REGIONS`=32,
máximo 4 VMs `e2-standard-8` efímeras simultáneas.

**Funcionalidad nueva, no relacionada con H35, pedida por Miguel
Ángel a mitad de sesión:** generación de dosieres para varios
trabajadores a la vez. Página propia de gestión de plantillas
(`panel:dossier_templates_manage`, todos los tipos agrupados por
familia y coloreados, sin acordeón, plantillas guardadas arriba,
previsualización de tipos marcados), acción masiva nueva en el
listado de Personal (plantilla + modo de agrupación -- PDF por
trabajador / ZIP por trabajador / todo junto, siempre PREGUNTADO,
nunca asumido -- + descarga o envío por correo, este último siempre
un `.eml` independiente por trabajador por privacidad), marcado
visual en el listado de quién le falta algún documento de la
plantilla elegida. De paso: campo `PersonIdentity.avatar_document`
nuevo (usar un documento-imagen ya indexado como foto de perfil sin
perder su clasificación real), y fix del modal de "Ver documento"
que se cerraba junto con el de Historial.

**Migraciones de esquema reales de esta sesión:** `0084`-`0086`
(siembra de catálogo, sin cambio de esquema), `0087` (campo nuevo
`avatar_document`, `AddField` nullable simple). Todas desplegadas
automáticamente vía `deploy.yml` tras cada push -- sin incidencia
reportada.

**Dos correcciones de etiqueta sin relación con lo anterior:**
"Grúas Aldi S.L." → "GRUALDI S.L." y "Transgrúal S.L." → "TRANSGRUAL
S.L." en el filtro de empresa del listado de Personal (el Excel real
ya tenía el nombre correcto, `GRUALDI S.L`/`TRANSGRUAL SL` -- el
desajuste era solo la etiqueta visible).

## Pendientes de revisión manual -- BAJA_PERSONAL (S105, cierre real)

**⛔ RESUELTO EN S107 -- ver "COMPLETADAS EN S107" más abajo.** Los 98
reales (13 ambiguos + 85 sin señal) quedaron cerrados al 100%, salvo
2 documentos (`28255`/`28256`) que necesitaron un tipo de catálogo
nuevo (`COMUNICACION_INSPECCION_TRABAJO`), ya dado de alta y aplicado.

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

---

## Pendientes de revisión manual -- CONTRATO (S105)

**⛔ RESUELTO EN S107 -- ver "COMPLETADAS EN S107" más abajo.** Los 10
reales quedaron cerrados al 100%: los 6 ambiguos eran falso positivo
sistemático del diccionario (signal `INCAPACIDAD TEMPORAL` corregido),
los 4 sin señal retipados/corregidos.

De 449 `CONTRATO` de personal activo, 146 quedaron resueltos (fecha
corregida y/o retipados), 303 confirmados como contrato real. Quedan
**10 pendientes** (mucho menor proporción que `BAJA_PERSONAL` -- este
tipo no compartía el mismo patrón de cajón de sastre tan agudo):

**6 AMBIGUOS** (mismo patrón real ya visto: contrato + parte médico
mezclados en el mismo PDF, todos del mismo trabajador):
```
35635  GOMEZ_GARCIA_JOSE_ANTONIO_CONTRATO_20680318.pdf    [CONTRATO, PARTE_BAJA_MEDICA]
35637  GOMEZ_GARCIA_JOSE_ANTONIO_CONTRATO_20680318_1.pdf  [CONTRATO, PARTE_BAJA_MEDICA]
35639  GOMEZ_GARCIA_JOSE_ANTONIO_CONTRATO_20070902.pdf    [CONTRATO, PARTE_BAJA_MEDICA]
35640  GOMEZ_GARCIA_JOSE_ANTONIO_CONTRATO_20680318_2.pdf  [CONTRATO, PARTE_BAJA_MEDICA]
35641  GOMEZ_GARCIA_JOSE_ANTONIO_CONTRATO_20680318_3.pdf  [CONTRATO, PARTE_BAJA_MEDICA]
35684  GOMEZ_GARCIA_JOSE_ANTONIO_CONTRATO_19680318_1.pdf  [CONTRATO, PARTE_BAJA_MEDICA]
```

**4 SIN SEÑAL:**
```
34098  ALVAREZ_GEA_ALBERTO_ADOLFO_CONTRATO_20111231.pdf
35636  GOMEZ_GARCIA_JOSE_ANTONIO_CONTRATO_20111231.pdf
36311  MARTINEZ_SEGURA_JOSE_CARLOS_CONTRATO_20210101.pdf
39831  RUEDA_ESCUDERO_JULIO_ALBERTO_CONTRATO_20251222.ordinario firmado-signe
```

---

## Pendientes de revisión manual -- IDC, RECONOCIMIENTO_MEDICO, INVESTIGACION_ACCIDENTE (S105)

**⛔ ACTUALIZADO EN S107 -- ver "COMPLETADAS EN S107" más abajo.** Los
recuentos de esta sección eran de S105 y **nunca se comiteó la lista
real de IDs** (solo el número) -- error real, mismo patrón que se
corrigió en S107. `IDC` quedó cerrado al 100% (y de paso se corrigió
un bug real de fechas). `RECONOCIMIENTO_MEDICO`/`INVESTIGACION_ACCIDENTE`
**siguen con pendiente real** -- ver Hoja de Ruta, listas de IDs
reales comiteadas en "COMPLETADAS EN S107".

**IDC** (250 activos): 176 quedaron sin retipar (ya eran IDC reales),
74 resueltos con fecha/tipo. De los 176: **solo 3 ambiguos reales**
(comprobado por reclasificación directa del `ocr_text` cacheado
contra el diccionario ya corregido -- la campaña de 3 shards corrió
por error con código previo al fix IDC/CONTRATO de este mismo
anexo, imagen `h28-ocr-batch-image-v3` congelada antes de ese commit;
como los ambiguos nunca se escriben, no quedó ningún dato incorrecto
en BD, solo el log de la campaña sobreestimó el problema).

**RECONOCIMIENTO_MEDICO** (689 activos): 556 fechas corregidas, 17
retipados, 21 sin nada, 0 ambiguos -- tipo mayormente bien
clasificado desde el origen, como se sospechaba.

**INVESTIGACION_ACCIDENTE** (661 activos): 173 fechas corregidas, 96
retipados, 34 sin nada, 0 ambiguos.

**PAGO_CORRIENTE** (1.762 documentos): fuera de alcance de
`--retype` -- vive vinculado a `CompanyWorksite` (empresa y obra),
nunca a `PersonIdentity`. Confirmado, no es un olvido.

---

## COMPLETADAS EN S106

**Resumen:** sesión larga, con un intento fallido de cierre a medio
camino (se llegó a proponer abrir S107 con PISA/PAH sin haber
cerrado S106 con PCS -- corregido al momento por aviso directo de
Miguel Ángel, sin consecuencias reales más allá de una caja de texto
anulada). Se cerraron 3 de los 6 tipos del punto 1 de H35
(`AUTONOMO`, `MOD_145`, `REGISTRO_JORNADA`), con el hallazgo más
fuerte de todo el hito hasta ahora en este último (90% cajón de
sastre). De paso, un desvío de sesión no relacionado con H35: rediseño
completo del flujo de plantillas de dosier (H31, S103/S105) a partir
de feedback directo de uso real de Miguel Ángel sobre la propia
interfaz.

**Desvío de sesión -- plantillas de dosier (`document_explorer/models.py`,
`panel/views_documentation_h30.py`, `panel/urls.py`,
`panel/templates/panel/dossier_templates_h35/manage.html`,
`panel/templates/panel/documentation_h30/_personal_dossier_template_list.html`):**
1. `PersonalDossierTemplate.is_active` (migración `0089`): selector
   de "plantilla activa" en el gestor -- botón que se convierte en
   insignia verde, en vez del radio sin etiqueta del primer intento.
2. `PersonalDossierTemplate.output_format` **eliminado** (migración
   `0090`) -- Miguel Ángel: "tenemos el zip y tenemos el PDF y hacemos
   dos plantillas [...] creo que es un error, solamente una
   plantilla". El formato se pregunta siempre al aplicar
   (`PersonalDossierTemplateApplyView` exige `?format=` explícito,
   nunca por defecto), nunca se guarda por plantilla. Eliminadas de
   paso `PersonalDossierTemplateCreateView`/`UpdateView` (dead code ya
   superseded) y `DuplicateView` (su único propósito era el formato
   contrario, ya no aplica).
3. "Marcar como activa" ya no abre un botón de previsualizar aparte
   -- carga sus tipos directamente en el panel de trabajo, con un
   visor siempre visible (con su propio scroll) que muestra en vivo
   los tipos marcados y usa el nombre de la plantilla como membrete.
   Detección de cambios sin guardar (nombre/tipos distintos de lo
   último cargado o guardado): activar otra plantilla o cerrar la
   pestaña con cambios pendientes pregunta si guardar antes.
4. Ajustes de UX menores sobre feedback directo: tipos incluidos en
   columnas de lectura vertical (`columns: 3` CSS) en vez de fila
   envuelta; alineación de la fila Nombre/Formato del formulario.

**Incidencias de protocolo reales de la sesión (autocorregidas, sin
impacto en producción):**
- Se generó y activó `DocumentTypeCatalog.ocr_unreliable=True` para
  `AUTONOMO` por una hipótesis incorrecta sobre su funcionamiento
  (se creía que saltaba motores OCR; en realidad solo descarta la
  fecha resuelta) -- revertido antes de causar ningún daño real, tras
  revisar el código fuente del propio script. Corregido con un campo
  nuevo y semánticamente distinto, `skip_light_ocr_engines`.
- Una consulta ORM real se entregó sin el envoltorio `SWAP` + `sftp`
  obligatorio de `com-bash-commands` sección 4 -- señalado por Miguel
  Ángel, corregido en la siguiente caja.
- Se intentó abrir sesión S107 (PISA completo + caja de PAH Momento 1)
  sin haber cerrado S106 con PCS -- señalado por Miguel Ángel antes de
  ejecutar ningún comando real, caja de PAH anulada sin uso.

**Herramienta nueva:** `DocumentTypeCatalog.skip_light_ocr_engines`
(migración `0088`) + `h28_migration_agent/extract_personal_dates_bulk_fast.py`,
variante de `extract_personal_dates_bulk.py`. Origen real: dry-run de
10 documentos `AUTONOMO`, 10/10 agotaron los 4 motores hasta Cloud
Vision sin que Tesseract/EasyOCR resolvieran ni uno solo -- relanzar
esa cadena completa sobre 189 documentos habría supuesto ~15h de
intentos locales sin ningún valor. El campo es **distinto** de
`ocr_unreliable` (que exige razonamiento de Gemini Vision y descarta
la fecha resuelta): `skip_light_ocr_engines` solo salta Tesseract/
EasyOCR cuando una muestra real ya demostró que nunca resuelven nada
para ese tipo, y la fecha resuelta por Cloud Vision se escribe con
normalidad. Verificado que ningún otro punto de la plataforma lee
este campo -- cero interferencia con la ingesta normal ni con otros
tipos documentales. Con el atajo activo, la campaña completa de 189
documentos tardó ~7 minutos en un único proceso (sin VMs efímeras ni
imagen nueva) -- activar este flag caso a caso, solo tras confirmar
el patrón con un dry-run real, nunca por suposición.

**Campaña `--retype` completa, alcance fijo `is_active_employee=True`:**

| Tipo | Total activos | Retipados | Fecha corregida | Ambiguos reales | Sin señal |
|---|---|---|---|---|---|
| `AUTONOMO` | 189 | 0 | 176 | 0 | 13 |
| `MOD_145` | 125 (no 161 -- la hoja de ruta partía de una estimación previa a auditar, corregido aquí) | 0 | 114 | 4 | 7 |
| `REGISTRO_JORNADA` | 20 (no 133 -- estimación muy alejada de la real, ver hallazgo abajo) | **18** | 3 | 0 | 1 |

**13 SIN SEÑAL de `AUTONOMO`** (`skip_light_ocr_engines` activo, Cloud Vision
agotado sin resolver tipo ni fecha nueva -- conservan la fecha que ya
tenían de la ingesta normal, no quedan sin fecha en absoluto):
```
27494  ALVAREZ_DIAZ_ADOLFO_AUTONOMO_20121031.pdf
27509  ALVAREZ_DIAZ_ADOLFO_AUTONOMO_20140829_1.pdf
27570  ALVAREZ_DIAZ_ADOLFO_AUTONOMO_20170531.pdf
27592  ALVAREZ_DIAZ_ADOLFO_AUTONOMO_20190102.pdf
27612  ALVAREZ_DIAZ_ADOLFO_AUTONOMO_20190430.pdf
27613  ALVAREZ_DIAZ_ADOLFO_AUTONOMO_20190830.pdf
27615  ALVAREZ_DIAZ_ADOLFO_AUTONOMO_20190228.pdf
27621  ALVAREZ_DIAZ_ADOLFO_AUTONOMO_20191231.pdf
27646  ALVAREZ_DIAZ_ADOLFO_AUTONOMO_20201130.pdf
27894  ALVAREZ_DIAZ_ALBERTO_JAVIER_AUTONOMO_20130930.pdf
27954  ALVAREZ_DIAZ_ALEJANDRO_SERGIO_AUTONOMO_20130930.pdf
27958  ALVAREZ_DIAZ_ALEJANDRO_SERGIO_AUTONOMO_20160801.pdf
28016  ALVAREZ_DIAZ_JOSE_LUIS_AUTONOMO_20150730.pdf
```

**`MOD_145` (S106, script original -- Tesseract sí resuelve bien este
tipo, sin necesidad de `skip_light_ocr_engines`), 4 AMBIGUOS:**
```
28459  BANDERA_DIAZ_YOLANDA_MARINA_MOD_145_20130101.pdf
28548  MACIAS_LUNA_ROCIO_MOD_145_20130101_1.pdf
37471  RUIZ_PORTILLO_MANUEL_MOD_145_19780827.pdf
37798  MENA_RUIZ_DAVID_MOD_145_19750101.pdf
```

**7 SIN SEÑAL:**
```
27784  ALVAREZ_DIAZ_ADOLFO_MOD_145_20160718.pdf
28278  GRANA_ALVAREZ_PALOMA_MOD_145_20180731.pdf
35951  GUTIERREZ_MATEO_CRISTHIAN_MOD_145_20250423.pdf
37447  ROSA_SANCHEZ_FRANCISCO_JOSE_MOD_145_20260622.pdf
38014  VARGAS_MORA_JOSE_ANTONIO_MOD_145_20260605.pdf
38172  ZAVALA_MANZANO_FRANCISCO_DE_P_MOD_145_20130101.pdf
40020  CARVAJAL_GONZALEZ_FRANCISCO_MOD_145_20110101.pdf
```

**`REGISTRO_JORNADA` (mismo día, sesión S106 continuada -- se intentó
por error abrir S107 con PISA/PAH sin haber cerrado S106 con PCS,
anulado por Miguel Ángel al momento, sigue siendo S106). HALLAZGO
FUERTE, el más marcado de todo H35 hasta
ahora: de los 20 candidatos reales de toda la empresa, 18 (el 90%)
NO eran `REGISTRO_JORNADA` -- eran nóminas archivadas bajo el tipo
equivocado. Solo 1 de los 20 era un `REGISTRO_JORNADA` genuino.**
Todos del mismo trabajador (Álvarez Díaz Adolfo) -- igual que pasó
con la muestra de `AUTONOMO` en S106, así que si aparece otro
trabajador con documentos de este tipo en el futuro, confirmar que
el patrón se sostiene antes de asumirlo. La fecha (`issue_date`) ya
la traían todos de la ingesta normal (coincide con la fecha del
propio nombre de archivo) -- esta campaña solo necesitaba corregir
el tipo, no la fecha; solo 2 fechas las puso Cloud Vision de nuevo
en esta pasada.

**18 RETIPADOS A `NOMINA`:**
```
40595  ALVAREZ_DIAZ_ADOLFO_REGISTRO_JORNADA_20230401.pdf
40617  ALVAREZ_DIAZ_ADOLFO_REGISTRO_JORNADA_20230101.pdf
40748  ALVAREZ_DIAZ_ADOLFO_REGISTRO_JORNADA_20240430.pdf
40749  ALVAREZ_DIAZ_ADOLFO_REGISTRO_JORNADA_20240430_1.pdf
40750  ALVAREZ_DIAZ_ADOLFO_REGISTRO_JORNADA_20240430_2.pdf
40751  ALVAREZ_DIAZ_ADOLFO_REGISTRO_JORNADA_20240430_3.pdf
40752  ALVAREZ_DIAZ_ADOLFO_REGISTRO_JORNADA_20240430_4.pdf
40755  ALVAREZ_DIAZ_ADOLFO_REGISTRO_JORNADA_20240430_5.pdf
40756  ALVAREZ_DIAZ_ADOLFO_REGISTRO_JORNADA_20240430_6.pdf
40757  ALVAREZ_DIAZ_ADOLFO_REGISTRO_JORNADA_20240430_7.pdf
40758  ALVAREZ_DIAZ_ADOLFO_REGISTRO_JORNADA_20240430_8.pdf
40759  ALVAREZ_DIAZ_ADOLFO_REGISTRO_JORNADA_20240131.pdf
40760  ALVAREZ_DIAZ_ADOLFO_REGISTRO_JORNADA_20240430_9.pdf
40770  ALVAREZ_DIAZ_ADOLFO_REGISTRO_JORNADA_20240731.pdf
40772  ALVAREZ_DIAZ_ADOLFO_REGISTRO_JORNADA_20240801.pdf
40799  ALVAREZ_DIAZ_ADOLFO_REGISTRO_JORNADA_20241130.pdf
40806  ALVAREZ_DIAZ_ADOLFO_REGISTRO_JORNADA_20241031.pdf (fecha nueva de Cloud Vision: issue_date=2024-10-31)
40808  ALVAREZ_DIAZ_ADOLFO_REGISTRO_JORNADA_20241031_1.pdf (fecha nueva de Cloud Vision: issue_date=2024-10-31)
```

**1 SIN SEÑAL (conserva el tipo `REGISTRO_JORNADA` sin cambiar, sin
fecha nueva -- queda para revisión manual):**
```
40764  ALVAREZ_DIAZ_ADOLFO_REGISTRO_JORNADA_20240831.pdf
```

**1 CONFIRMADO genuino como `REGISTRO_JORNADA`:**
```
40813  ALVAREZ_DIAZ_ADOLFO_REGISTRO_JORNADA_20240930.pdf (issue_date=2024-09-30)
```


---

## COMPLETADAS EN S107

**Resumen:** sesión muy larga dedicada a cerrar por completo el punto
1 de H35 (`CSS`/`VACACIONES`/`NOMINA`), ejecutar de verdad el punto 2
(barrido de otra persona sobre los 13 tipos), y -- al comprobar si lo
ya dado por "cerrado" en S105 lo estaba de verdad -- descubrir que
`BAJA_PERSONAL`/`CONTRATO` tenían 108 documentos reales nunca resueltos
(solo contados, nunca ejecutados) y que `ALTA` ni siquiera tenía su
lista de IDs comiteada. Ambos quedaron cerrados al 100% en esta misma
sesión. De paso: 2 bugs reales de fondo corregidos (diccionario de
`RECONOCIMIENTO_MEDICO` incompleto, extracción de fecha de `IDC`
usando el campo equivocado), un pase de control real de vigencia
(97→12 grupos con más de un documento "vigente" a la vez), un campo
nuevo de catálogo (`is_cumulative`), y una pieza de infraestructura
nueva (consultas SQL de solo lectura por GitHub Actions, sin pasar ya
por Comando S).

**Punto 1 de H35 -- CERRADO POR COMPLETO:**

| Tipo | Total real | Retipados | Fecha corregida |
|---|---|---|---|
| `CSS` | 89 | 0 | 89 (`skip_light_ocr_engines`, mismo patrón que `AUTONOMO`) |
| `VACACIONES` | 36 | 0 | 1 manual (3 fechas en conflicto en el propio documento, se usó la de inicio) |
| `NOMINA` | 85 | 1 (`NOMINA -> CARNET_GRUISTA`, pk real de carnet de gruista archivado como nómina) | 0 pendientes |

**Punto 2 de H35 -- barrido sistemático de otra persona, ejecutado por
primera vez de verdad (nunca se había hecho, solo 2 casos por
inspección manual puntual en S104/S105):** 1.998 documentos revisados
(`_person_name_missing()` contra `ocr_text` cacheado de los 12 tipos
personales de los 13 auditados -- `PAGO_CORRIENTE` excluido, dominio
`CompanyWorksite`). 86 candidatos iniciales →

- **4 casos reales de otra persona**, resueltos:
  - `pk=31985` (Gálvez Sibaja, no existe en el sistema) → papelera.
  - `pk=32837` ("Ana Requena Soler", el segundo caso de S104 nunca
    ejecutado) → papelera.
  - `pk=28491` (Parra Pizano, Pablo, inactivo) → papelera (mismo
    criterio que documentos de inactivos: no se reorganizan).
  - `pk=28650` (Berenguer Gómez, Alejandro, activo) → movido a su
    ficha real + renombrado canónico.
- **48 `MOD_145`** de la importación masiva `20130101`: falso positivo
  sistemático, campo "Apellidos y Nombre" en blanco en el propio
  formulario (verificado con 2 muestras completas, `pk=28038`/`30090`).
- **3 documentos de dominio equivocado** (empresa/vehículo, no
  personal): `pk=28276` (ficha técnica SEAT León, matrícula `1583JXX`),
  `pk=26847` (póliza RC de la empresa), más el ya conocido `pk=28245`
  del punto 3 -- **documentados como deuda técnica en
  `ENTERPRISEBOT_MASTER_DOCUMENT.md` sección 4.21** (turismos de
  empresa sin ficha en `fleet.MachineAsset`), decisión explícita de
  Miguel Ángel de dejarlo fuera del alcance de H35.
- **34 falsos positivos individuales** verificados uno a uno (DNI
  propio en cita previa, boilerplate de administrador de empresa,
  relato propio de accidente, plantillas en blanco, facturas de
  Correos...).
- **44 sin coincidencia exacta contra ninguna persona real** -- quedan
  como pendiente real, ver Hoja de Ruta (nunca se leyeron
  documento a documento, solo se descartó el ruido de apellidos
  cortos/comunes).

**Punto 3 de H35 (`pk=28245`, vehículo):** resuelto como deuda técnica
documentada (sección 4.21 del documento maestro), no como movimiento
de archivo -- criterio explícito de Miguel Ángel: no inventar un
`MachineAsset`/convención de carpeta para turismos sin decidirlo antes
con calma.

**Hallazgo real -- lo dado por "cerrado" en S105 no lo estaba:**
Miguel Ángel señaló explícitamente la contradicción de dar capítulos
por cerrados con documentos reales sin resolver. Verificado y
corregido en la misma sesión:

- **`BAJA_PERSONAL` (98 pendientes reales de S105, nunca ejecutados,
  solo contados) → CERRADO AL 100%.** 13 ambiguos retipados por
  contenido real (`CONTRATO`×4, `IDC`×5, `TARJETA_CUALIF_CONDUCTOR`×1,
  `ALTA`×2, `CARNET_GRUISTA`×1). De los 85 sin señal: 66
  retipados/corregidos con motivo real (`RECONOCIMIENTO_MEDICO`,
  `CURSO`, `FORMACION_PRL_GENERICA`, `ENTREGA_INFORMACION`,
  `FORMACION`, `TACOGRAFO`, `CARNET_CONDUCIR`, `COMUNICACION_CONTRATO`,
  `CERTIF_DISCAPACIDAD`, `CLAUSULA_PROTECCION_DATOS`, `DNI`,
  `CARNET_GRUISTA`, `CERTIFICADO_BANCARIO`, `CAMBIO_IRPF`,
  `AUTORIZACION_TEMPORAL_CONDUCIR`, `CARTA_BAJA_VOLUNTARIA`,
  `DOC_MUTUA`, `INVESTIGACION_ACCIDENTE`), 5 confirmados sin tipo de
  personal real (boletín de notas, demanda de desempleo SAE,
  localizador de Correos, transferencia bancaria, contrato bancario
  Cajamar -- contenido legítimo, ajeno a RRHH), y **2 exigieron un
  tipo de catálogo nuevo** (`COMUNICACION_INSPECCION_TRABAJO`,
  migración `0092`... nota: la migración real de este alta fue la
  `0091`, ver más abajo -- comunicación real de la Inspección de
  Trabajo por fraude en contratación temporal, `pk=28255`/`28256`).
- **`CONTRATO` (10 pendientes reales de S105) → CERRADO AL 100%.** Los
  6 "ambiguos" eran falso positivo sistemático: la frase suelta
  `INCAPACIDAD TEMPORAL` (señal de `PARTE_BAJA_MEDICA`) aparecía en
  una cláusula boilerplate estándar de cualquier contrato Modelo
  PE-177A -- retirada del diccionario (`personal_content_classification.py`).
  Los 4 sin señal: 2 `COMUNICACION_CONTRATO`, 1
  `SOLICITUD_ADMINISTRATIVA`, 1 con extensión de archivo rota
  (`.ordinario firmado-signe` en vez de `.pdf`) que nunca se pudo leer
  por OCR -- corregida, tipo ya era correcto.
- **`ALTA` (S105 solo dejó un recuento en tabla, "6 ambiguos, 7 sin
  señal" -- NUNCA se comitió la lista de IDs).** Mismo fallo que se
  está corrigiendo en toda esta sesión, cometido por una sesión
  anterior. No se pudo cerrar por no existir la lista real -- **queda
  en la Hoja de Ruta de esta sesión como primera tarea, con la lista
  regenerada desde cero contra el diccionario actual** (ver más abajo,
  ya no aplica -- ver nota).
- **`IDC` (S105: "3 ambiguos", sin lista de IDs) → CERRADO AL 100%,**
  y de paso un **bug real de fondo corregido**: `classify_dates_in_text()`
  usaba el patrón `PERIODO...DESDE...(fecha)` (máxima prioridad, S78,
  correcto para `CONTRATO`) también para `IDC`, donde ese campo es el
  inicio de la relación laboral -- estable entre reemisiones del mismo
  informe, nunca la fecha real de la emisión concreta. Corregido con
  detección del encabezado real de IDC + extracción de la fecha real
  del bloque "REFERENCIA/FECHA/HORA". Reclasificación completa contra
  el histórico: **143 fechas corregidas, 19 documentos duplicados
  literales (misma REFERENCIA/HUELLA) enviados a papelera.**
- **`RECONOCIMIENTO_MEDICO`** (S105: "21 sin señal", sin lista de
  IDs): el diccionario le faltaba el formato real más usado de toda la
  plataforma (certificados "Grupo MPE...CERTIFICA...ha sido
  sometido...a reconocimiento médico [periódico/inicial]") --
  añadido. Reclasificación fresca: de 341 "sin señal" reales (la
  cifra real de activos con este tipo, muy por encima de la
  estimación de S105) bajó a **25 reales, con lista de IDs
  comiteada más abajo -- pendiente real, primera tarea de la
  siguiente sesión.**
- **`INVESTIGACION_ACCIDENTE`** (S105: "34 sin señal", sin lista de
  IDs): reclasificación fresca = **72 reales** (recuento real, muy
  por encima de la estimación de S105), con lista de IDs comiteada
  más abajo -- **pendiente real, segunda tarea de la siguiente
  sesión.**

**Pase de control de vigencia (petición explícita de Miguel Ángel:
"un trabajador no puede tener dos DNIs vigentes, dos reconocimientos
médicos vigentes, etc."):** `evaluate_substitution()`/`is_current()`
(`document_management/vigencia_service.py`) **nunca se dispara
automáticamente** -- solo desde el flujo de subida real
(`subject_upload_service.py`) y un par de vistas del panel, nunca
desde una escritura directa por ORM (todo lo que ha hecho este hito,
sesión tras sesión, desde S104). Resultado real, con el management
command ya existente `backfill_obsolete_duplicates` (H30, S48):

1. Campo nuevo `DocumentTypeCatalog.is_cumulative` (migración `0092`)
   -- distingue tipos "de identidad" (un único vigente por persona:
   `DNI`, `CONTRATO`, `RECONOCIMIENTO_MEDICO`...) de tipos "de evento
   repetible" (`FORMACION`, `ENTREGA_INFORMACION`, `EPIS`... varios
   reales y vigentes a la vez, nunca se sustituyen entre sí). Sembrado
   `True` en 21 códigos reales de la familia `PRL_FORMACION` +
   `ENTREGA_DOCUMENTACION_VARIA`/`ENTREGA_MOVIL`. Reutilizable también
   para las subplantillas de dosier de H31 (decisión explícita de
   Miguel Ángel).
2. `backfill_obsolete_duplicates` actualizado para excluir
   `is_cumulative=True` (nunca agrupar solo por tipo+persona sin
   distinguir curso/evento concreto).
3. Ejecutado con `--apply`: 197→154 grupos tras excluir acumulables,
   155 documentos marcados obsoletos. Tras el fix de fechas de `IDC`
   (arriba), relanzado: 68 grupos, 14 documentos más.
4. **Quedan 12 grupos reales (no acumulables) con más de un
   documento "vigente" a la vez** -- causa real identificada, no
   corregida todavía: `is_current()` (`vigencia_service.py`) compara
   cada documento con fecha de caducidad **solo contra hoy, nunca
   contra sus hermanos** -- dos documentos del mismo tipo con
   caducidades distintas (o idénticas, caso `CARNET_CONDUCIR` de
   Barbero Cuenca, `pk=34682`/`34714`, ambos `2034-01-24`) pueden
   quedar ambos vigentes sin que ninguno gane. Es lógica **core**
   usada en toda la plataforma (máquinas incluidas) -- decisión
   explícita de Miguel Ángel de NO tocarla en esta sesión, dejarla
   para la siguiente con la cabeza despejada. Lista de los 12 grupos
   comiteada más abajo.

**Infraestructura nueva -- consultas SQL de solo lectura sin Comando
S:** `.github/workflows/db_query.yml` + secrets `PA_DB_READONLY_SSH_PRIVATE_KEY`/
`PA_DB_ADMIN_PASSWORD` + skill `com-mysql` sección 0bis (nueva) +
`SESSION_VARIABLES.md` (sección de máxima visibilidad, principio del
archivo). Verificado de punta a punta con una consulta real
(`SELECT COUNT(*)` sobre `DocumentTypeCatalog`, resultado real: 152).
PythonAnywhere no permite `CREATE USER` en ningún plan (confirmado
contra su documentación oficial) -- el blindaje real es
`SET SESSION TRANSACTION READ ONLY;` en la propia sesión MySQL
efímera del workflow, no un usuario dedicado.

**Reglas de sesión nuevas, documentadas en la skill `com-standards`
del modelo (persisten entre sesiones, no solo en este anexo):**
sección `0quinquies` (hoja de ruta numerada → se empieza siempre por
el punto 1, nunca se pregunta por dónde) y una nueva regla de "cerrado
significa cero pendientes reales, nunca 'cerrado con lista de
pendientes'" (origen explícito de esta misma sesión, tras la queja
formal de Miguel Ángel sobre capítulos dados por cerrados sin estarlo).
También: `SESSION_VARIABLES.md` ampliado con la convención de fecha de
caducidad en nombre de archivo para `RECONOCIMIENTO_MEDICO`/tipos con
vigencia anual (emisión + 1 año, nunca señal de mala clasificación por
sí sola).

**Migraciones de esquema reales de esta sesión:** `0091` (siembra
`COMUNICACION_INSPECCION_TRABAJO`), `0092` (campo nuevo
`is_cumulative` + siembra de 21 códigos). Ambas desplegadas
automáticamente vía `deploy.yml`, sin incidencia.

**IDs reales pendientes -- `RECONOCIMIENTO_MEDICO` (25, tras ampliar
el diccionario, activos, verificado S107):**
```
24883 24884 28456 28937 33934 35241 35369 35686 37408 40898
40914 40953 42752 42756 42765 42774 42779 42780 42782 42783
42787 42789 42791 42793 42794
```

**IDs reales pendientes -- `INVESTIGACION_ACCIDENTE` (72, activos,
verificado S107 -- `26847` YA documentado aparte en la deuda técnica
4.21 del documento maestro, empresa no persona, excluir de este
recuento personal):**
```
26337 26342 26345 26352 26353 26355 26422 26433 26434 26436
26514 26515 26518 26523 26524 26525 26526 26527 26538 26539
26544 26546 26549 26551 26565 26566 26567 26568 26577 26595
26598 26600 26714 26749 26750 26751 26834 26845 26846 26847
26848 26849 26851 26976 26978 26980 26982 26990 27008 27009
27019 27031 27032 27037 27038 27039 27040 27047 27048 27049
27050 27068 27078 27082 27087 27103 27154 27158 27169 27201
35788 37342
```

**IDs reales pendientes -- barrido de otra persona, punto 2 (44, sin
coincidencia exacta contra ninguna persona real, nunca leídos
documento a documento):**
```
28251 28255... (nota: 28255/28256 ya resueltos arriba, no incluir)
```
Nota: la lista exacta de estos 44 vive en la salida de
`EnterpriseBot_026_GET.txt`/`EnterpriseBot_027_GET.txt`/`028` de esta
sesión (no comiteada literal aquí por espacio) -- **primera acción de
la tarea correspondiente en la Hoja de Ruta es regenerar esta lista
con una consulta fresca** (mismo criterio que ya obligó esta sesión a
regenerar `ALTA`/`RECONOCIMIENTO_MEDICO`/`INVESTIGACION_ACCIDENTE):
`_person_name_missing()` con coincidencia exacta (no aproximada) de
apellidos ≥5 letras, sobre los 12 tipos ya auditados, filtrando los 42
ya resueltos/descartados con motivo real de S107.

**Grupos reales con más de un documento vigente a la vez (12,
pendientes del fix de `vigencia_service.py`):**
```
(persona_id=159, CONTRATO, 4 vigentes -- fecha OCR imposible 2068-03-18, revisar visualmente)
(persona_id=4,   CARNET_GRUISTA, 2 vigentes)
(persona_id=6,   CARNET_GRUISTA, 2 vigentes)
(persona_id=40,  TARJETA_CUALIF_CONDUCTOR, 2 vigentes)
(persona_id=154, CARNET_CONDUCIR, 2 vigentes -- pk=34682/34714, misma caducidad exacta 2034-01-24)
(persona_id=155, CARNET_CONDUCIR, 2 vigentes)
(persona_id=165, CONTRATO, 2 vigentes)
(persona_id=168, CONTRATO, 2 vigentes)
(persona_id=174, CARNET_GRUISTA, 2 vigentes)
(persona_id=175, PARTE_BAJA_MEDICA, 2 vigentes)
(persona_id=180, RECONOCIMIENTO_MEDICO, 2 vigentes)
(persona_id=49,  RECONOCIMIENTO_MEDICO, 2 vigentes)
```

---

## Hoja de Ruta para la Sesión Siguiente (S107)

**Sesión dedicada única y exclusivamente a terminar H35 del todo --
decisión explícita de Miguel Ángel: no se abre ningún punto nuevo, no
se deja ninguna deuda técnica más, se resuelve absolutamente todo lo
que quede antes de tocar cualquier otra cosa.** Orden fijo, punto por
punto, sin preguntar por dónde empezar (regla `0quinquies` de
`com-standards`).

**1. `RECONOCIMIENTO_MEDICO` -- cerrar los 25 IDs listados arriba a
0.** Para cada uno: leer `ocr_text` completo (o descargar el PDF si
hace falta, mismo criterio que esta sesión) y decidir con evidencia
real: (a) ya está bien tipado, solo el diccionario no lo confirmaba
-- ampliar `CONTENT_SIGNALS` con la frase real que falte, sin tocar el
documento; (b) es de otra persona real -- mover/papelera, mismo
criterio del punto 2; (c) es ilegible de verdad (OCR roto sin
remedio) -- documentar como tal, tipo ya correcto, sin acción posible.
**Criterio de cierre: reclasificación fresca contra el diccionario ya
actualizado devuelve 0 "sin señal" sobre estos 25 IDs concretos (o
cada uno que siga "sin señal" está documentado explícitamente como
ilegible, con el PDF ya inspeccionado visualmente, nunca por
descartar sin mirar).**

**2. `INVESTIGACION_ACCIDENTE` -- mismo procedimiento exacto que el
punto 1, sobre los 72 IDs listados arriba** (excluyendo `26847`, ya
resuelto como deuda técnica de dominio). Mismo criterio de cierre.

**3. Corregir `is_current()` en `document_management/vigencia_service.py`
para que compare también contra los hermanos (mismo tipo+persona), no
solo contra hoy, cuando el candidato tiene `expiry_date`** -- incluir
desempate real para fechas de caducidad empatadas (mismo criterio ya
usado para "sin fecha ninguna": el más recientemente indexado gana).
Escribir el fix con cuidado real (es lógica core usada en máquinas
también, no solo personal) y verificar contra los 12 grupos ya
identificados arriba antes de darlo por bueno. Tras el fix, relanzar
`backfill_obsolete_duplicates --apply`. **Criterio de cierre: una
consulta de control (mismo patrón usado toda esta sesión, agrupando
por persona+tipo con `is_obsolete=False` y `document_type.is_cumulative=False`)
devuelve 0 filas con más de 1 vigente, tanto en dominio `PersonIdentity`
como `MachineAsset`.**

**4. Corregir la fecha OCR imposible de `pk=35635`/`35637`/`35640`/
`35641` (Gómez García, `CONTRATO`, `issue_date=2068-03-18`, año real
casi seguro `2018` o similar -- revisar visualmente el PDF, no
adivinar) antes de que el fix del punto 3 decida el vigente sobre una
fecha basura.** Criterio de cierre: fecha real corregida tras
inspección visual del documento, confirmada contra el propio texto
("FECHA:...9 de 7... de 20 12" visible en el `ocr_text` ya cacheado,
sugiere `2012`, verificar).

**5. Punto 2 de H35, los 44 "sin coincidencia exacta" -- regenerar la
lista fresca (criterio: `_person_name_missing()` exacto sobre los 12
tipos, excluyendo los 42 ya resueltos con motivo real en S107) y leer
cada uno documento a documento** (texto cacheado primero, PDF/imagen
real si hace falta, mismo criterio de esta sesión). Resolver a mover/
papelera/confirmar-propio-sin-acción, con motivo real anotado por
cada uno. **Criterio de cierre: los 44 (o el recuento real que arroje
la consulta fresca) resueltos con motivo explícito, ninguno queda
"sin mirar".**

**6. Corrección menor de consistencia (opcional, si sobra tiempo tras
los 5 puntos anteriores): `pk=32780` tiene `document_type=IDC` real
pero el nombre de archivo sigue diciendo `BAJA_PERSONAL` (retipado sin
pasar por `apply_personal_canonical_rename`, sesión anterior a S107)
-- aplicar el renombrado canónico.**

**Con los 5 primeros puntos cerrados a 0 (el 6 es opcional), H35
queda cerrado del todo, sin ninguna deuda técnica pendiente relativa
a retipado/refechado/vigencia de personal.** La deuda de turismos sin
ficha en `fleet.MachineAsset` (sección 4.21 del documento maestro)
queda fuera de este hito por decisión explícita de Miguel Ángel -- no
es parte del criterio de cierre de H35.
