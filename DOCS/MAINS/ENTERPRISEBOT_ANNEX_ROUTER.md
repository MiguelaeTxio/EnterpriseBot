# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ENTERPRISEBOT_ANNEX_ROUTER.md
# Enrutador de Anexos — Proyecto EnterpriseBot

---

## 1. Función

Este archivo es la **única fuente de verdad** sobre qué hito está
`EN PROGRESO`. `ENTERPRISEBOT_MASTER_DOCUMENT.md` es puramente
descriptivo e invariable (salvo adición de hito nuevo) y **nunca**
menciona estados de hito — esa responsabilidad es exclusiva de este
archivo.

Cumple dos funciones inseparables:

1. **Enrutamiento:** identifica qué anexo leer según el hito EN
   PROGRESO de la tabla de abajo.
2. **Cambio de hito:** al cambiar el hito EN PROGRESO, se edita este
   mismo archivo (mover el marcador) — ver `nfs-enterprisebot-pch`.

---

## 2. Tabla de Enrutamiento

| Hito | Título resumido | Anexo |
|---|---|---|
| H01 | Validación Infraestructura de Voz | `ENTERPRISEBOT_ATTACHED_MILESTONE_V01.md` |
| H02 | Validación Diagnóstico test_live | `ENTERPRISEBOT_ATTACHED_MILESTONE_V02.md` |
| H03 | IVR Conversacional Configurable | `ENTERPRISEBOT_ATTACHED_MILESTONE_V03.md` |
| H04 | Canal WhatsApp — Chatbot | `ENTERPRISEBOT_ATTACHED_MILESTONE_V04.md` |
| H05 | Arquitectura Omnicanal IVR ↔ WhatsApp | `ENTERPRISEBOT_ATTACHED_MILESTONE_V05.md` |
| H06 | Procesador PDF→Excel + BBDD | `ENTERPRISEBOT_ATTACHED_MILESTONE_V06.md` |
| H07 | Partes Diarios de Reparación Digital | `ENTERPRISEBOT_ATTACHED_MILESTONE_V07.md` |
| H08 | Mejoras Procesador PDF→Excel + HTMX | `ENTERPRISEBOT_ATTACHED_MILESTONE_V08.md` |
| H09 | Informes y Analítica Cruzada | `ENTERPRISEBOT_ATTACHED_MILESTONE_V09.md` |
| H10 | Albaranes de Proveedores y Almacén de Repuestos | `ENTERPRISEBOT_ATTACHED_MILESTONE_V10.md` |
| H11 | Albaranes a Clientes | `ENTERPRISEBOT_ATTACHED_MILESTONE_V11.md` |
| H12 | Gestión Centros de Gasto | `ENTERPRISEBOT_ATTACHED_MILESTONE_V12.md` |
| H13 | Salas de Chat IRC por Sección | `ENTERPRISEBOT_ATTACHED_MILESTONE_V13.md` |
| H14 | Tickets de Avería y Órdenes de Reparación | `ENTERPRISEBOT_ATTACHED_MILESTONE_V14.md` |
| H15 | Gestor Árbol de Directorios Power Automate | `ENTERPRISEBOT_ATTACHED_MILESTONE_V15.md` |
| H16 | Motor de Presupuestos ASISTENCIA | `ENTERPRISEBOT_ATTACHED_MILESTONE_V16.md` |
| H17 | Unificación IVR + WhatsApp — Motor de Averías y Log de Conversaciones | `ENTERPRISEBOT_ATTACHED_MILESTONE_V17.md` |
| H18 | Gestión de Mapas y Geolocalización | `ENTERPRISEBOT_ATTACHED_MILESTONE_V18.md` |
| H19 | Mejoras WorkOrderAdminHistoryView | `ENTERPRISEBOT_ATTACHED_MILESTONE_V19.md` |
| **H20** | **Laboratorio de Análisis Unificado** | **`ENTERPRISEBOT_ATTACHED_MILESTONE_V20.md`** |
| H21 | Refactorización Arquitectónica Split views.py | `ENTERPRISEBOT_ATTACHED_MILESTONE_V21.md` |
| H22 | Visor de Historial de Máquinas (Operario) | `ENTERPRISEBOT_ATTACHED_MILESTONE_V22.md` |
| H23 | Documentación de Centros de Gasto | `ENTERPRISEBOT_ATTACHED_MILESTONE_V23.md` |
| H24 | Vacaciones y Calendario | `ENTERPRISEBOT_ATTACHED_MILESTONE_V24.md` |
| H25 | Documentación de Personal | `ENTERPRISEBOT_ATTACHED_MILESTONE_V25.md` |
| H26 | Infraestructura Documental Compartida (Alertas, PDF, Email, Sustitución) | `ENTERPRISEBOT_ATTACHED_MILESTONE_V26.md` |
| H27 | Ingesta de Documentación vía Correo Electrónico | `ENTERPRISEBOT_ATTACHED_MILESTONE_V27.md` |
| H28 | Migración y Reorganización de Documentación Histórica | `ENTERPRISEBOT_ATTACHED_MILESTONE_V28.md` |
| H29 | Explorador de Archivos y Gobierno Documental del Panel sobre GCS | `ENTERPRISEBOT_ATTACHED_MILESTONE_V29.md` |
| H30 | Vinculación Documental Real — Centros de Gasto y Personal | `ENTERPRISEBOT_ATTACHED_MILESTONE_V30.md` |
| H31 | Interfaz de Gestión Documental de Personal — Altas, Bajas, Sustituciones, EPIs y Circulares (título anterior: "Interfaz de Ficha de Personal — EPIs y Notificaciones/Circulares"; ampliado en S99 al fusionar H33) | `ENTERPRISEBOT_ATTACHED_MILESTONE_V31.md` ← EN PROGRESO |
| H32 | Migraciones de Infraestructura (Modelo IA, Python, Registro Android) | `ENTERPRISEBOT_ATTACHED_MILESTONE_V32.md` |
| ~~H33~~ | ~~Subida de Documentación en Tiempo Real desde el Panel~~ — **FUSIONADO EN H31 el 2026-09-10 (S99)**, ver sección 6 | `ENTERPRISEBOT_ATTACHED_MILESTONE_V33.md` (conservado íntegro como archivo histórico) |
| H34 | Modelo Propio de Clasificación de Documentos (entrenamiento) | `ENTERPRISEBOT_ATTACHED_MILESTONE_V34.md` |
| H35 | Retipado y Refechado Masivo de Documentación Histórica de Personal | `ENTERPRISEBOT_ATTACHED_MILESTONE_V35.md` |
| H36 | Retipado de Cursos de Formación (FORMACION genérico → 17 tipos por curso, solo trabajadores activos) | `ENTERPRISEBOT_ATTACHED_MILESTONE_V36.md` |

