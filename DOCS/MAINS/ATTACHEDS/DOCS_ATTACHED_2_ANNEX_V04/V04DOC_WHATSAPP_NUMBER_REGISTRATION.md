# Registro de Número Twilio para WhatsApp — Diagnóstico, Viabilidad y Hoja de Ruta
# Última actualización: 2026-04-16

## 0. Resumen Ejecutivo

Consolidación de dos investigaciones (2026-04-13 y 2026-04-16) cotejadas
contra la documentación oficial de Twilio vigente en abril de 2026.

**Conclusión principal:** Es completamente posible registrar los números
españoles existentes (+34951796832 y +34951799117) como WhatsApp Senders
sin adquirir números adicionales. La clave es configurar temporalmente el
número con una Twilio Function mínima durante los 10-15 minutos que dura
el proceso de Embedded Signup + verificación OTP de Meta, y restaurar la
configuración IVR después. El modelo de datos ya soporta esto mediante
`capabilities=BOTH` en `PhoneNumber`.

Los Twimlets (`twimlets.com/voicemail`) están marcados como legacy/obsoletos
en 2026. El reemplazo estándar son las **Twilio Functions**.

---

## 1. Viabilidad — Estado a Abril 2026

| Afirmación | Estado |
|---|---|
| Registrar números de solo voz en WhatsApp es posible | ✅ CORRECTO |
| Meta permite verificación por llamada de voz (OTP) | ✅ CORRECTO |
| Twimlets como solución de buzón de voz | ❌ OBSOLETO |
| Twilio Functions como reemplazo estándar | ✅ CORRECTO |
| Cuenta mejorada (Upgraded) obligatoria | ✅ CORRECTO |
| Números +34 requieren dirección española | ✅ CORRECTO |
| Meta detecta IVR complejos activos durante verificación | ✅ CORRECTO |
| Desactivar IVR temporalmente permite el registro | ✅ VIABLE |
| El mismo número puede ser IVR + WhatsApp simultáneamente | ✅ CORRECTO (capabilities=BOTH) |

---

## 2. Por qué los Twimlets ya no son viables (2026)

Los Twimlets han sido marcados como legacy/obsoletos. La URL
`twilio.com/labs/twimlets` ya no devuelve contenido funcional. Además,
Meta detecta activamente los sistemas IVR y buzones de voz automatizados
durante la verificación para prevenir registros no autorizados.

Intentar usar un Twimlet durante la verificación Meta conlleva alto riesgo
de bloqueo (como ocurrió en la sesión 2026-04-13 con el exceso de intentos
fallidos).

---

## 3. Por qué la desactivación temporal del IVR es viable

La restricción de Meta aplica **en el momento de la verificación**, no de
forma permanente. Un número con una Twilio Function mínima activa cumple
el requisito sin problemas.

Flujo completo:
1. Crear una Twilio Function mínima en Console → Serverless → Services.
2. Asignarla temporalmente al número en Voice Configuration (IE1).
3. Completar el Embedded Signup en Twilio → WhatsApp Senders.
4. Recibir la llamada de Meta, escuchar el OTP e introducirlo.
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

La pausa inicial es importante — da tiempo al bot de Meta para iniciar
la locución del código antes de que comience la grabación.

Configuración en el número:
- Voice Configuration → A call comes in → Function → `/whatsapp-verify`.
- Guardar. Realizar el registro. Restaurar después.

---

## 5. Requisitos Previos

### 5.1. Cuenta Twilio
- Cuenta **mejorada (Upgraded)** obligatoria.

### 5.2. Meta Business Portfolio
- Necesario un Meta Business Portfolio verificado.
- Para el piloto (1 número): cuenta básica verificada es suficiente.

### 5.3. WhatsApp Business Account (WABA)
- Nueva WABA exclusiva para Twilio — crear durante el Embedded Signup.
- No reutilizar WABA de otro proveedor.
- Un único WABA por cuenta Twilio.

### 5.4. Número de teléfono
- No debe estar ya registrado en WhatsApp.
- Cumple regulaciones españolas — ya verificado en Twilio para ambos números ES.

---

## 6. Procedimiento Paso a Paso (método actualizado 2026-04-16)

1. **Preparar la Twilio Function** (Sección 4) antes de iniciar el registro.

2. **Coordinar ventana fuera de horario** con Grupo Álvarez (fuera de L-V 08:00-18:00).

3. **Desactivar temporalmente el webhook IVR** en +34951799117:
   - Console → Active Numbers → +34951799117.
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
   - Introducir el OTP antes de que expire (~30s).

6. **Restaurar el webhook IVR:**
   - Voice Configuration (IE1) → A call comes in → Webhook → URL del orchestrator.
   - Guardar. El IVR vuelve a estar operativo.

7. **Configurar el sender WhatsApp:**
   - Webhook entrante: `https://enterprisebot-miguelaetxio.pythonanywhere.com/api/whatsapp/incoming/`
   - Actualizar `.env`: `TWILIO_WHATSAPP_SENDER=+34951799117`.

**Notas críticas:**
- No hacer más de 1-2 intentos seguidos — Meta aplica bloqueos temporales (~72h).
- No usar VPN durante el proceso.
- El proceso completo no debería superar los 15 minutos.

---

## 7. Compatibilidad con el Modelo de Datos Actual

El modelo `PhoneNumber` ya tiene `capabilities=BOTH`. No se requieren
cambios en el modelo de datos ni migraciones adicionales.

Tras el registro:
- `+34951799117`: `capabilities=BOTH` — IVR de voz + WhatsApp.
- `+34951796832`: `capabilities=VOICE` — reservado exclusivamente para IVR.
- `TWILIO_WHATSAPP_SENDER` en `.env` → `+34951799117`.
