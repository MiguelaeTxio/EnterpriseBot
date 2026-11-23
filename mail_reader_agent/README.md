# Agente de correos (PC de Yolanda)

H31, S156. Lee los correos que llegan a una carpeta de Outlook de
escritorio y los sube al cubo `cgs_grupo_alvarez`, a
`CORREOS DOCUMENTACION/NUEVOS`, para que el servidor los procese (avisos
de plataformas CAE, documentos adjuntos...). Se prepara y se prueba
primero en el PC de Miguel Ángel, eligiendo la carpeta
«Yolanda Bandera» de su buzón.

Miguel Ángel: leer los correos «sin quitar los avisos del propio
Outlook». Por eso el agente:

- lee cada correo sin abrirlo en pantalla: nunca lo marca como leído,
  nunca lo mueve, borra ni etiqueta. El contador de no leídos, la
  alerta de correo nuevo y las reglas siguen igual;
- solo mira los correos recibidos en los últimos 7 días;
- sube cada correo una sola vez (huella del Message-ID), aunque se
  mueva de carpeta.

## Qué sube de cada correo

`CORREOS DOCUMENTACION/NUEVOS/<AAAAMMDD-HHMMSS>_<huella>/`:

- cada adjunto con su nombre (un correo adjunto va como `.msg`);
- `correo.json`, el último: remitente (dirección SMTP también para los
  internos de Exchange), destinatarios, asunto, fecha de recepción,
  cuerpo en texto, carpeta de Outlook y lista de adjuntos (con
  `hidden` para las imágenes incrustadas de las firmas). Sin
  `correo.json` el correo está a medias y se vuelve a subir.

## Archivos

| Archivo | Qué es |
|---|---|
| `main.py` | Icono de bandeja, menú, lectura cada minuto, instancia única |
| `outlook_reader.py` | Lectura de Outlook (COM) y subida al cubo |
| `probar_lectura.py` | Prueba en seco: lee y lista, sin subir ni tocar nada |
| `config.py` | Cubo, carpeta de destino, plazos, rutas de datos |
| `requirements.in` | Dependencias directas (el candado se compila en Windows) |

## Datos en el PC

`%LOCALAPPDATA%\EnterpriseBot\AgenteCorreos\`:

- `service_account_key.json`: la misma clave de cuenta de servicio que
  el agente H28 (copiarla a mano, nunca va a git).
- `settings.json`: la carpeta de Outlook elegida.
- `uploaded.json`: lo ya subido (se olvida a los 30 días).
- `agente_correos.log`: log rotativo.
- `prueba_lectura.txt`: salida de la prueba en seco.

## Preparar el entorno (en el PC de Miguel Ángel, `C:\EnterpriseBot`)

Entorno virtual propio, `mail_agent_venv`. Nunca `Activate.ps1`: se
llama al intérprete del venv directamente.

```powershell
cd C:\EnterpriseBot
git pull

cd mail_reader_agent
..\h28_migration_agent\h28_agent_venv\Scripts\python.exe -m venv mail_agent_venv
.\mail_agent_venv\Scripts\python.exe -m pip install pip-tools
.\mail_agent_venv\Scripts\python.exe -m piptools compile requirements.in
.\mail_agent_venv\Scripts\python.exe -m piptools sync requirements.txt
.\mail_agent_venv\Scripts\python.exe -m pip install pip-tools
```

El `requirements.txt` generado se comitea junto a `requirements.in`.

## Probar en seco (sin subir nada)

Con Outlook abierto. Sale el selector de carpetas de Outlook: elegir
«Yolanda Bandera». Lista cada correo de los últimos 7 días y al final
dice si el número de no leídos ha cambiado (debe decir «SIN CAMBIOS»).

```powershell
cd C:\EnterpriseBot\mail_reader_agent
.\mail_agent_venv\Scripts\python.exe probar_lectura.py
```

## Compilar

```powershell
cd C:\EnterpriseBot\mail_reader_agent
.\mail_agent_venv\Scripts\python.exe -m PyInstaller --onefile --windowed --name AgenteCorreos main.py
```

Sale `dist\AgenteCorreos.exe`.

## Instalar

1. Copiar `AgenteCorreos.exe` a `C:\EnterpriseBot\AgenteCorreos\`.
2. Copiar la clave de la cuenta de servicio del H28 a
   `%LOCALAPPDATA%\EnterpriseBot\AgenteCorreos\service_account_key.json`
   del usuario que lo va a usar.
3. Con la sesión de ese usuario abierta, pegar en PowerShell (sin
   permisos de administrador). Crea los accesos directos del escritorio
   y de Inicio y lo lanza. La primera vez sale el selector de carpetas
   de Outlook.

```powershell
$exe = "C:\EnterpriseBot\AgenteCorreos\AgenteCorreos.exe"
$key = "$env:LOCALAPPDATA\EnterpriseBot\AgenteCorreos\service_account_key.json"
if (-not (Test-Path $exe)) { Write-Warning "Falta el ejecutable: $exe" }
if (-not (Test-Path $key)) { Write-Warning "Falta la clave: $key" }
$shell = New-Object -ComObject WScript.Shell
foreach ($folder in @([Environment]::GetFolderPath("Desktop"), [Environment]::GetFolderPath("Startup"))) {
    $link = $shell.CreateShortcut((Join-Path $folder "Agente de correos.lnk"))
    $link.TargetPath = $exe
    $link.WorkingDirectory = Split-Path $exe
    $link.Description = "EnterpriseBot - Agente de correos"
    $link.Save()
    Write-Output "Acceso directo creado en: $folder"
}
Start-Process $exe
```

## Avisos

- Necesita el Outlook clásico de escritorio (no el «nuevo Outlook»).
- Si el antivirus del PC no está al día, Outlook puede preguntar «Un
  programa está intentando acceder a información de direcciones de
  correo electrónico» al leer el remitente. Con el antivirus al día no
  sale.
