# Anexo H32 — Migraciones de Infraestructura (Modelo IA, Python, Registro Android)

---

## 1. Objetivo del Hito

Tres plazos externos reales, impuestos por terceros (Google/Vertex
AI, Google/PythonAnywhere, Google Play), convergen en
septiembre-octubre de 2026. Ninguno depende de decisiones de negocio
de Grupo Álvarez -- son fechas de corte técnicas que hay que cumplir
sí o sí. Se abre como hito propio (S92) en vez de colarse como
desvíos sueltos dentro de H30/H31, porque el volumen de auditoría
necesario (sobre todo el del modelo de IA) no está acotado todavía.

---

## 2. Contexto Técnico

### 2.1. Migración `gemini-2.5-flash` → `gemini-3.5-flash`

Deuda técnica ya registrada desde S001-H10 en
`ENTERPRISEBOT_MASTER_DOCUMENT.md` sección 4.1.1 -- releer esa sección
completa antes de tocar nada, no repetir la investigación desde cero.

**Plazos reales (verificados en línea en S001-H10, re-verificar si ha
pasado más de una semana antes de dar por buena la fecha):**
- Bloqueo de acceso a inferencia online **nueva**: ~16 de septiembre
  de 2026.
- Apagado total (`gemini-2.5-pro`, `gemini-2.5-flash`,
  `gemini-2.5-flash-lite`): 16 de octubre de 2026.
- Fuera de alcance de esta migración: `gemini-live-2.5-flash-native-audio`
  (Live API, voz/IVR) -- ciclo de vida propio, no asumir equivalencia
  automática con `gemini-3.5-flash`.

**Punto ya confirmado con `gemini-2.5-flash` pendiente de migrar**
(lista parcial, S001-H10):
- `work_order_processor/services.py` -- constante `_GEMINI_MODEL =
  "gemini-2.5-flash"`, usada por `extract_work_order_page()` (Gemini
  Vision) y `classify_fault()` (solo texto).

**Auditoría todavía sin hacer:** el resto del proyecto no se ha
revisado. Buscar `gemini-2.5-flash` y `gemini-2.5-pro` (constantes,
strings literales, variables de entorno) en todo el árbol de código
-- candidatos ya conocidos por usar Gemini en algún punto:
`ai_services/gemini_client.py`, `ai_services/gemini_rate_limiter.py`,
`document_explorer/date_verification_service.py`
(`extract_expiry_via_gemini`), cualquier `tasks.py` de dominio
(`machine_documents`, `personal_documents`, `document_ingestion`,
`document_management`), y los extractores standalone de
`h28_migration_agent/` (que son copias, no importan el módulo Django
-- ver `document_explorer/date_verification_service.py`, comentario
sobre "copia standalone").

### 2.2. Migración de versión de Python en PythonAnywhere

`google.api_core` deja de dar soporte a Python 3.10 a partir del **4
de octubre de 2026** (correo real de Google/PythonAnywhere ya
recibido por Miguel Ángel, con el detalle). Verificar en línea, al
empezar este bloque, cuál es la versión de Python más reciente
soportada tanto por PythonAnywhere (planes de hosting) como por el
`google-genai`/`google-cloud-storage` que usa el proyecto, antes de
fijar el objetivo (3.11 vs 3.12) -- no asumir de memoria.

### 2.3. Registro de apps Android en Google Play Console

Correo real de Google (recibido 2026-09-01): desde el 30 de
septiembre de 2026, las apps Android distribuidas en tiendas
participantes deben registrar nombre de paquete y firma con identidad
de desarrollador verificada para poder instalarse en dispositivos
certificados. **Sin acción posible todavía** -- no existe ninguna app
Android nativa construida en este proyecto (la app de albaranes para
tablets de operarios, en Kotlin, offline, sigue solo anotada como
alcance futuro, sin empezar). Punto informativo del hito hasta que
haya algo real que registrar.

---

## 3. COMPLETADAS EN S92

Hito abierto en esta misma sesión (PCH desde H30, tras cerrar el
dominio PERSONAL al 100%). Sin trabajo de código todavía sobre las
migraciones en sí -- el bloque de trabajo de S92 fue íntegramente el
cierre de H30/PERSONAL (ver `ENTERPRISEBOT_ATTACHED_MILESTONE_V30.md`)
y la creación de este hito (documento maestro, enrutador, este mismo
anexo). Punto de partida real para S93: sección 3 de arriba, "Hoja de
Ruta para la Sesión Siguiente (S93)".

---

## 4. Hoja de Ruta para la Sesión Siguiente (S93)

Ejecución estrictamente secuencial, sin preguntar por dónde empezar.

**Punto 1 -- Auditoría completa de usos de `gemini-2.5-flash`/
`gemini-2.5-pro` en todo el proyecto.** `grep -rn` (workspace del
modelo, sobre el clon) de ambas cadenas en todo el árbol de código
(excluir `.git/`, `node_modules/` si los hubiera). Criterio de cierre:
tabla completa con cada archivo/línea real encontrado, pegada en la
bitácora de S93, antes de decidir nada más. No dar la lista de
S001-H10 (sección 2.1 de arriba) por completa ni por desactualizada
sin comprobarlo.

**Punto 2 -- Migrar cada punto encontrado a `gemini-3.5-flash`.**
Uno a uno, con `py_compile` tras cada cambio. Verificar en línea antes
de migrar si `gemini-3.5-flash` tiene el mismo formato de respuesta
que `gemini-2.5-flash` para Vision (extracción de partes PDF) y para
texto (clasificación de avería) -- no asumir compatibilidad
automática, el propio master document ya lo advierte.

**Punto 3 -- Validar en producción con datos reales** al menos un caso
de cada punto migrado (un parte PDF real para Vision, una descripción
de avería real para clasificación de texto) antes de dar la migración
del modelo por cerrada.

**Punto 4 -- Investigar versión objetivo de Python** (3.11 vs 3.12)
verificando en línea compatibilidad con PythonAnywhere y con las
dependencias reales del proyecto (`requirements.txt`), y dejar
plan concreto de migración (no ejecutarla todavía en esta sesión
salvo que quede tiempo real de sobra tras los puntos 1-3).

**Punto 5 -- Sin acción sobre Google Play Console** hasta que exista
una app Android real que registrar (ver 2.3 arriba) -- no revisar este
punto en próximas sesiones salvo que Miguel Ángel abra la app de
albaranes.