Todos los anexos viven en `DOCS/MAINS/ATTACHEDS/`.

---

## 3. Resultado Actual

**Hito EN PROGRESO:** H31 — Interfaz de Gestión Documental de Personal
→ `ENTERPRISEBOT_ATTACHED_MILESTONE_V31.md`. Reactivado en S110 tras
cerrar H36 por completo en la misma sesión (PCH de vuelta) -- ver
"COMPLETADAS EN S110 -- H36 CERRADO POR COMPLETO" en el anexo propio
de H36 para el detalle completo. Hoja de ruta de arranque intacta
desde S99: (1) investigar la fecha `2016-04-27` duplicada en
`CONTRATO` de 6 personas, (2) gestión de Miguel Ángel con
Docuten/Viafirma (sin dependencia técnica), (3) enviar un dossier real
con firma y cuerpo editado, confirmado visualmente en Outlook real --
punto pendiente heredado sin avance desde S104, el mismo que motivó el
desvío a H36 en S109.

**Hito CERRADO en S110:** H36 — Retipado de Cursos de Formación →
`ENTERPRISEBOT_ATTACHED_MILESTONE_V36.md`. Sesión larguísima: catálogo
ampliado de 14 a 17 tipos de curso reales, más de 80 señales y 70
reglas `CONTENT_WINS` añadidas contra evidencia real, 3 bugs de intake
corregidos, 2 bugs de búsqueda del panel corregidos, y cierre final
completo (papelera para inactivos y tipos fuera del Excel de Yolanda,
reasignación a empresa de 946 documentos que nunca debieron colgar de
una persona). Punto de partida real 1.268 documentos genéricos;
verificado con consulta real que hoy no queda ninguno de la familia
`PRL_FORMACION` sin persona ni empresa asignada. Sin hoja de ruta
pendiente propia -- ver "COMPLETADAS EN S110" en su propio anexo para
el detalle completo.

