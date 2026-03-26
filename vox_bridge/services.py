# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/vox_bridge/services.py
import os
import requests
import logging
from typing import Optional
from django.conf import settings
from pydantic import BaseModel
from google import genai
from google.genai import types

# Configuración de logging para auditoría interna de procesos de audio e IA
# Logging configuration for internal auditing of audio and AI processes
logger = logging.getLogger(__name__)

class CallClassification(BaseModel):
    """
    Pydantic schema for structured output from Gemini 3.1 Pro.
    Ensures that the model returns a valid JSON for the department and transcription.
    ---
    Esquema Pydantic para la salida estructurada de Gemini 3.1 Pro.
    Asegura que el modelo devuelva un JSON válido para el departamento y la transcripción.
    """
    department: str
    transcription: str
    confidence_score: float

class AudioHandlingService:
    """
    Service dedicated to managing remote audio files from the MundoSMS bridge.
    Handles secure downloads and local temporary storage in the SWAP directory.
    ---
    Servicio dedicado a la gestión de archivos de audio remotos del puente MundoSMS.
    Gestiona descargas seguras y almacenamiento temporal local en el directorio SWAP.
    """

    @staticmethod
    def download_remote_audio(url: str, call_id: str) -> Optional[str]:
        """
        Downloads an audio file from MundoSMS and saves it to the SWAP directory.
        Uses streaming to maintain a low memory footprint.
        ---
        Descarga un archivo de audio de MundoSMS y lo guarda en el directorio SWAP.
        Usa streaming para mantener una baja huella de memoria.
        """
        target_path = os.path.join('/home/MiguelAeTxio/SWAP/', f"{call_id}.mp3")
        
        try:
            # Petición con timeout de 15 segundos para evitar bloqueos del worker
            response = requests.get(url, stream=True, timeout=15)
            response.raise_for_status()
            
            with open(target_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            logger.info(f"Audio downloaded successfully: {target_path}")
            return target_path
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error downloading audio for call {call_id}: {str(e)}")
            return None
        except IOError as e:
            logger.error(f"Disk error writing audio for call {call_id}: {str(e)}")
            return None

class GeminiAudioService:
    """
    High-level service for processing voice audio using Google Gemini 3.1 Pro API (SDK 2026).
    Integrates multimodal analysis with thinking capabilities for precise IVR routing.
    ---
    Servicio de alto nivel para procesar audio de voz usando la API de Google Gemini 3.1 Pro (SDK 2026).
    Integra análisis multimodal con capacidades de razonamiento para un enrutamiento de IVR preciso.
    """

    def __init__(self):
        """
        Initializes the GenAI client using the 2026 standards.
        The API Key must be defined in the Django settings or environment variables.
        ---
        Inicializa el cliente GenAI usando los estándares de 2026.
        La API Key debe estar definida en la configuración de Django o variables de entorno.
        """
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.model_id = "gemini-3.1-pro-preview"

    def classify_call_intent(self, audio_path: str) -> CallClassification:
        """
        Sends the audio file to Gemini for transcription and intent classification.
        Uses 'thinking_level' to enhance reasoning for ambiguous requests.
        ---
        Envía el archivo de audio a Gemini para transcripción y clasificación de intención.
        Usa 'thinking_level' para mejorar el razonamiento en peticiones ambiguas.
        """
        try:
            with open(audio_path, "rb") as audio_file:
                audio_data = audio_file.read()

            # Prompt coercitivo para asegurar cumplimiento del esquema de departamentos
            prompt = """
            ROLE: You are an expert Enterprise IVR Routing Assistant.
            INPUT: An audio recording of a customer stating their name and reason for calling.
            TASK:
            1. Transcribe the audio exactly.
            2. Classify the call into one of these specific departments: [VENTAS, SOPORTE, ADMINISTRACION].
            3. If the user mentions 'comprar', 'precio', 'presupuesto', assign to VENTAS.
            4. If the user mentions 'problema', 'error', 'ayuda técnica', assign to SOPORTE.
            5. If the user mentions 'factura', 'pago', 'recibo', assign to ADMINISTRACION.
            6. If it's silent or totally ambiguous, assign to ERROR_AMBIGUO.

            Strict adherence to the JSON schema is required.
            """

            response = self.client.models.generate_content(
                model=self.model_id,
                contents=[
                    types.Part.from_bytes(data=audio_data, mime_type="audio/mp3"),
                    prompt
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=CallClassification,
                    thinking_level="MEDIUM"
                )
            )
            
            # En el SDK 2026, si se provee response_schema, 'parsed' contiene el objeto Pydantic instanciado
            return response.parsed

        except Exception as e:
            logger.error(f"Critical error in Gemini processing: {str(e)}")
            # Fallback seguro para evitar la ruptura del flujo de la llamada
            return CallClassification(
                department="ERROR_AMBIGUO",
                transcription="No se pudo procesar la transcripción por un error técnico.",
                confidence_score=0.0
            )
