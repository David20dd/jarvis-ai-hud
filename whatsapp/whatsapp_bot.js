'use strict';

const { default: makeWASocket, useMultiFileAuthState, DisconnectReason, fetchLatestBaileysVersion } = require('@whiskeysockets/baileys');
const axios = require('axios');
const pino = require('pino');

const BACKEND_URL = (process.env.JARVIS_BACKEND_URL || 'https://jarvis-ai-hud.onrender.com').replace(/\/$/, '');
const ACCESS_KEY = process.env.JARVIS_ACCESS_KEY || '';
const AUTH_DIRECTORY = process.env.WHATSAPP_AUTH_DIRECTORY || 'auth_info_baileys';
const logger = pino({ level: process.env.LOG_LEVEL || 'info' });

function apiHeaders() {
  return ACCESS_KEY ? { 'X-Jarvis-Access-Key': ACCESS_KEY } : {};
}

async function notifyBackend(payload) {
  try {
    await axios.post(`${BACKEND_URL}/api/whatsapp/update_qr`, payload, {
      headers: apiHeaders(),
      timeout: 15000,
    });
  } catch (error) {
    logger.warn({ message: error.message }, 'No se pudo actualizar el estado de WhatsApp en el backend');
  }
}

function extractText(message) {
  if (!message) return '';
  return (
    message.conversation ||
    message.extendedTextMessage?.text ||
    message.imageMessage?.caption ||
    message.videoMessage?.caption ||
    ''
  ).trim();
}

async function connectToWhatsApp() {
  const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIRECTORY);
  const { version } = await fetchLatestBaileysVersion();

  const socket = makeWASocket({
    auth: state,
    version,
    logger,
    browser: ['JARVIS MAX', 'Chrome', '3.0.0'],
    markOnlineOnConnect: false,
    syncFullHistory: false,
  });

  socket.ev.on('creds.update', saveCreds);

  socket.ev.on('connection.update', async update => {
    const { connection, lastDisconnect, qr } = update;

    if (qr) {
      logger.info('Código QR recibido');
      await notifyBackend({ qr_raw: qr, connected: false });
    }

    if (connection === 'open') {
      logger.info('J.A.R.V.I.S. conectado a WhatsApp');
      await notifyBackend({ connected: true, qr_raw: null });
      return;
    }

    if (connection === 'close') {
      await notifyBackend({ connected: false });
      const statusCode = lastDisconnect?.error?.output?.statusCode;
      const shouldReconnect = statusCode !== DisconnectReason.loggedOut;
      logger.warn({ statusCode, shouldReconnect }, 'Conexión de WhatsApp cerrada');
      if (shouldReconnect) setTimeout(connectToWhatsApp, 5000);
    }
  });

  socket.ev.on('messages.upsert', async event => {
    const message = event.messages?.[0];
    if (!message?.message || message.key.fromMe) return;

    const sender = message.key.remoteJid;
    const text = extractText(message.message);
    if (!sender || !text) return;

    try {
      const response = await axios.post(
        `${BACKEND_URL}/api/jarvis`,
        { message: text, session_id: `whatsapp:${sender}`, files: [] },
        { headers: { ...apiHeaders(), 'Content-Type': 'application/json' }, timeout: 120000 }
      );
      const reply = response.data?.reply || 'No fue posible generar una respuesta.';
      await socket.sendMessage(sender, { text: reply });
    } catch (error) {
      logger.error({ message: error.message }, 'Error procesando mensaje de WhatsApp');
      await socket.sendMessage(sender, { text: '⚠️ El núcleo de J.A.R.V.I.S. está temporalmente ocupado. Intenta nuevamente en unos minutos.' });
    }
  });
}

connectToWhatsApp().catch(error => {
  logger.fatal({ message: error.message }, 'No fue posible iniciar el puente de WhatsApp');
  process.exitCode = 1;
});