**Hito PAUSADO desde S109 (histórico, hasta este cierre):** H36 —
Retipado de Cursos de Formación →
`ENTERPRISEBOT_ATTACHED_MILESTONE_V36.md`. Abierto en S109 (PCH CASO C
desde H31, desvío en la misma sesión): al desdoblar el tipo genérico
`FORMACION` en 14 tipos por curso real (punto 2 de la hoja de ruta de
H31), se confirmó que el histórico real afectado es demasiado grande
para tratarse como un punto más de H31 -- 1.182 documentos de 67
trabajadores ACTIVOS (los 414 documentos de 95 trabajadores inactivos
quedan fuera de alcance a petición explícita de Miguel Ángel, siguen
con el tipo genérico, recuperables desde la papelera si algún día
hicieran falta), de los cuales 840 no tenían OCR cacheado todavía.
Mismo perfil que motivó H35 (536 documentos) en su momento.
**Campaña de 12 shards ejecutada y verificada en la misma sesión
(S109): 352 de los 1.182 retipados con éxito, 830 quedan en
`FORMACION` genérico** (tipo ambiguo, sin nada resoluble, o
formación genérica real sin curso más específico) -- ver
"COMPLETADAS EN S109" en el anexo propio para el detalle completo y
la hoja de ruta de continuación.

