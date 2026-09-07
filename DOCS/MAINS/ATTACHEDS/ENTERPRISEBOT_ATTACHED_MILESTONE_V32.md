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

**CERRADA en S93.** Auditoría completa (`grep -rln` sobre todo el
árbol, no solo `.py`) y migración de las 5 líneas de código reales
encontradas -- ver sección "COMPLETADAS EN S93" para el detalle y el
commit. Sección conservada aquí solo por los plazos reales, que
siguen siendo relevantes hasta que Punto 3 (validación en producción)
se cierre:

**Plazos reales (verificados en línea en S001-H10, re-verificar si ha
pasado más de una semana antes de dar por buena la fecha):**
- Bloqueo de acceso a inferencia online **nueva**: ~16 de septiembre
  de 2026.
- Apagado total (`gemini-2.5-pro`, `gemini-2.5-flash`,
  `gemini-2.5-flash-lite`): 16 de octubre de 2026.
- Fuera de alcance de esta migración: `gemini-live-2.5-flash-native-audio`
  (Live API, voz/IVR) -- ciclo de vida propio, no asumir equivalencia
  automática con `gemini-3.5-flash`.

**Pendiente real, único punto abierto de este bloque:** validación en
producción con datos reales (Punto 3 de la hoja de ruta de S93, más
abajo) -- requiere que Miguel Ángel genere un caso real de Vision (un
parte de trabajo PDF) y uno de clasificación de texto (una descripción
de avería real por WhatsApp).

### 2.2. Migración de versión de Python en PythonAnywhere

`google.api_core` deja de dar soporte a Python 3.10 a partir del **4
de octubre de 2026** (correo real de Google/PythonAnywhere ya
recibido por Miguel Ángel, con el detalle) -- confirmado también en
línea en S93 (issue real de `googleapis/google-cloud-python`, aviso
`FutureWarning` de `google.api_core._python_version_support` citando
la misma fecha 2026-10-04 y recomendando mínimo Python 3.11).

**Investigación S93 (Punto 4 de la hoja de ruta, verificada en línea,
no de memoria):**
- **PythonAnywhere:** desde 2025-03-25, las cuentas nuevas tienen
  disponibles Python 3.11, 3.12 y 3.13 sobre la imagen de sistema
  nueva ("innit", Ubuntu 22.04). Las cuentas anteriores a esa fecha
  siguen en la imagen antigua salvo que se pida el cambio manual
  (`help.pythonanywhere.com/pages/ChangingSystemImage`) -- **sin
  confirmar todavía si la cuenta de Miguel Ángel ya está en "innit"**,
  pendiente del Comando S entregado en S93.
- **`google-genai`:** soporta Python 3.10 a 3.14 sin restricción
  (verificado en PyPI, release 2.22.0, 2026-09-02).
- **`google-cloud-aiplatform`** (dependencia transitiva de Vertex AI):
  requiere Python >= 3.10, sin límite superior confirmado.
- **Django 5.2:** compatible con 3.10-3.13 (conocido, sin necesidad de
  reverificar).

**Objetivo recomendado: Python 3.12.** Dentro del rango soportado por
PythonAnywhere/innit, por `google-genai`/`google-cloud-aiplatform`, y
por Django 5.2 -- con un margen de una versión completa sobre el
mínimo 3.11 que exige `google.api_core`, sin ser la más reciente
(3.13), que podría tener fricción de compatibilidad más nueva y menos
probada en el ecosistema de dependencias del proyecto.

**Plan concreto (no ejecutado todavía, pendiente de confirmar imagen
de sistema real de la cuenta):**
1. Confirmar con Miguel Ángel (Comando S de S93) si la cuenta ya está
   en la imagen "innit" o si hace falta pedir el cambio de imagen
   desde el dashboard de PythonAnywhere primero.
2. Crear un virtualenv nuevo (`EnterpriseBot_venv_py312` o
   equivalente) con Python 3.12, en paralelo al venv actual -- nunca
   sobrescribir el venv en producción directamente.
3. `pip-sync` del `requirements.txt` real del proyecto sobre el venv
   nuevo, y revisar uno a uno los paquetes que fallen (candidatos de
   riesgo: dependencias con extensiones C compiladas, si las hubiera --
   pendiente de verificar contra el `requirements.txt` real, no
   asumido de memoria).
4. Cambiar el intérprete del virtualenv en la configuración de la web
   app de PythonAnywhere (pestaña "Web" → "Virtualenv") solo cuando el
   punto 3 esté verde, y con una ventana de reload controlada, no en
   caliente sin aviso.
