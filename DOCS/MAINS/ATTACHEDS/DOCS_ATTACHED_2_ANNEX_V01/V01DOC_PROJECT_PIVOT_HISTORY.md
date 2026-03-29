# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/DOCS_ATTACHED_2_ANNEX_V01/V01DOC_PROJECT_PIVOT_HISTORY.md

# BITÁCORA DE PIVOTAJES ESTRATÉGICOS: SISTEMA DE VOZ
# PROYECTO: EnterpriseBot
# ESTADO: DOCUMENTO DE TRAZABILIDAD TÉCNICA

---

## 1. INTRODUCCIÓN Y PROPÓSITO
Este documento registra el proceso de toma de decisiones técnicas para la infraestructura de voz. Su objetivo es documentar el razonamiento tras cada cambio de proveedor y configuración, evitando la pérdida de conocimiento durante el desarrollo del Hito 1.

## 2. CRONOLOGÍA DE ITERACIONES

### ITERACIÓN 01: MUNDOSMS (MARZO 2026)
- **Motivo de Pivotaje:** Limitaciones en la bidireccionalidad en tiempo real y latencia crítica en el procesamiento de audio.

### ITERACIÓN 02: TWILIO US TRIAL (MARZO 2026)
- **Motivo de Pivotaje:** Fallo en la señalización internacional por falta de Geo-Permissions y restricciones de cuenta gratuita.

### ITERACIÓN 03: VOXIMPLANT (MARZO 2026)
- **Motivo de Pivotaje:** Pausa estratégica para centralizar el control en Twilio Media Streams tras adquirir mayor conocimiento de la red.

### ITERACIÓN 04: TWILIO UK (POST-UPGRADE)
- **Motivo de Pivotaje:** Muro regulatorio inesperado ("Regulatory Bundle") para numeración móvil de Reino Unido incluso en cuentas Paid.

### ITERACIÓN 05: TWILIO US PAID / REGION IE1 (ACTUAL)
- **Estado:** ACTIVO. Uso del número +1 260 346 6780. Optimización regional en Irlanda (IE1) para mínima latencia con Gemini 3.1 Pro.
