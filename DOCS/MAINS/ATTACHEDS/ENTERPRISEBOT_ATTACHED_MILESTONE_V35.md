# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V35.md

## ⚠️ DATO CRÍTICO DE CONTINUIDAD -- LEER ANTES DE CUALQUIER OTRA COSA

**Registro real afectado:** `PersonIdentity`, DNI `74633524L`, Miguel
Ángel Muñoz Cara (id original 249 -- ya no existe, ver más abajo).

**Motivo:** durante esta sesión se detectó un fallo real de ingesta
en la propia ficha de Miguel Ángel -- 3 de sus 4 documentos indexados
como `CONTRATO` eran en realidad **nóminas** mal clasificadas al
subirlas (mismo `blob_name` repetido en varias filas de índice, un
síntoma real de que la re-subida del mismo archivo generaba una fila
de índice nueva en vez de actualizar la existente). Para reproducir el
fallo y probar la ingesta de cero, se hizo lo siguiente, en este
orden: (1) los 18 documentos de su ficha se enviaron a papelera
(`trash_dossier_entry`, recuperable); (2) a petición explícita
posterior de Miguel Ángel ("borra mi ficha completa"), se hizo un
backup completo (`serializers.serialize`, `PersonIdentity` + sus 18
`DocumentIndexEntry`) y se borró de verdad la fila `PersonIdentity`
(`.delete()`, sin papelera -- no existe mecanismo de papelera para
este modelo); (3) Miguel Ángel volvió a subir toda su documentación
real desde cero, recreando su ficha por el flujo normal de alta
guiada.

**Estado del backup:** Miguel Ángel conserva su propia copia del JSON
(confirmado explícitamente, S105) -- **no se comiteó al repositorio**,
decisión suya explícita ("Tengo el J[SON]... déjalo"). No hace falta
ninguna acción de restauración -- su ficha ya existe de nuevo, recreada
por la re-subida real.

**Primera tarea obligatoria de la sesión siguiente, con criterio de
cierre objetivo:** comprobar si el fallo real que motivó todo esto se
reprodujo en la ficha recreada -- consultar los documentos actuales de
Miguel Ángel (buscar `PersonIdentity` por DNI `74633524L`) y revisar
si alguno de tipo `CONTRATO` es, por contenido real, una nómina. Cierra
a **0** documentos `CONTRATO` cuyo contenido real no sea un contrato
-- si aparece alguno, diagnosticar `personal_intake_service.py`/el
flujo de subida real (mismo síntoma ya visto: `blob_name` repetido
entre filas de índice distintas) antes de dar el fallo por corregido.

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

---

## Hoja de Ruta para la Sesión Siguiente (S106)

**0. Verificar el resultado de la re-ingesta de Miguel Ángel (ver el
"DATO CRÍTICO DE CONTINUIDAD" al principio de este anexo) -- PRIMERA
tarea, antes de cualquier otro punto.** ~~Buscar `PersonIdentity` por
DNI `74633524L`, listar sus documentos `CONTRATO` actuales y
comprobar, por contenido real (`ocr_text` o descarga directa si no
está cacheado), si alguno es en realidad una nómina.~~ **CERRADO EN
S106, confirmación directa de Miguel Ángel: su ficha está bien.**
Causa real del fallo original, para cuando se retome la interfaz/
ingesta (H31): verificación ausente de qué documento se sube, y
borrado indebido del blob al actualizar un documento (debería quedar
como obsoleto en el historial, nunca borrarse).

