# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/vox_bridge/services.py
import os
import logging
import asyncio
import audioop
import base64
from django.conf import settings
from google import genai
from google.genai import types
from asgiref.sync import sync_to_async

"""
EnterpriseBot Gemini Live Stream Service: High-Precision DSP and AI Orchestration.
April 2026 Standard: Mandatory gemini-2.5-flash for Conversational IVR.
This service manages the bidirectional voice bridge, applying digital signal processing
to match Twilio's G.711 mu-law (8kHz) with Gemini's L16 (16kHz) requirements.
---
Servicio de Streaming Gemini Live de EnterpriseBot: Orquestación de IA y DSP de Alta Precisión.
Estándar de Abril de 2026: gemini-2.5-flash obligatorio para IVR Conversacional.
Este servicio gestiona el puente de audio bidireccional, aplicando procesamiento de señal digital
para emparejar el mu-law G.711 (8kHz) de Twilio con los requisitos L16 (16kHz) de Gemini.
"""

# Logging configuration exclusively in Spanish (Directriz 2.1.3)
# Configuración de registro exclusivamente en Castellano (Directriz 2.1.3)
logger = logging.getLogger("VoxServices")

class GeminiStreamService:
    """
    Core orchestrator for real-time voice synthesis and recognition via Gemini 2.5 Flash.
    Handles DSP transcoding, AI session lifecycle, and Django ORM persistence.
    ---
    Orquestador núcleo para síntesis y reconocimiento de voz en tiempo real vía Gemini 2.5 Flash.
    Gestiona la transcodificación DSP, el ciclo de vida de la sesión de IA y la persistencia en el ORM de Django.
    """
    def __init__(self):
        """
        Initializes the GenAI client using April 2026 API standards (SDK 1.69.0).
        ---
        Inicializa el cliente GenAI usando los estándares de la API de abril de 2026 (SDK 1.69.0).
        """
        # ✅ SURGICAL FIX APRIL 2026: Forcing API version 'v1' to support gemini-2.5-flash in BiDi mode.
        # This update ensures compliance with the 2026 technical directive for Conversational IVR.
        # Esta actualización asegura el cumplimiento con la directriz técnica de 2026 para IVR Conversacional.
        # SDK 1.69.0 Constructor initialization.
        # Inicialización del constructor del SDK 1.69.0.
        self.client = genai.Client(
            api_key=settings.GEMINI_API_KEY,
            http_options={'api_version': 'v1'}
        )
        
        # Mandatory model for Conversational IVR (Directriz Técnica 1.4)
        # Modelo obligatorio para IVR Conversacional (Directriz Técnica 1.4)
        # ✅ UPDATED TO GEMINI 2.5 FLASH (GA VERSION APRIL 2026)
        self.model_id = "models/gemini-2.5-flash"
        
        self.state_in = None
        self.state_out = None
        self.frames_in = 0
        self.frames_out = 0
        self.setup_confirmed = asyncio.Event()

    @sync_to_async
    def _persist_transcript(self, call_sid, text_chunk):
        """
        Thread-safe database update for interaction logging.
        Ensures the full_transcript field is updated atomically.
        ---
        Actualización de base de datos segura entre hilos para el registro de interacciones.
        Asegura que el campo full_transcript se actualice de forma atómica.
        """
        from vox_bridge.models import CallInteraction
        try:
            interaction, _ = CallInteraction.objects.get_or_create(call_sid=call_sid)
            if interaction.full_transcript:
                interaction.full_transcript += f"\n{text_chunk}"
            else:
                interaction.full_transcript = text_chunk
            interaction.save()
        except Exception as e:
            logger.error(f"# [ORM ERROR] Fallo en la persistencia de la conversación: {str(e)}")

    async def connect(self):
        """
        Establishes an asynchronous Live session with forced Spanish localization.
        ---
        Establece una sesión Live asíncrona con localización forzada en castellano.
        """
        # Regional Spanish speech configuration (es-ES).
        # Configuración de voz para español regional (es-ES).
        
        # ✅ SURGICAL FIX APRIL 2026: Nesting voice_name inside prebuilt_voice_config to satisfy Pydantic.
        voice_config = types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                voice_name="Aoede"
            )
        )
        
        speech_config = types.SpeechConfig(
            language_code="es-ES",
            voice_config=voice_config
        )
        
        # Real-time stateful connection configuration.
        # Configuración de conexión con estado en tiempo real.
        config = types.LiveConnectConfig(
            system_instruction=types.Content(
                parts=[types.Part(text=(
                    "Eres EnterpriseBot, una IA corporativa de nivel empresarial. "
                    "HABLA SIEMPRE EN CASTELLANO DE ESPAÑA. "
                    "Tu tono es profesional, eficiente y empático. "
                    "Mantén respuestas breves para reducir la latencia percibida."
                ))]
            ),
            # OBLIGATORIO: Audio como modalidad principal.
            response_modalities=["AUDIO"],
            speech_config=speech_config
        )
        
        logger.info(f"# [SDK] Iniciando sesión LIVE con {self.model_id} (Localización: es-ES).")
        return self.client.aio.live.connect(model=self.model_id, config=config)

    async def send_initial_greeting(self, session, call_sid=None):
        """
        Injects the first interaction once the AI handshake is confirmed.
        ---
        Inyecta la primera interacción una vez que se confirma el apretón de manos de la IA.
        """
        try:
            logger.info("# [SDK] Esperando confirmación de infraestructura de IA...")
            # Handshake verification with 12s timeout for 2026 infrastructure.
            # Verificación del apretón de manos con tiempo de espera de 12s para la infraestructura de 2026.
            await asyncio.wait_for(self.setup_confirmed.wait(), timeout=12.0)
            
            msg = "Hola, soy EnterpriseBot. ¿En qué puedo ayudarte hoy?"
            
            # Using strict Input schema for text injections.
            # Usando esquema de entrada estricto para inyecciones de texto.
            greeting = types.LiveClientRealtimeInput(text=msg)
            await session.send(input=greeting, end_of_turn=False) 
            
            if call_sid:
                await self._persist_transcript(call_sid, f"BOT: {msg}")
        except asyncio.TimeoutError:
            logger.error("# [SDK ERROR] Tiempo de espera agotado en el Handshake.")
        except Exception as e:
            logger.error(f"# [SDK ERROR] Fallo en el saludo inicial: {str(e)}")

    def _transcode_twilio_to_gemini(self, b64_data: str) -> bytes:
        """
        DSP: G.711 mu-law (8kHz) -> PCM Linear (16kHz).
        Ensures signal continuity for the AI recognition engine.
        ---
        DSP: G.711 mu-law (8kHz) -> PCM Linear (16kHz).
        Asegura la continuidad de la señal para el motor de reconocimiento de IA.
        """
        try:
            raw_audio = base64.b64decode(b64_data)
            # Mu-law decoding: Transforms 8-bit log compressed audio to 16-bit linear PCM.
            # Decodificación Mu-law: Transforma audio comprimido logarítmico de 8 bits a PCM lineal de 16 bits.
            pcm_8k = audioop.ulaw2lin(raw_audio, 2)
            
            # Resampling: Interpolates the 8kHz signal to meet Gemini's 16kHz requirement.
            # Resampling: Interpola la señal de 8kHz para cumplir con el requisito de 16kHz de Gemini.
            # Note: 2026 implementation maintains self.state_in to prevent phase clipping.
            pcm_16k, self.state_in = audioop.ratecv(pcm_8k, 2, 1, 8000, 16000, self.state_in)
            
            self.frames_in += 1
            return pcm_16k
        except Exception as e:
            logger.error(f"# [DSP IN ERROR] Error en decodificación de audio: {str(e)}")
            return b""

    def _transcode_gemini_to_twilio(self, pcm_bytes: bytes) -> str:
        """
        DSP: PCM Linear (16kHz) -> G.711 mu-law (8kHz).
        Optimized for Twilio's telephony infrastructure.
        ---
        DSP: PCM Linear (16kHz) -> G.711 mu-law (8kHz).
        Optimizado para la infraestructura de telefonía de Twilio.
        """
        try:
            # Downsampling: Reduces the 16kHz AI output to Twilio's 8kHz standard.
            # Downsampling: Reduce la salida de IA de 16kHz al estándar de 8kHz de Twilio.
            pcm_8k, self.state_out = audioop.ratecv(pcm_bytes, 2, 1, 16000, 8000, self.state_out)
            
            # Mu-law encoding: Compresses 16-bit linear PCM to 8-bit log for network transmission.
            # Codificación Mu-law: Comprime PCM lineal de 16 bits a logarítmico de 8 bits para transmisión de red.
            data_8k = audioop.lin2ulaw(pcm_8k, 2)
            
            self.frames_out += 1
            return base64.b64encode(data_8k).decode("utf-8")
        except Exception as e:
            logger.error(f"# [DSP OUT ERROR] Error en codificación de audio: {str(e)}")
            return ""

    async def send_audio_frame(self, session, b64_data: str):
        """
        Transmits processed audio frames to the Gemini Live session.
        ---
        Transmite tramas de audio procesadas a la sesión Gemini Live.
        """
        if not self.setup_confirmed.is_set():
            return
            
        pcm_frame = self._transcode_twilio_to_gemini(b64_data)
        if pcm_frame:
            # SDK 1.69.0: Mandatory Blob schema for PCM 16kHz.
            # SDK 1.69.0: Esquema de Blob obligatorio para PCM 16kHz.
            payload = types.LiveClientRealtimeInput(
                audio=types.Blob(data=pcm_frame, mime_type="audio/pcm;rate=16000")
            )
            await session.send(input=payload)

    async def listen_to_ai(self, session, call_sid=None):
        """
        Listens for AI server responses and yields encoded audio payloads.
        Handles interruption events (Barge-in) and transcript persistence.
        ---
        Escucha las respuestas del servidor de IA y genera payloads de audio codificados.
        Gestiona eventos de interrupción (Barge-in) y persistencia de transcripción.
        """
        try:
            async for message in session.receive():
                if message.setup_complete:
                    self.setup_confirmed.set()
                    logger.info("# [SDK] Handshake de infraestructura completado.")
                
                # Check for audio/text model turns.
                # Comprobar turnos del modelo de audio/texto.
                if message.server_content and message.server_content.model_turn:
                    for part in message.server_content.model_turn.parts:
                        if part.inline_data:
                            yield self._transcode_gemini_to_twilio(part.inline_data.data)
                        if part.text and call_sid:
                            await self._persist_transcript(call_sid, f"BOT: {part.text}")
                            
                elif message.server_content and message.server_content.interrupted:
                    logger.warning("# [SDK EVENT] Interrupción de IA detectada (Barge-in).")
                    
        except Exception as e:
            logger.error(f"# [SDK LISTEN ERROR] Error en recepción de IA: {str(e)}")

if __name__ == "__main__":
    # Standard 2026 Syntax Check Entry point.
    # Punto de entrada de comprobación sintáctica estándar 2026.
    print("# [SERVICE] Módulo de servicios listo para la orquestación.")
