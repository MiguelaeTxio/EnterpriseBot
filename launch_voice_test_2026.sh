#!/bin/bash

# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/launch_voice_test_2026.sh
# EnterpriseBot Master Launcher - Milestone 1: Voice Infrastructure Field Testing.
# April 2026 Standard: Unified orchestration for Ngrok v3, Sidecar Bridge and Twilio.
# ---
# Lanzador Maestro de EnterpriseBot - Hito 1: Pruebas de Campo de Infraestructura de Voz.
# Estándar de Abril de 2026: Orquestación unificada para Ngrok v3, Sidecar Bridge y Twilio.

PROJECT_ROOT="/home/MiguelAeTxio/PROJECTS/EnterpriseBot"
URL_FILE="$PROJECT_ROOT/DOCS/SESSION/NGROK_URL.txt"
LOG_FILE="/home/MiguelAeTxio/SWAP/enterprisebot_session.log"

# 1. CLEANUP / LIMPIEZA
# Ensures a clean network state by killing ghost processes on target ports.
# Asegura un estado de red limpio finalizando procesos fantasma en los puertos objetivo.
echo "# [1/5] [CLEANUP] Preparando entorno de red 2026..."
fuser -k 8081/tcp 4041/tcp 2>/dev/null
rm -f "$URL_FILE"
rm -f "$LOG_FILE"
touch "$LOG_FILE"

# 2. ORCHESTRATION / ORQUESTACIÓN
# Launches the Python Orchestrator which manages Ngrok and the Sidecar Bridge.
# Lanza el Orquestador Python que gestiona Ngrok y el Puente Sidecar.
echo "# [2/5] [ORCHESTRATOR] Iniciando infraestructura de túnel y puente..."
python3 -u "$PROJECT_ROOT/voice_orchestrator.py" >> "$LOG_FILE" 2>&1 &
ORCH_PID=$!

# 3. TUNNEL DISCOVERY / DESCUBRIMIENTO DEL TÚNEL
# Polls for the dynamic Ngrok URL until infrastructure is ready.
# Muestrea la URL dinámica de Ngrok hasta que la infraestructura esté lista.
echo "# [3/5] [WAIT] Esperando resolución del túnel dinámico..."
MAX_RETRIES=15
COUNT=0
while [ ! -f "$URL_FILE" ] && [ $COUNT -lt $MAX_RETRIES ]; do
    sleep 2
    ((COUNT++))
    echo -n "."
done
echo ""

if [ -f "$URL_FILE" ]; then
    PUBLIC_URL=$(cat "$URL_FILE")
    echo "# [SUCCESS] Infraestructura activa en: $PUBLIC_URL"
else
    echo "# [ERROR] Fallo al iniciar el túnel. Revisa $LOG_FILE"
    kill $ORCH_PID
    exit 1
fi

# 4. OUTBOUND TRIGGER / DISPARADOR DE LLAMADA
# Stabilizes the bridge and executes the call to the validation number.
# Estabiliza el puente y ejecuta la llamada al número de validación.
echo "# [4/5] [TRIGGER] Estabilizando puente y disparando llamada Twilio..."
sleep 5 # Mandatory DSP stabilization / Estabilización DSP obligatoria
python3 "$PROJECT_ROOT/trigger_outbound_call.py"

# 5. MONITORING / MONITOREO
# Connects the terminal to the real-time interaction log.
# Conecta la terminal al registro de interacción en tiempo real.
echo "# [5/5] [MONITOR] Entrando en modo escucha activa (Ctrl+C para salir)..."
echo "-----------------------------------------------------------------------"
tail -f "$LOG_FILE"

# Graceful Exit Handler / Gestor de salida ordenada
trap "kill $ORCH_PID; echo '# [STOP] Sistema detenido.'; exit" INT TERM
