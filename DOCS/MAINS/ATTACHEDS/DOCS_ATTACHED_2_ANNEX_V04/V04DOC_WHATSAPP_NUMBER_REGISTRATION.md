# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/DOCS_ATTACHED_2_ANNEX_V04/V04DOC_WHATSAPP_NUMBER_REGISTRATION.md
# Documento satélite del Anexo Hito 4 — EnterpriseBot
# Última actualización: 2026-04-16

---

# Registro de Número Twilio para WhatsApp — Diagnóstico, Viabilidad y Hoja de Ruta

## 0. Resumen Ejecutivo

Este documento consolida dos investigaciones realizadas en sesión (2026-04-13 y
2026-04-16) cotejadas contra la documentación oficial de Twilio vigente en abril
de 2026.

**Conclusión principal:** Es completamente posible registrar los números españoles
existentes (+34951796832 y +34951799117) como WhatsApp Senders sin adquirir
números adicionales. La clave es configurar temporalmente el número con una
Twilio Function mínima (sin IVR complejo activo) durante los 10-15 minutos que
dura el proceso de Embedded Signup + verificación OTP de Meta, y restaurar
la configuración IVR después. El modelo de datos ya soporta esto mediante
`capabilities=BOTH` en `PhoneNumber`.

Los Twimlets (`twimlets.com/voicemail`), propuestos en la investigación inicial,
están marcados como legacy/obsoletos en 2026 y no son una solución fiable.
El reemplazo estándar son las **Twilio Functions**.

---

## 1. Viabilidad — Estado a Abril 2026

| Afirmación | Fuente | Estado |
|---|---|---|
| Registrar números de solo voz en WhatsApp es posible | Twilio Docs oficial | ✅ CORRECTO |
| Meta permite verificación por llamada de voz (OTP) | Twilio Docs oficial | ✅ CORRECTO |
| Twimlets como solución de buzón de voz | twilio.com/labs/twimlets (obsoleto) | ❌ OBSOLETO |
| Twilio Functions como reemplazo estándar | Twilio Docs oficial 2026 | ✅ CORRECTO |
| Cuenta mejorada (Upgraded) obligatoria | Twilio Docs oficial | ✅ CORRECTO |
| Números +34 requieren dirección española | Regulaciones Twilio ES | ✅ CORRECTO |
| Meta detecta IVR complejos activos durante verificación | Twilio Docs oficial | ✅ CORRECTO |
| Desactivar IVR temporalmente permite el registro | Análisis técnico confirmado | ✅ VIABLE |
| El mismo número puede ser IVR + WhatsApp simultáneamente | capabilities=BOTH en BD | ✅ CORRECTO |

---

## 2. Por qué los Twimlets ya no son viables (2026)

Los Twimlets (`twimlets.com/voicemail`) han sido marcados como **legacy/obsoletos**.
La URL `twilio.com/labs/twimlets` ya no devuelve contenido funcional. Además, Meta
detecta activamente los sistemas IVR y buzones de voz automatizados durante el
proceso de verificación para prevenir registros no autorizados.

Intentar usar un Twimlet o cualquier sistema de buzón automático durante la
verificación Meta conlleva un alto riesgo de bloqueo del intento (como ocurrió
en la sesión 2026-04-13 con el exceso de intentos fallidos).

---

## 3. Por qué la desactivación temporal del IVR es viable

La restricción de Meta aplica **en el momento de la verificación**, no de forma
permanente. Meta verifica que el número puede recibir una llamada de voz y que
hay un sistema capaz de capturar el OTP dictado. Un número con una Twilio Function
mínima activa cumple este requisito sin problemas.

Flujo completo:
1. Crear una Twilio Function mínima en Console → Serverless → Services.
2. Asignarla temporalmente al número en Voice Configuration (IE1 para números ES).
3. Completar el Embedded Signup en Twilio → WhatsApp Senders.
4. Recibir la llamada de Meta, escuchar el OTP e introducirlo en el formulario.
5. Restaurar el webhook IVR del orchestrator en el número.
6. El número queda registrado como WhatsApp Sender con `capabilities=BOTH`.

Ventana de inactividad IVR estimada: **10-15 minutos**.
Coordinación necesaria: realizar fuera del horario de atención de Grupo Álvarez.

---

## 4. Twilio Function mínima para recibir el OTP

Crear en Console → Serverless → Services → New Service → New Function (`/whatsapp-verify`):