**Hito PAUSADO en esta sesión (S109):** H31 — Interfaz de Gestión
Documental de Personal → `ENTERPRISEBOT_ATTACHED_MILESTONE_V31.md`.
En esta sesión se completaron los puntos 1 (grupos de reparto) y 3
(triángulo de alerta con detalle) de su hoja de ruta ampliada, y se
sembró el catálogo de 14 tipos de curso del punto 2 (ver "COMPLETADAS
EN S109" en su propio anexo) -- el retipado real de los documentos
históricos de ese punto 2 es precisamente lo que motiva este PCH a
H36. Hoja de ruta pendiente al reactivar: intacta, sin cambios --
enviar un dossier real desde el panel con firma y cuerpo editado,
confirmado visualmente en Outlook real (heredada sin tocar desde
S104/S108).

**Hito CERRADO en S108:** H35 — Retipado y Refechado Masivo de
Documentación Histórica de Personal → `ENTERPRISEBOT_ATTACHED_MILESTONE_V35.md`.
Los 6 puntos de su hoja de ruta quedaron cerrados a 0 -- ver
"COMPLETADAS EN S108 -- H35 CERRADO POR COMPLETO" en su propio anexo
para el detalle completo (3 migraciones nuevas de catálogo, 2 bugs
reales corregidos en `is_current()`/`backfill_obsolete_duplicates`,
un incidente de infraestructura en `db_query.yml`, y todos los casos
reales de retipado/reubicación/papelera resueltos con decisión
explícita de Miguel Ángel en cada uno). Sin hoja de ruta pendiente
propia.

**Hito EN PROGRESO (histórico, hasta S108):** H35 — Retipado y
Refechado Masivo de Documentación Histórica de Personal →
`ENTERPRISEBOT_ATTACHED_MILESTONE_V35.md`. Abierto en S104 (Caso C)
tras un hallazgo real durante una sesión de H31: investigando por qué
77 activos no tenían `hire_date`, se descubrió primero una fecha de
nacimiento colada como `issue_date` en 135 ficheros (9 tipos
documentales, bug histórico anterior a la protección actual), y
después algo bastante más grave -- `BAJA_PERSONAL` usado como "cajón
de sastre" en la migración histórica: de 536 documentos con ese tipo
en toda la plataforma, apenas ~3% de los que ya se pueden juzgar por
contenido son una baja real. Decisión explícita de Miguel Ángel:
esto es su propio hito, no un punto de H31 -- primero VMs de OCR con
Tesseract, Cloud Vision solo si Tesseract no resuelve.

**Hito PAUSADO en esta sesión (S104):** H31 — Interfaz de Gestión
Documental de Personal → `ENTERPRISEBOT_ATTACHED_MILESTONE_V31.md`.
Los 3 puntos de la hoja de ruta de S104 quedaron cerrados (formato de
operario en export H20, backend completo de envío de dossieres por
email, verificación real de la corrección `is_current()`) -- ver
"COMPLETADAS EN S104" en su propio anexo para el detalle. Pendiente
real al pausar: confirmación visual en Outlook real de un envío de
dossier (único punto heredado, sin hoja de ruta nueva definida más
allá de eso). Se retoma cuando H35 esté cerrado.

**Reorganización de hitos en S99 (2026-09-10)** — ver sección 6 para
el detalle completo y la cita textual de Miguel Ángel que la autoriza:
H33 se fusiona en H31, que se renombra y amplía en consecuencia. El
trabajo real de S99 sobre estructura de carpetas de PERSONAL se
reclasifica como H29, sin mover el marcador `← EN PROGRESO` (Caso A,
desvío de sesión).

**Hitos nuevos abiertos en S94 (PAUSADOS, sin tocar todavía):** H33 —
Subida de Documentación en Tiempo Real desde el Panel, y H34 — Modelo
Propio de Clasificación de Documentos (entrenamiento), este último
con prioridad de atención propia máxima, verbatim de Miguel Ángel:
"vamos a sentar la base de la clasificación de documentos a raíz del
entrenamiento de este modelo [...] no un punto de hoja de ruta dentro
de otro hito." Ninguno de los dos tiene hoja de ruta ejecutable
todavía -- pendientes de sesión de diseño dedicada cada uno. El
marcador `← EN PROGRESO` no se mueve -- apertura de hito nuevo (Caso C
de la sección 5), no cambio de hito.

**Hito reactivado en S93:** H31 — Interfaz de Ficha de Personal: EPIs
y Notificaciones/Circulares → `ENTERPRISEBOT_ATTACHED_MILESTONE_V31.md`.
Reactivado tras confirmar que se cumple la condición real de
reactivación registrada en su propio anexo (sección 5.5): las
familias `LABORAL` + `SALUD_BAJAS_PERSONA` (6.085 documentos, 0% con
`issue_date`/`expiry_date` en el momento de la pausa, S77) quedaron
cubiertas al 100% con el cierre del dominio PERSONAL de H30 en S92.

**Hito CERRADO en S93:** H32 — Migraciones de Infraestructura (Modelo
IA, Python, Registro Android) → `ENTERPRISEBOT_ATTACHED_MILESTONE_V32.md`.
Los tres plazos que motivaron el hito quedaron atendidos: migración
`gemini-2.5-flash` → `gemini-3.5-flash` completa y desplegada, venv de
Python migrado a 3.12 sobre imagen `innit` y verificado en producción
(webapp + 2 tareas Always On + consola), y registro de Google Play
Console reconducido a Android Developer Console (fuera del alcance de
código de este repositorio, seguimiento manual de Miguel Ángel). Sin
hoja de ruta pendiente propia -- si `google.api_core`/PythonAnywhere
o Gemini generan una incidencia real futura, se atenderá como desvío
puntual (Caso A de `com-pch`), no reabriendo el hito completo.

**Hito PAUSADO en esta sesión (S92):** H30 — Vinculación Documental
Real: Centros de Gasto y Personal → `ENTERPRISEBOT_ATTACHED_MILESTONE_V30.md`.
El dominio PERSONAL queda fechado y con dominio asignado al 100% para
los trabajadores activos (auditoría real completa S92, ver anexo).
Queda pendiente el dominio MÁQUINAS -- hoja de ruta intacta, sin
tocar en esta sesión. Se retoma cuando H32 esté cerrado.

**Hito PAUSADO en esta sesión (S77):** H31 — Interfaz de Ficha de
Personal: EPIs y Notificaciones/Circulares →
`ENTERPRISEBOT_ATTACHED_MILESTONE_V31.md`. Acordeón Laboral/Salud de
la ficha de personal completo (documentos, Vacaciones real, Dietas
placeholder, Partes de trabajo con resumen agregado y filtro por
periodo de cobro real, detalle del parte del día en formato
documento). Se retoma cuando H30 tenga la ingesta de `issue_date`
lo bastante avanzada -- ver anexo H31 sección 5.5, "Pendiente real
para cuando H31 se retome".

**Hito PAUSADO en esta sesión (S73):** H30 — Vinculación Documental
Real: Centros de Gasto y Personal →
`ENTERPRISEBOT_ATTACHED_MILESTONE_V30.md`. El bloque EPIs de su hoja
de ruta S73 quedó completo (113 `DocumentAcknowledgment`, extractores
de Botiquines/CONTROL EPIS/ARNES MIRA 12-A/RECURSO PREVENTIVO,
mecanismo `current_template` aplicado). Pendiente real al pausar:
Fase A de `DOC. MAQUINAS` (bloqueada hasta ahora por EPIs, ya
desbloqueada) y la deuda técnica aparcada (plantillas de
comunicados/notificaciones de S71/S72, interfaz del supervisor --
esta última absorbida por el propio H31).

**Hito PAUSADO en esta sesión (S53):** H07 — Partes Diarios de
Reparación Digital → `ENTERPRISEBOT_ATTACHED_MILESTONE_V07.md`. Sin
trabajo de código en S53 sobre este hito — la sesión se dedicó
íntegramente al incidente de H30. Hoja de ruta de H07 queda tal cual
la dejó S52 (sin comprometidos pendientes).

**Hito PAUSADO desde S51:** H30 se pausó entonces así: sesión
larguísima (S51): resolución de las tres preguntas bloqueantes
arrastradas, atajo de alta de tipo documental desde el panel,
corrección de dos bugs reales (enlace de documentación del listado de
flota apuntando al modelo legado, enlaces rotos en el historial de
operaciones para filas ya borradas), fusión de tipos duplicados
(`MANDATO`→`CERTIFICADO_PODERES`, `DOC_BAJA_DEFINITIVA`→
`BAJA_DEFINITIVA`), clasificación en tiempo real heurística+OCR antes
de Gemini, y arreglo del aviso repetido del agente H28. H07 se abrió
entonces por decisión explícita de Miguel Ángel a mitad de sesión:
mientras una VM en la nube (`h28-ocr-batch`, GCE) seguía corriendo de
fondo el barrido de OCR de maquinaria sin necesitar supervisión, se
atendió un bloque grande de mejoras reales sobre Partes Digitales
(clasificación de avería por Gemini, familias, exportación
PDF/Excel, plantillas). H07 permaneció EN PROGRESO durante S52
(cierre completo de esa hoja de ruta) sin que se preguntara si tocaba
reactivar H30 pese a la condición de retorno ya escrita aquí —
incidente real corregido en `nfs-enterprisebot-pcs` durante S53 (ver
anexo H07, registro de sesión S53).

**Hito PAUSADO en esta sesión (S043):** H29 — Explorador de Archivos y
Gobierno Documental del Panel sobre Google Cloud Storage →
`ENTERPRISEBOT_ATTACHED_MILESTONE_V29.md`. Sesión larguísima (S043):
vehículos de empresa por matrícula, herramienta de fusión de
carpetas, arreglo real del aviso instantáneo del agente H28 (404
desde S040), fotografías/extensiones basura auto-eliminadas,
reversos de documentos de doble cara, ordenación del catálogo, y la
Fase 1 completa de la auditoría de máquinas/personal huérfanos
(`audit_new_machines_and_personnel`), con `MachineAsset`/
`PersonIdentity` ya al día contra un Excel real de plantilla y
maquinaria. H30 se abre por decisión explícita de Miguel Ángel: dotar
a esas dos tablas de una referencia viva a su documentación es tarea
de gran calado, con enlace directo a la consolidación de cubos (H29
3.12) que quedó aplazada -- no una tarea más dentro de H29.

**Hito PAUSADO en esta sesión (S036→S037):** H28 — Migración y
Reorganización de Documentación Histórica →
`ENTERPRISEBOT_ATTACHED_MILESTONE_V28.md`. Su Fase 1 quedó completa y
verificada en producción de extremo a extremo al cierre de S036. El
trabajo restante (normalizador de nombres, vocabulario de tipos
documentales, deduplicación, extracción de EPIs y consumidor de la
cuarentena) sigue vivo en su propia hoja de ruta. H29 se abre por
decisión explícita de Miguel Ángel: un explorador de Google Cloud
Storage en el panel es infraestructura de plataforma, no migración de
documentación histórica.

**Hito PAUSADO desde S030→S031:** H23 — Documentación de
Centros de Gasto → `ENTERPRISEBOT_ATTACHED_MILESTONE_V23.md`. Sin
trabajo pendiente urgente propio (ver hoja de ruta de ese anexo);
H28 lo precede y condiciona -- la documentación histórica real debe
migrarse y limpiarse antes de que las pruebas de H23/H25 tengan
sentido pleno contra datos reales.

---

## 4. Protocolo de Enrutamiento Estándar

### Caso normal — Un único hito EN PROGRESO

1. Leer el hito EN PROGRESO de la tabla (marcador `← EN PROGRESO`).
2. Consultar `ENTERPRISEBOT_MASTER_DOCUMENT.md` para el título y
   descripción completa de ese hito.
3. Leer el anexo indicado.
4. La hoja de ruta de ese anexo es la **LEY SUPREMA** de la sesión.

---

## 5. Casos Especiales

### Caso A — Desvío de sesión a otro hito

El trabajo se desvía de H_X (EN PROGRESO) a atender H_Y (PAUSADO).

**Al cierre de sesión se actualizan DOS anexos** (vía
`nfs-enterprisebot-edit`):

1. Anexo de H_X → registrar únicamente la NOTA DE DESVÍO. La hoja
   de ruta no cambia porque el hito no avanzó.
2. Anexo de H_Y → registrar el trabajo realizado y actualizar su
   hoja de ruta.

El marcador `← EN PROGRESO` de esta tabla **NO cambia**. Un desvío de
sesión no implica cambio de hito EN PROGRESO.

### Caso B — Cambio de hito al cierre de sesión

El hito EN PROGRESO (H_X) se pausa y se abre H_Y (ya existente en la
tabla).

**Flujo obligatorio:**

**Paso 1 — Determinar el tipo de cambio:**

- Hito actual no terminado → continuar en el mismo hito. Actualizar
  solo la hoja de ruta del anexo actual. No hay cambio de hito.
- Trabajo para hito anterior pausado → proponer REACTIVACIÓN. Mover
  el marcador `← EN PROGRESO` de H_X a H_Y en la tabla de este
  archivo.
- Hito completamente nuevo → ver Caso C.
- Incidencia fuera del hito actual → atenderla como Caso A (desvío).
  No alterar la hoja de ruta del hito en progreso.

**Paso 2 — Editar este archivo** (vía `nfs-enterprisebot-edit`): mover
el marcador `← EN PROGRESO` de H_X a H_Y en la tabla, y actualizar la
sección "3. Resultado Actual". Solo puede haber UN hito EN PROGRESO
en todo momento.

**Paso 3 — Actualizar los DOS anexos afectados** (mismo commit o
inmediatamente después, vía `nfs-enterprisebot-edit`):

1. Anexo de H_X → registrar el trabajo final. Hoja de ruta de cierre
   o vacía.
2. Anexo de H_Y → registrar el contexto inicial y la hoja de ruta de
   arranque.

### Caso C — Hito nuevo, sin anexo todavía

1. Editar `ENTERPRISEBOT_MASTER_DOCUMENT.md`: añadir fila a la tabla
   de anexos y su descripción en la Hoja de Ruta Estratégica (vía
   `nfs-enterprisebot-edit`).
2. Editar este archivo: añadir el hito nuevo a la tabla como PAUSADO
   (nunca EN PROGRESO directamente sin que Miguel Ángel lo confirme).
3. Crear el anexo nuevo en `DOCS/MAINS/ATTACHEDS/` (número
   correlativo siguiente al último existente) con estructura base:
   objetivo del hito, contexto técnico, hoja de ruta ejecutable de
   forma autónoma.
4. **No modificar el anexo del hito que se pausa.**
5. Un solo commit `docs:` para los tres archivos, vía
   `nfs-enterprisebot-edit`.

### Caso D — Tres o más hitos tocados en la misma sesión

Actualizar tantos anexos como hitos tocados, en este orden:

1. Hito EN PROGRESO (primero siempre).
2. Hitos atendidos por desvío, en orden cronológico.
3. Hito nuevo que abre, si lo hay (último).

---

## 6. Registro de Fusiones y Reorganizaciones de Hitos

Historial permanente de cualquier fusión, renombrado o eliminación de
hito -- **nunca se borra una entrada de aquí**, aunque el hito
afectado deje de existir como tal. Este es el mecanismo de
trazabilidad que exige Miguel Ángel: quién decidió qué, cuándo, y por
qué, para que cualquier persona que retome el proyecto sepa "por
dónde van los tiros" sin tener que reconstruirlo de memoria.

### 2026-09-10 (S99) — H33 fusionado en H31; trabajo de S99 reclasificado a H29

**Contexto real:** la sesión S99 arrancó con H31 `EN PROGRESO`
ejecutando el Punto 1 de su hoja de ruta de S98 (reorganización de
carpetas virtuales de PERSONAL). Al cierre de la sesión, Miguel Ángel
señaló que ese trabajo no correspondía a H31 sino a H29, y que el
verdadero trabajo pendiente de H31 ("dar vida" a la documentación de
personal desde el panel: altas, bajas, subida/sustitución de
documentos, EPIs, notificaciones, poderes, certificados) coincide
exactamente con el objetivo, nunca ejecutado, de H33.

**Cita textual de Miguel Ángel, autorizando explícitamente la
reorganización:** *"la organización de los hitos te la dejo a ti. Tú
verás dónde lo vas a englobar y cómo lo vas a hacer [...] si es
necesario crear un hito nuevo, lo creas. Si es necesario fusionar
hitos anteriores, los fusionas [...] que quede documentado, que quede
una trazabilidad, que se sepa de dónde han venido los hitos [...] si
no, estamos totalmente perdidos."*

**Decisiones tomadas:**
1. El trabajo real de S99 (estructura de carpetas ACTIVOS/INACTIVOS/
   EPIS, subdivisión por empresa, limpieza de carpetas vacías,
   recálculo de contadores) se registra en
   `ENTERPRISEBOT_ATTACHED_MILESTONE_V29.md` ("COMPLETADAS EN S99"),
   no en el de H31. El marcador `← EN PROGRESO` no se movió a H29
   durante la sesión (Caso A de `com-pch`, desvío).
2. **H33 se funde en H31.** H33 no tenía trabajo completado ni hoja de
   ruta ejecutable -- solo un objetivo y cuatro preguntas de diseño
   abiertas, idénticas en espíritu al objetivo real de H31. Su anexo
   (`ENTERPRISEBOT_ATTACHED_MILESTONE_V33.md`) se conserva íntegro,
   sin borrar ni una línea, como archivo histórico; sus preguntas
   abiertas pasan a la hoja de ruta de H31.
3. **H31 se renombra**: de "Interfaz de Ficha de Personal — EPIs y
   Notificaciones/Circulares" a "Interfaz de Gestión Documental de
   Personal — Altas, Bajas, Sustituciones, EPIs y Circulares", en este
   archivo y en `ENTERPRISEBOT_MASTER_DOCUMENT.md`.
4. H30 y H29 no se fusionan ni se tocan más allá de lo del punto 1 --
   H30 conserva su propio trabajo pendiente real (dominio MÁQUINAS),
   genuinamente distinto del objetivo de H31/H33.

**Qué NO cambió:** el número de hito H33 no se reutiliza para nada
nuevo (queda marcado como fusionado, no libre); H29 sigue `PAUSADO`;
no hubo ninguna otra fusión ni eliminación de hito en esta sesión.

---

## 7. Reglas de Obligado Cumplimiento

- Los estados de hito son responsabilidad **exclusiva** de este
  archivo. Ningún anexo ni `ENTERPRISEBOT_MASTER_DOCUMENT.md` puede
  mencionar estados de hito.
- Solo un hito EN PROGRESO en todo momento, sin excepción.
- **QUEDA TERMINANTEMENTE PROHIBIDO** trabajar sobre un anexo que no
  figure en la tabla de este archivo.
