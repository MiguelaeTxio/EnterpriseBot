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
| H31 | Interfaz de Ficha de Personal — EPIs y Notificaciones/Circulares | `ENTERPRISEBOT_ATTACHED_MILESTONE_V31.md` ← EN PROGRESO |
| H32 | Migraciones de Infraestructura (Modelo IA, Python, Registro Android) | `ENTERPRISEBOT_ATTACHED_MILESTONE_V32.md` |
| H33 | Subida de Documentación en Tiempo Real desde el Panel | `ENTERPRISEBOT_ATTACHED_MILESTONE_V33.md` |
| H34 | Modelo Propio de Clasificación de Documentos (entrenamiento) | `ENTERPRISEBOT_ATTACHED_MILESTONE_V34.md` |

Todos los anexos viven en `DOCS/MAINS/ATTACHEDS/`.

---

## 3. Resultado Actual

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

**Hito EN PROGRESO:** H31 — Interfaz de Ficha de Personal: EPIs y
Notificaciones/Circulares → `ENTERPRISEBOT_ATTACHED_MILESTONE_V31.md`.
Reactivado en S93 tras confirmar que se cumple la condición real de
reactivación registrada en su propio anexo (sección 5.5): las
familias `LABORAL` + `SALUD_BAJAS_PERSONA` (6.085 documentos, 0% con
`issue_date`/`expiry_date` en el momento de la pausa, S77) quedaron
cubiertas al 100% con el cierre del dominio PERSONAL de H30 en S92.
Hoja de ruta de arranque: los tres puntos de "Pendiente real para
cuando H31 se retome" de su propio anexo (sección 5.5), intactos
desde S77.

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

## 6. Reglas de Obligado Cumplimiento

- Los estados de hito son responsabilidad **exclusiva** de este
  archivo. Ningún anexo ni `ENTERPRISEBOT_MASTER_DOCUMENT.md` puede
  mencionar estados de hito.
- Solo un hito EN PROGRESO en todo momento, sin excepción.
- **QUEDA TERMINANTEMENTE PROHIBIDO** trabajar sobre un anexo que no
  figure en la tabla de este archivo.
