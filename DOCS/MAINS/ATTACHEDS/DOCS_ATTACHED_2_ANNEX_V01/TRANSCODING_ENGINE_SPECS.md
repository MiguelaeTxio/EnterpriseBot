# ESPECIFICACIONES DEL MOTOR DE TRANSCODIFICACIÓN
# TRANSCODING ENGINE SPECIFICATIONS
---
# Lógica de conversión de audio y gestión de identificadores de flujo.
# Audio conversion logic and stream identifier management.

## 1. Formatos de Audio en Conflicto / Conflicting Audio Formats

| Dominio | Formato | Frecuencia | Profundidad |
|---------|---------|------------|-------------|
| **Twilio (Entrada)** | mu-law (G.711) | 8,000 Hz | 8-bit |
| **Gemini 3.1 Live** | PCM Linear | 16,000 Hz | 16-bit (Mono) |
| **Twilio (Salida)** | mu-law (G.711) | 8,000 Hz | 8-bit |

## 2. Lógica de Conversión (Lado Servidor) / Conversion Logic (Server Side)
Utilizamos la librería nativa `audioop` para minimizar la latencia:
We use the native `audioop` library to minimize latency:

- **Inbound:** `audioop.ulaw2lin(data, 2)` seguido de un remuestreo (vía padding/linear) de 8kHz a 16kHz.
- **Outbound:** Downsampling de 24kHz (nativa Gemini) a 8kHz seguido de `audioop.lin2ulaw(data, 2)`.

## 3. El Identificador Crítico: streamSid / The Critical Identifier: streamSid
Cada paquete de audio enviado hacia Twilio **DEBE** incluir el `streamSid` en la raíz del objeto JSON.
Each audio packet sent to Twilio MUST include the `streamSid` at the root of the JSON object.

```json
{
    "event": "media",
    "streamSid": "MZ...",
    "media": { "payload": "..." }
}
```

**Importancia:** Su omisión provoca el **Warning 31951** de Twilio y el descarte silencioso del audio.
**Importance:** Its omission triggers Twilio **Warning 31951** and silent audio discard.
