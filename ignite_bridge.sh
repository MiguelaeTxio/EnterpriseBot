#!/bin/bash
# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/ignite_bridge.sh

# ---
# Description: Infrastructure ignition script (REFACTORED FOR PYTHONANYWHERE).
# Uses pkill for robust cleanup when lsof is unavailable.
# ---
# Descripción: Script de ignición (REFACTORIZADO PARA PYTHONANYWHERE).
# Usa pkill para limpieza robusta cuando lsof no está disponible.
# ---

PROJECT_ROOT="/home/MiguelAeTxio/PROJECTS/EnterpriseBot"
SWAP_DIR="/home/MiguelAeTxio/SWAP"

# 1. CLEANUP / LIMPIEZA
# Instead of lsof, we target the specific script name to ensure port release
# En lugar de lsof, apuntamos al nombre del script para asegurar la liberación del puerto
echo "# [CLEANUP] Purging existing Sidecar and ngrok processes..."
pkill -9 -f "voice_sidecar_bridge.py"
pkill -9 -f "ngrok"

# Small pause to allow kernel to release sockets / Pausa para liberar sockets
sleep 2

# 2. LAUNCH SIDECAR / LANZAMIENTO DEL SIDECAR
echo "# [BOOT] Launching Voice Sidecar Bridge..."
cd $PROJECT_ROOT
source /home/MiguelAeTxio/.virtualenvs/EnterpriseBot_venv/bin/activate
python3 voice_sidecar_bridge.py >> "$SWAP_DIR/sidecar_runtime.log" 2>&1 &

echo "# [SUCCESS] Ignition sequence completed. Sidecar is running in background."
