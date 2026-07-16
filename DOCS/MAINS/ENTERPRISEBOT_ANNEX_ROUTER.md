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
| H23 | Documentación de Centros de Gasto | `ENTERPRISEBOT_ATTACHED_MILESTONE_V23.md` ← EN PROGRESO |
| H24 | Vacaciones y Calendario | `ENTERPRISEBOT_ATTACHED_MILESTONE_V24.md` |
| H25 | Documentación de Personal | `ENTERPRISEBOT_ATTACHED_MILESTONE_V25.md` |

Todos los anexos viven en `DOCS/MAINS/ATTACHEDS/`.

---

## 3. Resultado Actual

**Hito EN PROGRESO:** H23 — Documentación de Centros de Gasto →
`ENTERPRISEBOT_ATTACHED_MILESTONE_V23.md`

**Hito PAUSADO en esta sesión (S021):** H24 — Vacaciones y Calendario →
`ENTERPRISEBOT_ATTACHED_MILESTONE_V24.md`. Funcionalidad de vacaciones/
calendario en sí completa desde S020 (sin trabajo pendiente propio); el
único punto abierto que quedaba (migración Google Drive → Google Cloud
Storage, ver anexo V24 "COMPLETADAS EN S019") pasa a rastrearse como
primera tarea de H23, por afectar también a H23 (`MachineDocument`).

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