5. Verificar en producción con datos reales tras el cambio -- misma
   filosofía que Punto 3 del bloque Gemini: no dar por cerrada la
   migración solo por ausencia de errores en el reload.

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
anexo).

## 3.1. COMPLETADAS EN S93

**Punto 1 -- Auditoría completa cerrada.** `grep -rln` sobre todo el
árbol del clon (no solo `.py`) de `gemini-2.5-flash`/`gemini-2.5-pro`.
Solo 5 líneas de código real en 3 archivos pendientes de migrar:
`file_organizer/organizer_probe.py:34`, `whatsapp/services.py:170`,
`whatsapp/services.py:1298`, `whatsapp/services.py:1744`,
`work_order_processor/services.py:123`. El resto de coincidencias
(`work_order_processor/tasks.py`, `spare_parts/services.py`,
`ai_services/gemini_client.py`) eran comentarios/docstrings, no
constantes funcionales -- `document_explorer/date_verification_service.py`
y `ai_services/gemini_rate_limiter.py`, citados como candidatos en la
sección 2.1 original, **ya no aparecían** en el grep: ya resuelven a
`gemini-3.5-flash` vía `DEFAULT_MODEL` de `ai_services.gemini_client`,
sin que constara documentado en ningún sitio -- la migración real ya
había avanzado más de lo que registraba la lista parcial de S001-H10.

**Punto 2 -- Migración cerrada.** Las 5 líneas migradas a
`gemini-3.5-flash`, `py_compile` en verde tras cada cambio.
Verificado en línea antes de migrar (búsqueda "gemini-3.5-flash
Vertex AI response format changes"): ninguno de los 5 puntos usa
segmentación de imagen (no soportada en Gemini 3.x, hay que seguir
usando 2.5 Flash con thinking apagado para eso) ni `candidate_count`
(retirado en Gemini 3.x) -- `thinking_budget=0`, usado en
`work_order_processor/services.py` (2 llamadas), sigue soportado por
compatibilidad hacia atrás. Comentarios desactualizados que citaban la
deuda como pendiente, actualizados en el mismo bloque
(`work_order_processor/tasks.py`, `ai_services/gemini_client.py`,
`spare_parts/services.py`). Commit `253a057`, push a `main`, Action
"Deploy EnterpriseBot to PythonAnywhere" en `success` (sin migración
de modelo Django en este bloque, conclusion suficiente).

**Punto 4 -- Investigación de versión de Python completada, plan
dejado en sección 2.2** (no ejecutado). Objetivo recomendado: Python
3.12. Pendiente de un dato real de la cuenta de Miguel Ángel (imagen
de sistema activa) antes de ejecutar nada -- Comando S entregado en
S93, resultado todavía no recibido al cierre de esta sesión.

**Punto 3 -- Sin cerrar, requiere acción de Miguel Ángel** fuera del
alcance de esta sesión de chat: generar un caso real de Vision (parte
de trabajo PDF) y uno de clasificación de texto (descripción de
avería real por WhatsApp) en producción, ya con `gemini-3.5-flash`
activo tras el despliegue del Punto 2.

---

## 4. Hoja de Ruta para la Sesión Siguiente (S94)

Ejecución estrictamente secuencial, sin preguntar por dónde empezar.

**Punto 1 -- Cerrar el Comando S de Python pendiente de S93.** Leer
el resultado real de `EnterpriseBot_001_GET.txt` (intérpretes
disponibles, versión del venv actual, imagen de sistema) antes de
decidir nada del plan de migración de la sección 2.2 -- no asumir que
la cuenta ya está en "innit" sin la confirmación real.

**Punto 2 -- Validar el Punto 3 del bloque Gemini** (sección 2.1) si
Miguel Ángel ya generó los casos reales de Vision/texto -- confirmar
formato de respuesta de `gemini-3.5-flash` en producción antes de dar
la migración del modelo por completamente cerrada. Si todavía no hay
casos reales disponibles, dejarlo abierto y no bloquear el resto de
la sesión por ello.

**Punto 3 -- Ejecutar el plan de migración de Python** (sección 2.2,
pasos 2-5) si el Punto 1 de esta hoja de ruta confirma que la cuenta
está en imagen "innit" (o una vez completado el cambio de imagen si
no lo estaba). Crear venv nuevo con Python 3.12, `pip-sync` del
`requirements.txt` real, y no cambiar el intérprete de la web app en
producción hasta que ese venv esté verde.

**Punto 4 -- Sin acción sobre Google Play Console** hasta que exista
una app Android real que registrar (ver sección 2.3) -- no revisar
este punto en próximas sesiones salvo que Miguel Ángel abra la app de
albaranes.
