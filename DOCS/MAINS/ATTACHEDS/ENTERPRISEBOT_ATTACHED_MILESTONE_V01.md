# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V01.md
# ANEXO HITO 1: INFRAESTRUCTURA DE VOZ (ESTABILIZACIÓN CRÍTICA 3.1)
# ESTADO: EN PROGRESO (BLOQUEO POR REGRESIÓN TÉCNICA RESUELTO DOCUMENTALMENTE)
# FECHA ACTUALIZACIÓN: 2026-04-04

---

## 1. AUDITORÍA DE INCAPACIDAD (SESIÓN ANTERIOR)
El agente anterior falló sistemáticamente al ignorar el estándar de abril de 2026 (SDK 1.69.0). 
- **Causa del Fallo:** Intentó inyectar datos ("Wake-up") antes de recibir la confirmación de infraestructura, violando el protocolo Setup-First de Gemini 3.1.
- **Error de Sintaxis:** Usó argumentos inválidos (input=) en send_realtime_input, ignorando la firma de la API de 2026.
- **Consecuencia:** Timeouts constantes por denegación de protocolo de Google.

## 2. HOJA DE RUTA PARA LA SIGUIENTE SESIÓN (LEY SUPREMA - FUENTE DE LA VERDAD)
El próximo agente DEBE seguir estas instrucciones sin desviarse un solo milímetro. PROHIBIDO SUPONER O INVENTAR.

### PASO 1: Implementación del Handshake Setup-First (Quirúrgico)
1.  **Ubicación:** `vox_bridge/services.py`.
2.  **Lógica Obligatoria:** 
    - El método `send_initial_greeting` **DEBE ESPERAR** el flag `setup_confirmed`. Prohibido enviar datos antes.
    - El método `listen_to_ai` **DEBE CAPTURAR** el atributo `message.setup_complete` del flujo `session.receive()`. 
    - Al detectar `message.setup_complete == True`, se debe activar `self.setup_confirmed.set()`.
3.  **Sintaxis 1.69.0:** Para enviar el saludo, usar exclusivamente: 
    `await session.send_realtime_input(text="Hola...", end_of_turn=True)`. 
    Prohibido usar `input=`, `audio=`, o cualquier otro envoltorio si el mensaje es de texto.

### PASO 2: Estabilización de Tiempos de Respuesta
1.  Establecer todos los `asyncio.wait_for` a un mínimo de **60.0 segundos**. 
2.  La infraestructura Preview de 2026 tiene un TTFT (Time to First Token) de hasta 35s. Menos de 60s causará un fallo de falso positivo por timeout.

### PASO 3: Validación de Infraestructura (Zero-Cost)
1.  Lanzar orquestador.
2.  Ejecutar `test_bridge_connectivity.py` asegurando que el script de test también siga la lógica Setup-First.
3.  Confirmar el log: "[SDK] Handshake Gemini 3.1 (SetupComplete: True) VALIDADO".

---
*Referencia Obligatoria:* ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-live-preview
*Normativa Twilio:* G.711 mu-law 8kHz -> Sidecar PCM 16kHz.
