# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/h28_migration_agent/README.md
# Agente de Migración H28 — Fase 1

Script auxiliar independiente (no es una app Django, no se carga en
`enterprise_core`). Corre en una máquina Windows, sube en bruto las
carpetas elegidas al cubo sucio de GCS, y vigila esas carpetas de
forma indefinida tras la copia inicial. Ver
`DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V28.md` para
el diseño completo y las decisiones cerradas en S031.

## 1. Preparar el entorno (primera vez, en la máquina Windows)

```powershell
py -m venv h28_agent_venv
.\h28_agent_venv\Scripts\activate
pip install -r requirements.txt
```

## 2. Colocar la clave de la cuenta de servicio

**Cambio S031, respecto a versiones anteriores de este README:** la
clave ya no necesita variable de entorno para el uso normal. Vive en
una carpeta propia del agente, `agent_data\` (nunca versionada — ver
`.gitignore`), junto al script o junto al ejecutable una vez
empaquetado.

Copia ahí la clave JSON descargada en S031 (Key ID
`3309552c7eafa004aea366390f04b0f10cd729c6`) con este nombre exacto:

```
h28_migration_agent\agent_data\service_account_key.json
```

Si `agent_data\` no existe todavía, créala — el propio agente también
la crea sola al arrancar si hace falta.

**Alternativa (opcional):** si prefieres guardar la clave en otro
sitio, sigue funcionando fijando la variable de entorno
`H28_AGENT_KEY_PATH` con la ruta completa — esta tiene prioridad
sobre la ubicación por defecto de `agent_data\`.

## 3. Ejecutar en modo consola (desarrollo/pruebas)

```powershell
python main.py
```

Aparece un icono en la bandeja del sistema ("EnterpriseBot — Agente
de Migración H28"). Clic derecho:

- **Seleccionar carpeta y copiar** — abre el diálogo de selección de
  carpeta, copia todo su contenido de forma recursiva y completa al
  cubo sucio (`cgs_grupo_alvarez`), y a partir de ahí queda vigilando
  esa carpeta indefinidamente: cualquier archivo nuevo que aparezca
  se sube al cubo de cuarentena (`cgs_grupo_alvarez_cuarentena`), no
  al árbol espejo del cubo sucio.
- **Salir** — detiene todas las vigilancias en marcha y cierra el
  agente. **No olvida las carpetas** — quedan guardadas en
  `agent_data\watched_folders.json` y se retoman automáticamente en
  el siguiente arranque, sin volver a seleccionarlas (decisión S031:
  "el agente tiene que recordar qué estaba haciendo y seguir
  haciéndolo").

El log completo de cada ejecución queda en
`h28_migration_agent.log`, junto al script (o junto al ejecutable
una vez empaquetado).

## 4. Empaquetar como ejecutable (decisión S031: ejecutable con icono en bandeja)

```powershell
pyinstaller --onefile --windowed --name AgenteMigracionH28 main.py
```

El ejecutable resultante queda en `dist\AgenteMigracionH28.exe`. La
clave sigue resolviéndose igual (sección 2) — colócala en
`dist\agent_data\service_account_key.json`, junto al `.exe`, o usa
la variable de entorno.

**Pendiente (fuera de esta sesión):** sustituir el icono de bandeja
provisional (generado por código en `_build_tray_image()`,
`main.py`) por un `.ico` definitivo — cuando Miguel Ángel lo
entregue, añadir `--icon=ruta\icono.ico` al comando de PyInstaller
de arriba.

## 5. Puntos abiertos para la siguiente sesión de H28 (no decididos en S031)

- **Alcance de la persistencia entre reinicios.** Lo construido en
  S031 retoma la *vigilancia* de las carpetas ya elegidas, pero no
  repite la copia inicial ni escanea archivos que hayan aparecido
  mientras el agente estaba cerrado — solo los eventos en vivo de
  watchdog (agente corriendo) llegan a cuarentena. Si Miguel Ángel
  quiere que también se detecten archivos nuevos aparecidos durante
  el tiempo que el agente estuvo apagado, hace falta diseñar un
  escaneo de "puesta al día" al arrancar — no construido en S031.
- **Formato exacto del nombre de blob dentro del cubo sucio.** Esta
  sesión implementó `{nombre_de_la_carpeta_elegida}/{ruta_relativa
  interna}` como interpretación pragmática de "replicar la ruta
  local completa" (ver docstring de `build_blob_name()` en
  `uploader.py`) — no incluye la ruta absoluta de Windows completa
  (unidad, OneDrive, etc.). Confirmar con Miguel Ángel si esto es lo
  que se quería decir, o si hace falta algo distinto.
- **Arranque automático de la máquina Windows** (tarea programada,
  inicio de sesión, servicio de Windows) — no decidido ni construido
  todavía, solo el ejecutable en sí.
