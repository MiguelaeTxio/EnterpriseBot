# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/DOCS_ATTACHED_2_ANNEX_V01/V01DOC_MUNDOSMS_VIABILITY_TEST.md

# DOCUMENTO SATÉLITE: Test de Viabilidad Inbound MundoSMS
---

## 1. Introducción / Introduction
Este documento detalla la estrategia para convertir una centralita pasiva en un IVR inteligente conversacional.
This document details the strategy to convert a passive PBX into a conversational intelligent IVR.

## 2. Flujo Técnico / Technical Flow
1. **Llamada entrante**: MundoSMS ejecuta el `xmlplan` inicial.
2. **Indagación**: El bot reproduce un `<read>` de bienvenida y activa un `<record>` de 5 segundos.
3. **Webhook de Procesamiento**: MundoSMS envía el audio a Django.
4. **Discriminación IA**: 
   - Conversión Speech-to-Text (STT).
   - Inferencia de Gemini para clasificar el departamento.
5. **Respuesta Dinámica**: Django responde con un nuevo XML `<call destination="...">`.

## 3. Configuración de Gemini (Prompting)
El modelo debe actuar como un clasificador de alta precisión.
- **Entrada**: Texto transcrito.
- **Salida**: Código de departamento (VENTAS, SOPORTE, ADMIN) o ERROR si es ambiguo.

## 4. Próximos Pasos / Next Steps
Configurar el endpoint `/api/vox/inbound/` en la futura aplicación `vox_bridge`.
