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
- **Verificar y reparar carpeta** *(S033)* — abre el mismo diálogo
  de selección de carpeta y ejecuta una reconciliación bajo demanda:
  vuelve a comparar la carpeta local contra el cubo y repara
  cualquier hueco, sin salir del agente ni tocar ninguna consola.
  Útil para volver a comprobar una carpeta ya migrada en cualquier
  momento.
- **Auditar carpeta (Fase 2)** *(S034)* — abre el diálogo de
  selección de carpeta y genera el inventario de la copia local:
  por cada archivo, su ruta relativa, carpeta contenedora, nombre,
  extensión, tamaño en bytes, hash SHA-256 y —si es PDF— su número
  de páginas. **No toca GCS ni la cuenta de servicio, y no modifica
  ni borra absolutamente nada:** es estrictamente local y
  estrictamente de lectura (paso 1 y 2 de la secuencia de la
  sección 8 del anexo H28). Es el dataset con el que se calibran las
  reglas de la Fase 2 —deduplicación, heurística de dosieres y
  catálogo de patrones de nombre— con datos reales delante en vez de
  a ciegas. Salida en `agent_data\audits\`: un CSV con el inventario
  completo y un `_resumen.txt` en castellano con los totales,
  duplicados exactos detectados y reparto por extensión. Como hay
  que leer cada archivo entero para calcular su hash, la pasada
  tarda varios minutos sobre una carpeta grande y el menú no
  responde mientras tanto — se avisa antes de empezar y se pide
  confirmación.
- **Ver historial** *(S033)* — abre una ventana de solo lectura con
  los eventos recientes del agente (copias y reconciliaciones), más
  reciente primero, sin necesidad de abrir `h28_migration_agent.log`.
  Decisión de Miguel Ángel: el visor de tareas vive en el propio
  agente, no en la plataforma web — agente y plataforma quedan
  deliberadamente separados. Guardado en
  `agent_data\history.json`, con los últimos
  `config.HISTORY_MAX_EVENTS` eventos (200 por defecto).
- **Salir** — detiene todas las vigilancias en marcha y cierra el
  agente. **No olvida las carpetas** — quedan guardadas en
  `agent_data\watched_folders.json` y se retoman automáticamente en
  el siguiente arranque, sin volver a seleccionarlas (decisión S031:
  "el agente tiene que recordar qué estaba haciendo y seguir
  haciéndolo").

El log completo de cada ejecución queda en
`h28_migration_agent.log`, junto al script (o junto al ejecutable
una vez empaquetado).

### Reconciliación automática tras la copia (S033)

Confirmado por Miguel Ángel: el sistema debe poder afrontar errores y
recuperarse solo, sin intervención manual por consola. Al terminar
**Seleccionar carpeta y copiar**, el agente ejecuta automáticamente
`reconciler.reconcile_folder()`:

1. Vuelve a listar la carpeta local y compara cada archivo, por
   tamaño, contra lo que hay realmente en el cubo — usando la
   librería `google-cloud-storage`, nunca `gcloud` CLI.
2. Cualquier archivo ausente o con tamaño distinto se reintenta
   automáticamente hasta 3 veces, con espera creciente entre
   intentos (5s, 15s, 45s — `config.RECONCILE_MAX_RETRIES` /
   `RECONCILE_RETRY_DELAYS_SECONDS`).
3. Lo que siga sin subir tras los 3 intentos queda registrado en el
   log con la etiqueta `IRRECUPERABLE`, distinta de un fallo
   normal, para que salte a la vista sin necesidad de revisar todo
   el log línea a línea.
4. El resultado se muestra siempre como notificación de bandeja
   (reparados / irrecuperables), sin necesidad de abrir el log salvo
   que se quiera el detalle.

El mismo mecanismo es el que usa **Verificar y reparar carpeta** bajo
demanda.

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

## 5. Arranque automático (decisión S031: tarea programada)

Registrada una tarea programada de Windows que arranca el `.exe` en
cuanto el usuario inicia sesión (no requiere permisos de
administrador ni cuenta SYSTEM — un icono de bandeja necesita una
sesión de escritorio real):

```powershell
$Action = New-ScheduledTaskAction -Execute "C:\EnterpriseBot\h28_migration_agent\dist\AgenteMigracionH28.exe" -WorkingDirectory "C:\EnterpriseBot\h28_migration_agent\dist"
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERNAME"
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERNAME" -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName "EnterpriseBot_H28_MigrationAgent" -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal -Description "Agente de migracion H28 - sube documentacion historica a GCS"
```

Probada en S031 con `Start-ScheduledTask -TaskName
"EnterpriseBot_H28_MigrationAgent"` — icono de bandeja apareció
correctamente. `LastTaskResult: 267009` en
`Get-ScheduledTaskInfo` es `SCHED_S_TASK_RUNNING`, no un error — es
el código normal para una tarea que se queda corriendo indefinidamente
(la app de bandeja nunca termina sola).

**El `.exe` debe reconstruirse tras cualquier cambio de código**
(sección 4) — y recuerda copiar también la clave actualizada a
`dist\agent_data\service_account_key.json` si `dist\` se genera de
cero.

## 6. Reconciliación automática al arrancar (S034) — punto cerrado

El matiz que S031 dejó documentado y S033 dejó pendiente de decisión
explícita queda **cerrado en S034**, por decisión de Miguel Ángel:
*"creo que es lo más lógico de hacerlo de forma automática una vez
que arranque el agente"*.

`_resume_watched_folders()` (`main.py`) ya no se limita a retomar la
vigilancia de las carpetas persistidas: tras arrancar los
vigilantes, ejecuta también una reconciliación completa sobre cada
una de ellas, con el mismo mecanismo de **Verificar y reparar
carpeta**. Los archivos aparecidos con el agente apagado dejan de
quedar invisibles hasta que alguien se acuerde de pedir una
verificación a mano.

Dos detalles de implementación, deliberados:

- **La vigilancia arranca antes que la reconciliación.** Reconciliar
  una carpeta grande tarda minutos, y durante esa ventana los
  archivos que se creen en local deben llegar igualmente a
  cuarentena. Al revés se perderían esos eventos.
- **Cada carpeta se reconcilia dentro de su propio guardado de
  errores.** Que una falle no puede impedir que las demás se
  reconcilien, ni tumbar el arranque del agente.

Consecuencia práctica: el arranque del agente sobre carpetas ya
migradas grandes tarda ahora bastante más que antes, porque compara
el árbol entero contra el cubo antes de quedarse en reposo. Es el
coste esperado de la decisión, no un síntoma de cuelgue — el
progreso queda en `h28_migration_agent.log` y el resultado como
notificación de bandeja y entrada de **Ver historial**.
