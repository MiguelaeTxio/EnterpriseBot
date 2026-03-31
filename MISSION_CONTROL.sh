#!/bin/bash
# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/MISSION_CONTROL.sh

# ---
# Description: Mission Control Orchestrator (Script S Model).
# Directs all telemetry to a downloadable audit report.
# ---
# Descripción: Orquestador de Control de Misión (Modelo Script S).
# Dirige toda la telemetría a un informe de auditoría descargable.
# ---

PROJECT_ROOT="/home/MiguelAeTxio/PROJECTS/EnterpriseBot"
SWAP_DIR="/home/MiguelAeTxio/SWAP"
VENV_PATH="/home/MiguelAeTxio/.virtualenvs/EnterpriseBot_venv"
REPORT_FILE="$SWAP_DIR/MISSION_REPORT_V01.txt"

echo "############################################################"
echo "# [1/4] PURGE & TRANSPORT: Initializing Infrastructure..."
echo "Mission Audit Started: $(date)" > "$REPORT_FILE"

# Clean processes
pkill -9 -f "voice_sidecar_bridge.py" >> "$REPORT_FILE" 2>&1
pkill -9 -f "ngrok" >> "$REPORT_FILE" 2>&1
sleep 2

# Start ngrok
ngrok http 8081 --log=stdout >> "$REPORT_FILE" 2>&1 &

# Sync URL
echo "# [2/4] SYNC: Sychronizing Public Tunnel..."
for i in {1..15}; do
    URL=$(curl -s http://127.0.0.1:4040/api/tunnels | python3 -c "import sys, json; d=json.load(sys.stdin); print(d['tunnels'][0]['public_url'])" 2>/dev/null)
    if [ -n "$URL" ]; then
        echo "$URL" > "$PROJECT_ROOT/DOCS/SESSION/NGROK_URL.txt"
        echo "NGROK_URL: $URL" >> "$REPORT_FILE"
        echo "# [SUCCESS] URL Synchronized: $URL"
        break
    fi
    sleep 2
done

# Start Sidecar and Trigger
echo "# [3/4] IGNITION: Starting Engines and Call..."
source "$VENV_PATH/bin/activate"
python3 "$PROJECT_ROOT/voice_sidecar_bridge.py" >> "$REPORT_FILE" 2>&1 &
sleep 5
python3 "$PROJECT_ROOT/trigger_outbound_call.py" >> "$REPORT_FILE" 2>&1

# Validation Period (Increased for Audit Stability)
echo "# [4/4] AUDIT: Capturing telemetry (90 seconds). Please wait..."
sleep 90

# Cleanup and Final Report
echo "Mission Audit Completed: $(date)" >> "$REPORT_FILE"
pkill -9 -f "voice_sidecar_bridge.py"
pkill -9 -f "ngrok"

echo "############################################################"
echo "# [MISSION COMPLETE] Audit report ready in SWAP."
echo "# Use SFTP to download: $REPORT_FILE"
echo "############################################################"
