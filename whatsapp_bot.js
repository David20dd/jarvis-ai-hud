const { default: makeWASocket, useMultiFileAuthState, DisconnectReason } = require('@whiskeysockets/baileys');
const express = require('express');
const QRCode = require('qrcode');
const axios = require('axios');

const app = express();
const PORT = process.env.PORT_WA || 3000;

let latestQR = null;
let isConnected = false;

// Servidor Web para mostrar el QR en pantalla
app.get('/qr', async (req, res) => {
    if (isConnected) {
        return res.send(`
            <html style="background:#020509; color:#00ff88; font-family:sans-serif; display:flex; justify-content:center; align-items:center; height:100vh;">
                <div style="text-align:center;">
                    <h1>🚀 J.A.R.V.I.S. WHATSAPP CONECTADO</h1>
                    <p>La sesión está activa y lista para recibir mensajes.</p>
                </div>
            </html>
        `);
    }

    if (!latestQR) {
        return res.send(`
            <html style="background:#020509; color:#00f2fe; font-family:sans-serif; display:flex; justify-content:center; align-items:center; height:100vh;">
                <div style="text-align:center;">
                    <h1>⌛ GENERANDO CÓDIGO QR...</h1>
                    <p>Por favor recarga la página en 5 segundos.</p>
                </div>
            </html>
        `);
    }

    try {
        const qrImage = await QRCode.toDataURL(latestQR);
        res.send(`
            <html style="background:#020509; color:#00f2fe; font-family:sans-serif; display:flex; justify-content:center; align-items:center; height:100vh;">
                <div style="text-align:center; background:rgba(0,242,254,0.1); padding:30px; border-radius:15px; border:1px solid #00f2fe;">
                    <h1 style="margin-bottom:10px;">📲 ESCANEA CON TU WHATSAPP</h1>
                    <p style="color:#fff; margin-bottom:20px;">Abre WhatsApp > Dispositivos Vinculados > Vincular dispositivo</p>
                    <img src="${qrImage}" style="width:280px; height:280px; border-radius:10px; border:4px solid #fff;" />
                </div>
            </html>
        `);
    } catch (err) {
        res.status(500).send("Error generando imagen QR");
    }
});

app.get('/', (req, res) => {
    res.send("Servidor de WhatsApp Jarvis Activo. Ve a /qr para escanear.");
});

app.listen(PORT, () => {
    console.log(`🌐 Servidor Web del QR corriendo en puerto ${PORT}`);
});

async function connectToWhatsApp() {
    const { state, saveCreds } = await useMultiFileAuthState('auth_info_baileys');
    
    const sock = makeWASocket({
        auth: state,
        browser: ['Ubuntu', 'Chrome', '20.0.04']
    });

    sock.ev.on('creds.update', saveCreds);

    sock.ev.on('connection.update', (update) => {
        const { connection, lastDisconnect, qr } = update;
        
        if (qr) {
            latestQR = qr;
            console.log("📲 Nuevo Código QR disponible en la ruta /qr");
        }

        if (connection === 'close') {
            isConnected = false;
            const shouldReconnect = (lastDisconnect.error?.output?.statusCode !== DisconnectReason.loggedOut);
            console.log('⚠️ Conexión cerrada. Reintentando...', shouldReconnect);
            if (shouldReconnect) {
                setTimeout(connectToWhatsApp, 3000);
            }
        } else if (connection === 'open') {
            isConnected = true;
            latestQR = null;
            console.log('🚀 J.A.R.V.I.S. CONECTADO A WHATSAPP EXITOSAMENTE');
        }
    });

    sock.ev.on('messages.upsert', async m => {
        const msg = m.messages[0];
        if (!msg || !msg.message || msg.key.fromMe) return;

        const sender = msg.key.remoteJid;
        const textMessage = msg.message.conversation || msg.message.extendedTextMessage?.text;

        if (textMessage) {
            console.log(`📩 Mensaje de ${sender}: ${textMessage}`);
            try {
                const response = await axios.post('https://jarvis-ai-hud.onrender.com/api/jarvis', {
                    message: textMessage,
                    session_id: sender
                });

                if (response.data && response.data.reply) {
                    await sock.sendMessage(sender, { text: response.data.reply });
                }
            } catch (err) {
                console.error("⚠️ Error llamando a Jarvis Backend:", err.message);
            }
        }
    });
}

connectToWhatsApp();