```javascript
exports.handler = function(context, event, callback) {
  const twiml = new Twilio.twiml.VoiceResponse();
  twiml.pause({ length: 2 });
  twiml.say({
    language: 'es-ES'
  }, 'Por favor, escuche el siguiente código de verificación.');
  twiml.record({
    timeout: 15,
    transcribe: true,
  });
  callback(null, twiml);
};
```

La pausa inicial es importante — da tiempo al bot de Meta para iniciar la
locución del código antes de que comience la grabación.

Configuración en el número:
- Voice Configuration → A call comes in → Function → seleccionar `/whatsapp-verify`.
- Guardar. Realizar el registro. Restaurar después.

---

## 5. Requisitos Previos

### 5.1. Cuenta Twilio
- Cuenta **mejorada (Upgraded)** obligatoria — verificar antes del registro.

### 5.2. Meta Business Portfolio
- Necesario un Meta Business Portfolio verificado.
- Para más de 2 números: verificación de negocio completa en Meta.
- Para el piloto (1 número): cuenta básica verificada es suficiente.

### 5.3. WhatsApp Business Account (WABA)
- Nueva WABA exclusiva para Twilio — crear durante el Embedded Signup.
- No reutilizar WABA de otro proveedor.
- Un único WABA por cuenta Twilio — restricción de la plataforma.

### 5.4. Número de teléfono
- No debe estar ya registrado en WhatsApp.
- Cumple regulaciones españolas — ya verificado en Twilio para ambos números ES.

---

## 6. Procedimiento Paso a Paso (método actualizado 2026-04-16)

1. **Preparar la Twilio Function** (ver Sección 4) — tener el servicio listo
   antes de iniciar el registro para minimizar la ventana de inactividad.

2. **Coordinar ventana fuera de horario** con Grupo Álvarez (fuera de L-V 08:00-18:00).

3. **Desactivar temporalmente el webhook IVR** en el número +34951799117:
   - Twilio Console → Active Numbers → +34951799117.
   - Voice Configuration (IE1) → A call comes in → Function → `/whatsapp-verify`.
   - Guardar.

4. **Iniciar el Embedded Signup:**
   - Console → Messaging → Senders → WhatsApp Senders → Create new sender.
   - Seleccionar +34951799117 → Continue with Facebook.
   - Ventana Meta: seleccionar o crear Meta Business Portfolio.
   - Crear nueva WABA específica para Twilio.
   - Introducir el número → seleccionar verificación **VOICE CALL**.

5. **Recibir y anotar el OTP:**
   - El bot de Meta llama al número.
   - La Twilio Function responde, pausa y graba.
   - Revisar logs de Twilio o transcripción para obtener el código.
   - Introducir el OTP en la ventana Meta antes de que expire (~30s).

6. **Restaurar el webhook IVR:**
   - Voice Configuration (IE1) → A call comes in → Webhook → URL del orchestrator.
   - Guardar. El IVR vuelve a estar operativo.

7. **Configurar el sender WhatsApp:**
   - Una vez registrado (status ONLINE), configurar el webhook entrante:
     `https://enterprisebot-miguelaetxio.pythonanywhere.com/api/whatsapp/incoming/`
   - Actualizar `.env`: `TWILIO_WHATSAPP_SENDER=+34951799117`.

**Notas:**
- No hacer más de 1-2 intentos seguidos — Meta aplica bloqueos temporales (~72h).
- No usar VPN durante el proceso.
- El proceso completo no debería superar los 15 minutos.

---

## 7. Compatibilidad con el Modelo de Datos Actual

El modelo `PhoneNumber` ya tiene `capabilities=BOTH` para ambos números ES.
No se requieren cambios en el modelo de datos ni migraciones adicionales.

Tras el registro:
- `+34951799117`: `capabilities=BOTH` — IVR de voz + WhatsApp.
- `+34951796832`: `capabilities=VOICE` — reservado exclusivamente para IVR.
- `TWILIO_WHATSAPP_SENDER` en `.env` → `+34951799117`.

---

## 8. Referencias Documentación Oficial (verificadas 2026-04-16)

| Documento | URL |
|---|---|
| WhatsApp Self Sign-up | `https://www.twilio.com/docs/whatsapp/self-sign-up` |
| Register Senders via API | `https://www.twilio.com/docs/whatsapp/register-senders-using-api` |
| WhatsApp Business Platform | `https://www.twilio.com/docs/whatsapp` |
| Twilio Functions (Serverless) | `https://www.twilio.com/en-us/serverless/functions` |
| WhatsApp Senders API | `https://www.twilio.com/docs/whatsapp/api/senders` |

---

*Documento generado en sesión 2026-04-16. Revisión requerida antes del Paso 1 del Hito 4.*
