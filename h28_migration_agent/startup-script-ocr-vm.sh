#!/bin/bash
# h28_migration_agent/startup-script-ocr-vm.sh
#
# H30 (sesion tras S85). Script de arranque de las 4 VMs de OCR
# (h28-ocr-batch-1/2/3/4), instalado como metadato `startup-script` de
# cada instancia (GCE lo ejecuta como root en cada arranque).
#
# Decision explicita de Miguel Angel: NUNCA guardar un token de GitHub
# en metadatos de instancia (legible por cualquiera con permiso
# "viewer" del proyecto) -- por eso este script NO hace git pull ni
# toca el codigo del checkout. Su unico trabajo es dejar el entorno
# virtual (ocr_venv) sincronizado contra el candado de dependencias ya
# versionado (requirements-ocr-vm.txt), por si la imagen base
# (h28-ocr-batch-image-v1) quedo desactualizada respecto al candado
# real del repo entre una sesion y otra.
#
# El codigo en si (git pull) lo sigue haciendo Miguel Angel a mano al
# empezar cada sesion en cada VM que use, pegando el token el.
set -e

CHECKOUT_DIR="/home/Usuario/EnterpriseBot/h28_migration_agent"
LOG_FILE="/home/Usuario/startup-script-ocr-vm.log"

{
    echo "=== startup-script-ocr-vm.sh -- $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="

    if [ ! -d "$CHECKOUT_DIR" ]; then
        echo "AVISO: $CHECKOUT_DIR no existe todavia -- nada que sincronizar."
        exit 0
    fi

    cd "$CHECKOUT_DIR"
    source ocr_venv/bin/activate

    echo "Sincronizando ocr_venv contra requirements-ocr-vm.txt ..."
    pip-sync requirements-ocr-vm.txt

    echo "=== startup-script-ocr-vm.sh terminado OK ==="
} >> "$LOG_FILE" 2>&1
