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

## 2. Configurar la clave de la cuenta de servicio

La clave JSON descargada en S031 (Key ID
`3309552c7eafa004aea366390f04b0f10cd729c6`) vive **solo en esta
máquina Windows, nunca en este repositorio**. Antes de arrancar el
agente, fija la variable de entorno con su ruta local:

```powershell
$env:H28_AGENT_KEY_PATH = "C:\ruta\segura\enterprisebot-h28-migration-ag-key.json"
```

(Para que persista entre sesiones de PowerShell, usar
`[System.Environment]::SetEnvironmentVariable(...)` a nivel de
usuario, o configurarla en el Programador de tareas de Windows si el
agente se lanza como tarea.)

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
  agente.

El log completo de cada ejecución queda en
`h28_migration_agent.log`, junto al script (o junto al ejecutable
una vez empaquetado).

## 4. Empaquetar como ejecutable (decisión S031: ejecutable con icono en bandeja)

```powershell
pyinstaller --onefile --windowed --name AgenteMigracionH28 main.py
```

El ejecutable resultante queda en `dist\AgenteMigracionH28.exe`. La
variable de entorno `H28_AGENT_KEY_PATH` debe seguir configurada en
la máquina donde se ejecute el `.exe`, exactamente igual que en modo
consola.

**Pendiente (fuera de esta sesión):** sustituir el icono de bandeja
provisional (generado por código en `_build_tray_image()`,
`main.py`) por un `.ico` definitivo — cuando Miguel Ángel lo
entregue, añadir `--icon=ruta\icono.ico` al comando de PyInstaller
de arriba.

## 5. Puntos abiertos para la siguiente sesión de H28 (no decididos en S031)

- **Persistencia de carpetas vigiladas entre reinicios del agente.**
  Ahora mismo, si se cierra el agente y se vuelve a abrir, hay que
  volver a seleccionar cada carpeta manualmente — no hay ninguna
  lista guardada. Si Miguel Ángel quiere que las carpetas ya elegidas
  se retomen automáticamente al reiniciar, hace falta diseñarlo
  (archivo de estado local, ¿dónde vive?) antes de implementarlo.
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
