# Agente de facturas (PC de Ani)

H28, S151 (sesión invasora). Agente análogo al H28: vigila la carpeta
que Ani le indica y sube al cubo `cgs_grupo_alvarez`, a
`FACTURACION PROVEEDORES/FACTURAS NUEVAS`, cada factura (PDF o imagen)
que aparezca en ella o en sus subcarpetas. No hace nada más:

- El servidor revisa esa carpeta del cubo cada 5 minutos, indexa lo
  nuevo, procesa cada factura (`supplier_invoices`: albaranes, almacén,
  partes) y la pasa a `FACTURAS PROCESADAS`. En el panel:
  Documentación > Bandeja de entrada > FACTURACIÓN PROVEEDORES.
- Nunca borra ni mueve nada de la carpeta de Ani.
- El mismo archivo nunca se sube dos veces (objeto
  `<12 primeros de la huella SHA-256>_<nombre>`; el servidor quita el
  prefijo al indexarlo). Una copia con otro nombre sí se sube, y el
  servidor la marca como factura repetida sin tocar el almacén.

## Archivos

| Archivo | Qué es |
|---|---|
| `main.py` | Icono de bandeja, menú, revisión cada minuto, instancia única |
| `scanner.py` | Recorrido de la carpeta y subida al cubo |
| `config.py` | Cubo, carpeta de destino, rutas de datos |
| `requirements.in` | Dependencias directas (el candado se compila en Windows) |

## Datos en el PC de Ani

`%LOCALAPPDATA%\EnterpriseBot\AgenteFacturas\`:

- `service_account_key.json`: la misma clave de cuenta de servicio que
  usa el agente H28 (copiarla a mano, nunca va a git).
- `settings.json`: la carpeta vigilada (se elige al primer arranque o
  desde el menú "Elegir carpeta de facturas").
- `uploaded.json`: lo ya subido.
- `agente_facturas.log`: log rotativo.

## Compilar (en el PC de Miguel Ángel, `C:\EnterpriseBot`)

Entorno virtual propio, `invoice_agent_venv`, dentro de esta carpeta.
Nunca `Activate.ps1`: se llama al intérprete del venv directamente.

```powershell
cd C:\EnterpriseBot
git pull

cd invoice_upload_agent
..\h28_migration_agent\h28_agent_venv\Scripts\python.exe -m venv invoice_agent_venv
.\invoice_agent_venv\Scripts\python.exe -m pip install pip-tools
.\invoice_agent_venv\Scripts\python.exe -m piptools compile requirements.in
.\invoice_agent_venv\Scripts\python.exe -m piptools sync requirements.txt
.\invoice_agent_venv\Scripts\python.exe -m pip install pip-tools
.\invoice_agent_venv\Scripts\python.exe -m PyInstaller --onefile --windowed --name AgenteFacturas main.py
```

El `requirements.txt` generado se comitea junto a `requirements.in`.
Sale `dist\AgenteFacturas.exe`.

## Instalar en el PC de Ani

1. Copiar `AgenteFacturas.exe` a `C:\EnterpriseBot\AgenteFacturas\`.
2. Copiar la clave a
   `%LOCALAPPDATA%\EnterpriseBot\AgenteFacturas\service_account_key.json`.
3. Arranque automático: acceso directo al `.exe` en
   `shell:startup` (carpeta Inicio del usuario de Ani).
4. Abrir el `.exe`: pide la carpeta de facturas la primera vez.
