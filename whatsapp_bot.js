const { default: makeWASocket, useMultiFileAuthState, DisconnectReason } = require('@whiskeysockets/baileys');
const qrcode = require('qrcode-terminal');
const axios = require('axios');

async function connectToWhatsApp() {
    const { state, saveCreds } = await useMultiFileAuthState('auth_info_baileys');
    
    const sock = makeWASocket({
        auth: state,
        printQRInTerminal: true
    });

    sock.ev.on('creds.update', saveCreds);

    sock.ev.on('connection.update', (update) => {
        const { connection, lastDisconnect, qr } = update;
        
        if (qr) {
            console.log("\n==========================================");
            console.log("📲 ESCANEA ESTE CÓDIGO QR DESDE TU WHATSAPP:");
            console.log("==========================================\n");
            qrcode.generate(qr, { small: true });
        }

        if (connection === 'close') {
            const shouldReconnect = (lastDisconnect.error?.output?.statusCode !== DisconnectReason.loggedOut);
            console.log('⚠️ Conexión cerrada. Intentando reconectar...', shouldReconnect);
            if (shouldReconnect) {
                setTimeout(connectToWhatsApp, 3000);
            }
        } else if (connection === 'open') {
            console.log('🚀 J.A.R.V.I.S. CONECTADO A WHATSAPP EXITOSAMENTE');
        }
    });

    sock.ev.on('messages.upsert', async m => {
        const msg = m.messages[0];
        if (!msg || !msg.message || msg.key.fromMe) return;

        const sender = msg.key.remoteJid;
        const textMessage = msg.message.conversation || msg.message.extendedTextMessage?.text;

        if (textMessage) {
            console.log(`📩 Consulta recibida de ${sender}: ${textMessage}`);
            try {
                const response = await axios.post('https://jarvis-ai-hud.onrender.com/api/jarvis', {
                    message: textMessage,
                    session_id: sender
                });

                if (response.data && response.data.reply) {
                    await sock.sendMessage(sender, { text: response.data.reply });
                }
            } catch (err) {
                console.error("⚠️ Error comunicando con el servidor de Jarvis:", err.message);
            }
        }
    });
}

connectToWhatsApp();
