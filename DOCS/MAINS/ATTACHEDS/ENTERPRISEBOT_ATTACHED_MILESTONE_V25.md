# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V25.md

# Anexo de Hito V25 — Documentación de Personal
# Proyecto: EnterpriseBot
# Fecha de inicio: 2026-07-16 (S022)

---

## 1. Visión General del Hito

Cada trabajador/chófer de Grupo Álvarez tiene documentación oficial dispersa
(identidad, contractual, carnets y permisos con vigencia, reconocimientos
médicos, cursos de formación, EPIS, entregas de material) hoy repartida en
carpetas locales sin ningún criterio uniforme — la propia carpeta de
ejemplo aportada por Miguel Ángel en S022 contiene una subcarpeta
`OBSOLETOS/` de archivado manual, documentos duplicados por estado de
trámite (firmado/sin firmar) y nombres de archivo con fechas de caducidad
calculadas a mano.

Este hito construye, para documentación de personal, el mismo principio de
**"servidor de archivos"** ya aplicado en H23 para documentación de
centros de gasto: el usuario nunca gestiona carpetas ni rutas — solo dice
qué documentación sube (de qué trabajador, de qué tipo) o qué
documentación necesita descargar, y el sistema se encarga de organizarlo,
clasificarlo y ubicarlo de forma consistente.

**Origen:** carpeta de ejemplo real (chófer, caso real anonimizable)
aportada por Miguel Ángel en S022 durante el diseño de la migración de
Google Drive a Google Cloud Storage (ver `ENTERPRISEBOT_ATTACHED_MILESTONE_V23.md`
sección 5, prioridad 0 de S022).

---

## 2. Decisiones cerradas con Miguel Ángel en S022 (directriz 4.8 — tal cual)

1. **Modularidad:** app y modelo Django propios, separados de
   `machine_documents` (H23), aunque compartan principios de diseño.
   Palabras de Miguel Ángel: "la modularidad ya es importante porque el
   proyecto tiene una dimensión gigantesca. Así que lo mejor es tener
   aplicaciones y modelos separados."
2. **Vigencia:** explícita siempre que el propio documento la indique
   (incluida una regla textual, como el "la validez del resultado de su
   examen de salud es ANUAL" encontrado en el reconocimiento médico de
   ejemplo — la fecha real de caducidad se calcula desde la fecha del
   examen usando esa regla, en vez de fiarse del nombre del archivo).
   Calculada solo cuando no exista ninguna referencia explícita en el
   documento. Palabras de Miguel Ángel: "creo que lo suyo es que sea de
   forma explícita siempre que exista y que se calcule cuando no haya
   otra opción."
3. **Persistencia:** Google Cloud Storage, bucket dedicado
   `enterprisebot-alvarez-personnel-documents` (confirmado como parte del
   esquema de 4 buckets de la migración GCS — ver anexo H23 sección 5).
   Bucket privado + URL firmada bajo demanda (mismo criterio que el resto
   de buckets de la migración — nunca acceso público directo, todo pasa
   por autenticación del panel).

---

## 3. Análisis de la carpeta de ejemplo (S022)

41 elementos (39 archivos + `OBSOLETOS/` con 2 archivos archivados a
mano). Patrones detectados, verificados abriendo 3 documentos
representativos:

- **Vigencia en el nombre de archivo** (patrón manual actual a
  sustituir): `DNI ... 20-06-2034`, `CARNET DE GRUAS A ... 05-07-28`,
  `TARJETA DEL CONDUCTOR ... 27-01-2028`, `PERMISO DE CIRCULACION ...
  24-01-2034`, `TARJETA DE CUALIFICACION DEL CONDUCTOR ... 14-12-2027`.
