# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V33.md
# Anexo H33 — Subida de Documentación en Tiempo Real desde el Panel

---

**ABIERTO EN S94** (Caso C de `ENTERPRISEBOT_ANNEX_ROUTER.md`), decisión
explícita de Miguel Ángel durante una conversación de planificación
general sobre varios bloques de trabajo pendientes (EPIs/notificaciones
de H31, alta/baja de trabajadores, subida en tiempo real, modelo propio
de clasificación). Este hito recoge específicamente el bloque de
subida en tiempo real -- ver `ENTERPRISEBOT_ATTACHED_MILESTONE_V34.md`
para el modelo propio de clasificación, hito hermano abierto en la
misma sesión.

---

## 1. Objetivo del hito

La vía de ingesta actual (agente local H28 + Always-on Task de
cuarentena, ver `ENTERPRISEBOT_ATTACHED_MILESTONE_V28.md`) no es
inmediata: un supervisor que deja documentación real en la carpeta
vigilada tiene que esperar al siguiente barrido periódico de la tarea
para que se suba a la nube, se clasifique y se ingeste en base de
datos. Miguel Ángel, verbatim (S94): "esta entrada de documentación no
es inmediata, claro. No nos serviría para situaciones de producción en
las que el supervisor dejase documentación en la carpeta y tener que
esperar a que la tarea que se está ejecutando siempre recoja la
documentación."

Construir una vía de subida **directa desde el propio panel**, para
dos casos reales:

1. Documentación de un **trabajador nuevo** (alta) -- carpeta completa
   con todos sus documentos iniciales.
2. **Actualización** de uno o varios documentos de un trabajador que
   ya existe en base de datos.

La clasificación debe reutilizar el mismo mecanismo real ya construido
en H29/H30 (heurística de nombre de archivo/carpeta → OCR → Gemini
como último recurso), disparado al momento de la subida, sin esperar a
ningún barrido periódico.

---

## 2. Contexto técnico de partida (S94)

- El pipeline de clasificación real vive en `document_explorer`
  (heurística, OCR, Gemini) y en el agente H28 (`h28_migration_agent/`,
  fuera de este repositorio) para la vigilancia de carpeta. Este hito
  necesita reutilizar la lógica de clasificación SIN pasar por el
  agente/Always-on Task -- disparo síncrono o casi síncrono desde una
  petición del panel.
- Relación directa con H34 (modelo propio de clasificación): si H34
  cierra antes, esta subida en tiempo real debería poder usar el
  modelo propio en vez de (o antes que) Gemini -- a decidir en el
  diseño de cada uno según qué cierre primero.
- Relación con H30 (`directriz 4.12`): `blob_name` sigue siendo
  inmutable, cualquier operación de esta subida nueva son altas
  reales en GCS (objeto nuevo), nunca mover/renombrar un objeto ya
  existente por esta vía.

---

## 3. Preguntas abiertas, sin resolver todavía (pendiente de sesión de diseño dedicada)

1. **Alcance del dominio**: ¿solo PERSONAL desde el principio, o
   también MÁQUINAS? El planteamiento de Miguel Ángel en S94 fue sobre
   personal explícitamente, pero el mecanismo es genérico por diseño
   en H29/H30.
2. **Interfaz de subida**: ¿carpeta completa arrastrada de una vez
   (para el alta de un trabajador nuevo con muchos documentos), o
   archivo a archivo (para la actualización puntual de un documento
   concreto)? Probablemente ambas, pero el diseño de la interfaz
   necesita decidir la prioridad.
3. **Manejo de fallos de clasificación en el momento**: a diferencia
   del barrido periódico (donde un fallo puede reintentarse en la
   siguiente pasada sin que nadie lo note), una subida síncrona desde
   el panel necesita una respuesta clara e inmediata al supervisor si
   la clasificación automática falla o tiene baja confianza -- ¿cola
   de revisión manual visible desde el propio panel? ¿reintento
   automático con backoff antes de rendirse?
4. **Relación con NO CONFORMES / cuarentena** (H28): ¿esta vía nueva
   convive con la cuarentena existente, o la sustituye para el caso de
   subida directa desde panel (que en teoría ya tiene el sujeto
   identificado explícitamente por el supervisor, a diferencia de la
   cuarentena, que existe precisamente porque el sujeto no se pudo
   determinar automáticamente)?

---

## Hoja de Ruta para la Sesión Siguiente

**Sin hoja de ruta ejecutable todavía.** Antes de escribir código,
sesión de diseño dedicada para resolver las preguntas abiertas de la
sección 3 con Miguel Ángel.