**1. Auditar con `--retype` los 6 tipos de volumen alto restantes de
las familias `LABORAL`/`SALUD_BAJAS_PERSONA`, mismo procedimiento
exacto que el resto de esta sesión** (dry-run de 10 primero, revisar
el patrón, campaña completa -- ver nota de shards más abajo):
~~`AUTONOMO` (189)~~ **CERRADO EN S106.** ~~`MOD_145` (161)~~
**CERRADO EN S106 (125 reales, ver "COMPLETADAS EN S106" arriba).**
Quedan: `REGISTRO_JORNADA` (133), `CSS` (89), `VACACIONES` (74),
`NOMINA` (73) -- **estimaciones de la hoja de ruta original, sin
auditar: el recuento real puede diferir, como ya pasó con `MOD_145`
(161 estimados, 125 reales).** Para cada uno, registrar en este
anexo el mismo desglose que ya tienen `BAJA_PERSONAL`/`ALTA`/
`CONTRATO`/`IDC`/`RECONOCIMIENTO_MEDICO`/`INVESTIGACION_ACCIDENTE`/
`AUTONOMO`/`MOD_145` (retipados/fecha corregida/ambiguos con IDs/sin
señal con IDs). **Nota de shards (S106): si el dry-run de un tipo
muestra el mismo patrón de `AUTONOMO` (100% de escalado hasta Cloud
Vision), activar `skip_light_ocr_engines` para ese tipo y usar
`extract_personal_dates_bulk_fast.py` -- un único proceso en
`h28-ocr-batch-1` puede bastar sin necesidad de congelar imagen ni
crear VMs efímeras (verificado real: 189 documentos en ~7 minutos).
Si el patrón es mixto o Tesseract resuelve bien (como `MOD_145`),
usar el script original sin el flag.** **Criterio de cierre de este
punto: los 6 tipos con su desglose comiteado en este anexo, cada uno
con las listas de IDs pendientes reales (nunca solo el recuento).**

**2. Ejecutar el criterio de remediación del punto 0 original de
S105** (documento de otra persona real archivado bajo una ficha que
no es la suya -- buscar sistemáticamente con `_person_name_missing()`
sobre el `ocr_text` ya cacheado de todos los tipos auditados hasta
ahora, no solo los 2 casos ya encontrados por inspección manual
puntual en S105: `pk=41145`/`42128`, EPIS de Jorge Milheiro Felicio y
Francisco Gómez Rivero archivados bajo Jorge Ramírez García). Si la
persona nombrada existe ya como `PersonIdentity` (activa o inactiva,
cualquier empresa), mover el documento a su ficha real; si no existe,
papelera (`trash_dossier_entry`). **Criterio de cierre: barrido
sistemático ejecutado sobre los 6+7=13 tipos ya auditados a fecha de
S105/S106, con el recuento real de cuántos documentos de otra persona
se encontraron y qué se hizo con cada uno, comiteado en este anexo.**

**3. Documento del vehículo mal archivado (`pk=28245`, ficha ITV de
un Volkswagen matrícula 8534-BGX, archivado bajo Grana Álvarez,
Paloma) -- aplicar el criterio de remediación del punto 2, adaptado:
este no es un documento de OTRA PERSONA, es un documento que no
pertenece al dominio `PersonIdentity` en absoluto.** Buscar primero en
el catálogo real (`DocumentTypeCatalog`, dominio `MACHINE`/`BOTH`) si
ya existe un tipo para fichas ITV de vehículos de empresa (turismos,
no maquinaria pesada); si existe, reubicar el documento a su dominio y
tipo reales con `move_service`. Si no existe ningún tipo/carpeta real
para esto, darlo de alta siguiendo el mismo criterio ya usado en el
resto de altas de tipo de esta plataforma (label, family, domain)
antes de reubicar. **Criterio de cierre: `pk=28245` con
`domain_content_type`/`document_type` reales de vehículo, ya no bajo
la ficha de Grana Álvarez, Paloma.**

**3. Documento del vehículo mal archivado (`pk=28245`, ficha ITV de
un Volkswagen matrícula 8534-BGX, archivado bajo Grana Álvarez,
Paloma) -- aplicar el criterio de remediación del punto 2, adaptado:
este no es un documento de OTRA PERSONA, es un documento que no
pertenece al dominio `PersonIdentity` en absoluto.** Buscar primero en
el catálogo real (`DocumentTypeCatalog`, dominio `MACHINE`/`BOTH`) si
ya existe un tipo para fichas ITV de vehículos de empresa (turismos,
no maquinaria pesada); si existe, reubicar el documento a su dominio y
tipo reales con `move_service`. Si no existe ningún tipo/carpeta real
para esto, darlo de alta siguiendo el mismo criterio ya usado en el
resto de altas de tipo de esta plataforma (label, family, domain)
antes de reubicar. **Criterio de cierre: `pk=28245` con
`domain_content_type`/`document_type` reales de vehículo, ya no bajo
la ficha de Grana Álvarez, Paloma.**