- **Archivado manual ya existente:** subcarpeta `OBSOLETOS/` — confirma
  que el campo de archivado ya diseñado en H23 (sección "Decisiones
  cerradas en S021") aplica igual aquí, sin rediseño.
- **Duplicados por estado de trámite:** mismo documento en versión sin
  firmar y firmada conviviendo (`FORM 60H...` / `FORM 60H...FIRMADO`,
  `FORM 6H APARATOS ELEVADORES...` / `...FIRMADO`, `FORM 6H GRUA
  AUTOCARGANTE...` / `...FIRMADO`).
- **Renovación periódica con vigencia calculada, no leída:** el
  Reconocimiento Médico de ejemplo (`RM ... 15-09-2026.pdf`) contiene la
  fecha real del examen (15/09/2025) y el texto "la validez del
  resultado de su examen de salud es ANUAL" — el nombre del archivo
  (`15-09-2026`) es la caducidad ya calculada a mano por quien lo
  guardó. Confirma la decisión de la sección 2.2 de este anexo.
- **Cursos de formación (categoría mayoritaria en volumen):** ~15
  certificados de curso distintos, cada uno con código de acción
  formativa, formador, entidad formadora, fecha de inicio/fin y
  localidad — campos que no aplican a otros tipos de documento.
  Ejemplo verificado (`FORM 6H ALTURA...`): capa de texto perfecta vía
  `pdftotext`, sin necesidad de Gemini Vision para extracción (aunque sí
  para clasificación por contenido, igual que H23).
- **Documentos escaneados sin capa de texto:** verificado con
  `pdffonts` sobre el carnet de grúas — tabla de fuentes vacía, PDF
  puramente rasterizado. Estos sí requieren Gemini Vision para
  extracción, igual que el flujo ya construido en H23.
- **Categorías identificadas de partida** (a confirmar/ampliar con
  Miguel Ángel, sin lista cerrada — mismo principio de H23 de dejar que
  Gemini proponga categorías nuevas): identidad (DNI, tarjeta sanitaria),
  contractual (contrato, alta, MOD 145), permisos/carnets con vigencia
  (carnet de grúas, tarjeta del conductor, tarjeta de cualificación,
  permiso de circulación), reconocimientos médicos, formación/cursos,
  EPIS y entregas de material/información.

---

## 4. Preguntas Abiertas — Resolver al Retomar Este Hito

1. **Nombre de la app Django** — no decidido todavía en S022 (sesión
   centrada en priorizar primero la migración GCS). Candidato de
   partida: `personnel_documents` (paralelo a `machine_documents`), a
   confirmar con Miguel Ángel antes de crear el modelo definitivo.
2. **Modelo de datos exacto** — mismo diseño híbrido que H23 (columnas
   propias para campos repetidos + `extra_data` JSON para lo
   impredecible)? Candidatos de columnas propias vistos en el análisis:
   `expiry_date`, `issue_date`, `document_number`, `issuing_entity`,
   más el caso especial de vigencia calculada (regla textual, no fecha
   directa) para reconocimientos médicos — decidir mecanismo concreto
   (¿campo `validity_period_days`/`validity_rule` + cálculo en
   `save()`/manager, o cómputo al vuelo en la vista?).
3. **Lista de categorías (`document_type`)** — ¿cerrada con las
   candidatas de la sección 3, o libre igual que H23 (Gemini puede
   proponer categorías nuevas)?
4. **Rol(es) con acceso** a documentación de personal — dato sensible
   (identidad, salud), probablemente más restringido que "Documentación
   Centros de Gasto" (candidato natural: ADMIN/SUPERVISOR únicamente,
   nunca WORKSHOP/DRIVER ni siquiera para su propia documentación, salvo
   que Miguel Ángel diga lo contrario) — confirmar explícitamente, sin
   asumir.
5. **Relación con `CompanyUser`** — FK directa a `ivr_config.CompanyUser`
   (mismo patrón denormalizado que `TaskPhoto`/`MachineDocument`), a
   confirmar.
6. **Vista de subida/listado** — ¿integrada en el panel de
   Administración existente (nueva entrada de sidebar, mismo patrón que
   H23), o vinculada también desde la ficha del propio trabajador si
   existe una vista de perfil/administración de personal? No localizada
   todavía una vista de "ficha de trabajador" en el código — verificar
   al empezar.
7. **Verificación online de la API de Gemini Vision** (directriz
   4.4/SINE QUA NON) — ya hecha en S017 para H23 (PDF nativo hasta 1000
   páginas/50MB sin rasterizar); confirmar si sigue vigente al retomar
   este hito, dado el ritmo de cambios de la API.

---

## 5. Hoja de Ruta para la Siguiente Sesión que Retome Este Hito

**Bloqueado por la migración GCS de H23 (prioridad 0 de S022)** — el
bucket `enterprisebot-alvarez-personnel-documents` se crea como parte de
esa migración, pero el modelo/servicio de este hito no se construye hasta
que se retome explícitamente.

1. Resolver las 7 preguntas abiertas de la sección 4 con Miguel Ángel.
2. Crear app `personnel_documents` (o el nombre confirmado) + modelo
   inicial + migración.
3. Generalizar/reutilizar `document_classification_service.py` (H23) o
   crear equivalente propio, según directriz de modularidad ya cerrada.
4. Vista de subida + listado, con el mismo principio de "servidor de
   archivos" (sección 1) — el usuario nunca ve carpetas ni rutas.

---

## 6. Registro de Sesiones

| Sesión | Fecha | Trabajo realizado |
|---|---|---|
| S022 | 2026-07-16 | Hito creado a partir de una funcionalidad anotada durante el diseño de la migración GCS de H23. Miguel Ángel aportó una carpeta de ejemplo real (chófer) — analizada íntegramente (listado + inspección de 3 documentos representativos: carnet de grúas escaneado, certificado de curso con capa de texto, reconocimiento médico con capa de texto). Confirmadas 3 decisiones de diseño (modularidad, vigencia explícita/calculada, bucket GCS dedicado). Sin código todavía — hito registrado como PAUSADO, bloqueado por la prioridad 0 de H23 (migración GCS). Ver sección 4 (preguntas abiertas) y sección 5 (hoja de ruta) para el punto de partida de la siguiente sesión. |
