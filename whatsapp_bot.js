const { default: makeWASocket, useMultiFileAuthState, DisconnectReason } = require('@whiskeysockets/baileys');
const axios = require('axios');

const BACKEND_URL = 'https://jarvis-ai-hud.onrender.com';

async function connectToWhatsApp() {
    const { state, saveCreds } = await useMultiFileAuthState('auth_info_baileys');
    
    const sock = makeWASocket({
        auth: state,
        browser: ['Ubuntu', 'Chrome', '20.0.04']
    });

    sock.ev.on('creds.update', saveCreds);

    sock.ev.on('connection.update', async (update) => {
        const { connection, lastDisconnect, qr } = update;
        
        if (qr) {
            console.log("📲 Código QR recibido, actualizando en backend...");
            try {
                await axios.post(`${BACKEND_URL}/api/whatsapp/update_qr`, {
                    qr_raw: qr,
                    connected: false
                });
            } catch (err) {
                console.error("Error enviando QR al backend:", err.message);
            }
        }

        if (connection === 'close') {
            const shouldReconnect = (lastDisconnect.error?.output?.statusCode !== DisconnectReason.loggedOut);
            console.log('⚠️ Conexión cerrada. Reintentando...', shouldReconnect);
            try {
                await axios.post(`${BACKEND_URL}/api/whatsapp/update_qr`, {
                    connected: false
                });
            } catch (err) {}
            
            if (shouldReconnect) {
                setTimeout(connectToWhatsApp, 3000);
            }
        } else if (connection === 'open') {
            console.log('🚀 J.A.R.V.I.S. CONECTADO A WHATSAPP EXITOSAMENTE');
            try {
                await axios.post(`${BACKEND_URL}/api/whatsapp/update_qr`, {
                    connected: true,
                    qr_raw: null
                });
            } catch (err) {}
        }
    });

    sock.ev.on('messages.upsert', async m => {
        const msg = m.messages[0];
        if (!msg || !msg.message || msg.key.fromMe) return;

        const sender = msg.key.remoteJid;
        const textMessage = msg.message.conversation || msg.message.extendedTextMessage?.text;

        if (textMessage) {
            console.log(`📩 Mensaje recibido de ${sender}: ${textMessage}`);
            try {
                const response = await axios.post(`${BACKEND_URL}/api/jarvis`, {
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
