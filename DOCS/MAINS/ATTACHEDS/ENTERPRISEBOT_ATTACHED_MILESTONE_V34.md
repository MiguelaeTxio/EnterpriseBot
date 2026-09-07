# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V34.md
# Anexo H34 — Modelo Propio de Clasificación de Documentos (entrenamiento)

---

**ABIERTO EN S94** (Caso C de `ENTERPRISEBOT_ANNEX_ROUTER.md`), con
**prioridad de atención propia máxima** -- decisión explícita de
Miguel Ángel, verbatim: "coincido en que el entrenamiento del modelo
[...] requiere un hito propio. Porque además vamos a sentar la base de
la clasificación de documentos a raíz del entrenamiento de este
modelo. Por tanto, debemos dedicarle la máxima atención posible y no
un punto de hoja de ruta dentro de otro hito." Hito hermano de H33
(subida en tiempo real), abierto en la misma sesión de planificación.

---

## 1. Objetivo del hito

Entrenar un modelo propio que sustituya a Gemini como clasificador
**principal** de documentos -- Gemini pasa a ser el último recurso
(fallback), no la vía por defecto. Empezando por el dominio
**PERSONAL** (donde ya existe volumen real suficiente tras el cierre
de H30), con **MAQUINARIA** como extensión futura del mismo mecanismo,
no como parte de este hito.

---

## 2. Contexto real de partida (S94)

- **Intento anterior, sin éxito por falta de datos.** Miguel Ángel,
  verbatim: "lo intentamos en la propia clasificación, pero no
  teníamos datos suficientes para que el modelo fuese efectivo."
- **Ahora sí hay dataset real.** Tras el cierre del dominio PERSONAL de
  H30 (S92, extracción de `issue_date`/`expiry_date` al 100% y
  clasificación completa), existe un volumen considerable de
  documentos ya clasificados y verificados en base de datos --
  especialmente en los tipos documentales de **gran volumen** real
  (ver tabla de la sección 5.5 del anexo H31: declaraciones de estar
  al corriente, bajas de Seguridad Social, reconocimientos médicos,
  investigaciones de accidente laboral, contratos laborales,
  registros de jornada... cientos a miles de documentos por tipo).
- **Los tipos de poco volumen no necesitan modelo.** Miguel Ángel,
  verbatim: "los de poco volumen casi todos se han reducido ya, que
  son plantillas y documentos que en un momento dado, pues por
  heurística sí podríamos discriminarlos." El modelo propio se dirige
  específicamente a los tipos de gran volumen, donde la heurística de
  nombre de archivo/carpeta no basta y hoy se depende de Gemini.

---

## 3. Preguntas abiertas, sin resolver todavía (pendiente de sesión de diseño dedicada)

1. **Arquitectura del modelo**: ¿clasificador de texto sobre el
   `ocr_text` ya cacheado (H30 S78, `DocumentIndexEntry.ocr_text`), un
   modelo de visión sobre la imagen/PDF directamente, o un híbrido?
   El texto OCR ya cacheado de miles de documentos reales es un punto
   de partida real y disponible sin coste adicional de extracción.
2. **Formato y tamaño real del dataset de entrenamiento**: extraer de
   BD ya clasificada (`DocumentIndexEntry.document_type` real,
   verificado por meses de uso en producción) -- volumen exacto por
   tipo documental a auditar antes de diseñar el modelo, para saber
   qué tipos tienen suficiente volumen real y cuáles seguirán
   dependiendo de heurística/Gemini.
3. **Criterio de validación** antes de sustituir a Gemini en
   producción -- ¿qué exactitud mínima por tipo documental, medida
   contra qué conjunto de validación (documentos ya clasificados y
   verificados manualmente, nunca autoevaluación circular)?
4. **Mecanismo de fallback real**: cuando el modelo propio no tenga
   confianza suficiente para un documento concreto, ¿cae a heurística,
   a Gemini, o a cuarentena para revisión humana? Necesita un umbral de
   confianza real, no una decisión binaria.
5. **Dónde y cómo se entrena**: ¿en local (máquina de Miguel Ángel),
   en una VM de GCE dedicada (mismo patrón que las VMs de OCR de H28),
   o en un servicio gestionado? Afecta directamente al coste y al
   tiempo de iteración.

---

## Hoja de Ruta para la Sesión Siguiente

**Sin hoja de ruta ejecutable todavía.** Antes de escribir código o
tocar cualquier dato, sesión de diseño dedicada para resolver las
preguntas abiertas de la sección 3 con Miguel Ángel -- empezando
probablemente por una auditoría real del volumen disponible por tipo
documental (pregunta 2), que condiciona todas las demás decisiones.
