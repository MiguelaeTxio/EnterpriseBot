# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_ingestion/apps.py
"""
App configuration for document_ingestion (H23/H25 -- S024).

Hasta este commit, document_ingestion era un paquete Python plano
(ver entity_matching_service.py) porque no tenía modelos propios. Pasa
a ser una app Django registrada porque necesita IngestedFile
(models.py): el staging de un archivo subido ANTES de saber a qué
dominio (máquina/personal) ni a qué entidad pertenece -- el propio
motivo de ser de este módulo (ver entity_matching_service.py) es
resolver eso, así que tiene que existir un sitio donde vivir mientras
tanto.
"""
from django.apps import AppConfig


class DocumentIngestionConfig(AppConfig):
    """
    AppConfig for the document_ingestion application.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "document_ingestion"
    verbose_name = "Ingesta de Documentación (enrutado)"
