# -*- coding: utf-8 -*-

import csv
import re
import os
import tempfile
import shutil
import logging
import json
import time
import traceback
from telegram.constants import ParseMode
from telegram import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove, Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters, ConversationHandler, JobQueue

############################################
#                                          #
#                 COSTANTI                 #
#                                          #
############################################

# Configurazione file e percorsi
FILE = "shared/dati.csv"
ENCODING = "utf-8"
LOG_STATE_FILE = "log_state.json"

# Limiti di input
MAX_NAME_LENGTH = 14
MAX_DESC_LENGTH = 50
MAX_LINK_LENGTH = 40
MAX_MARKERS_PER_USER = 3
MAX_MARKERS_FOR_SPECIAL_USERS = 6

# Timeout conversazioni
TIMEOUT_SECONDS = 300  # 5 minuti
TIMEOUT_CHECK_INTERVAL = 60

# Utenti speciali (da usare come array numerici)
ADMIN_IDS = [1608289624]  # ID Telegram degli admin
SPECIAL_USERS = [1608289624]  # ID Telegram degli utenti speciali

# Opzioni predefinite
NODE_TYPES = ["Mehstastic", "MeshCore", "Altro"]
FREQUENCIES = ["433 MHz", "868 MHz"]

# Messaggi del bot
MESSAGES = {
    "start": "👋 <b>Benvenuto!</b> Scegli un'azione:\n\n"
             "➕ Aggiungi marker (massimo 3) - /add\n"
             "✏️ Rinomina marker - /rename\n"
             "🗑️ Elimina marker - /delete\n"
             "📍 Lista marker - /list",
    "unknown_command": "Comando non riconosciuto. Usa /help per la lista dei comandi",
    "operation_in_progress": "Hai già un'operazione in corso. Completa prima quella",
    "max_markers_reached": f"Hai già {MAX_MARKERS_PER_USER} marker. Elimina uno per aggiungerne un altro",
    "no_markers": "Non hai ancora aggiunto marker",
    "no_markers_to_rename": "Non hai marker da rinominare",
    "no_markers_to_delete": "Non hai marker da eliminare",
    "marker_added": "✅ Marker aggiunto con successo!",
    "marker_deleted": "🗑️ Marker eliminato",
    "name_updated": "✅ Nome aggiornato!",
    "invalid_selection": "❌ Selezione non valida",
    "invalid_name": "❌ Nome non valido",
    "name_too_long": f"❌ Il nome è troppo lungo. Massimo {MAX_NAME_LENGTH} caratteri",
    "desc_too_long": f"❌ La descrizione è troppo lunga. Massimo {MAX_DESC_LENGTH} caratteri",
    "link_too_long": f"❌ Il link è troppo lungo. Massimo {MAX_LINK_LENGTH} caratteri",
    "invalid_link": "❌ Il link non è valido. Deve iniziare con http:// o https://",
    "duplicate_name": "❌ Hai già un marker con questo nome. Ripeti l'operazione e usa un nome diverso",
    "add_lat": "📍 Inserisci la latitudine oppure invia la posizione:",
    "add_lon": "Inserisci la longitudine:",
    "add_name": f"🔤 Inserisci il nome del marker (max {MAX_NAME_LENGTH} caratteri):",
    "enter_description": f"✏️ Inserisci una descrizione (max {MAX_DESC_LENGTH} caratteri):",
    "add_link_ask": "🔗 Vuoi aggiungere un link?",
    "add_link": "Inserisci il link:",
    "rename_select": "Quale marker vuoi rinominare?\n\n",
    "rename_new_name": "🔤 Inserisci il nuovo nome:",
    "delete_select": "Quale marker vuoi eliminare?\n\n",
    "your_markers": "I tuoi marker:\n\n",
    "no_markers_left": "Non hai più marker salvati",
    "select_node_type": "📡 Seleziona il tipo di nodo:",
    "select_frequency": "📶 Seleziona la frequenza di utilizzo:",
    "select_freq_kbd": "❌ Seleziona una frequenza valida dalla tastiera",
    "not_authorized": "⛔ Accesso negato",
    "error_generic": "❌ Si è verificato un errore. Segnala il problema a un admin",
    "error_position": "❌ Valore non valido. Invia la posizione o inserisci le coordinate manualmente",
    "error_value": "❌ Valore non valido",
    "error_select": "❌ Errore nella selezione",
    "timed_out": "⏳ Sessione scaduta per inattività. Usa /start per ricominciare.",
    "cancelled": "❌ Operazione annullata"
}

# Stati del ConversationHandler
(
    ADD_LAT, ADD_LON, ADD_NAME, ADD_DESC, ADD_LINK_ASK, 
    ADD_LINK, RENAME_SELECT, RENAME_NEW_NAME, DELETE_SELECT, 
    SELECT_NODE_TYPE, SELECT_FREQUENCY, ENTER_DESCRIPTION
) = range(12)

def load_log_state():
    try:
        with open(LOG_STATE_FILE, 'r') as f:
            return json.load(f).get('enabled', True)
    except:
        return True

def save_log_state(enabled):
    with open(LOG_STATE_FILE, 'w') as f:
        json.dump({'enabled': enabled}, f)

LOG_ENABLED = load_log_state()

################################################
#                                              #
#             FUNZIONI DI SERVIZIO             #
#                                              #
################################################

# Handler per timeout della chat
def check_timeout(user_id):
    """Verifica se è scaduto il timeout per un'operazione."""
    user_id = str(user_id)
    if user_id not in user_data or 'timestamp' not in user_data[user_id]:
        return True  # Considera scaduto se non esiste il timestamp
    
    elapsed = time.time() - user_data[user_id]['timestamp']
    return elapsed > TIMEOUT_SECONDS

async def timeout_checker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce il timeout globale."""
    uid = str(update.effective_user.id)
    if uid in user_data and check_timeout(uid):
        await update.message.reply_text(
            MESSAGES["timed_out"],
            reply_markup=ReplyKeyboardRemove()
        )
        user_data.pop(uid, None)
        return ConversationHandler.END
    return None

async def cleanup_timeout(context: ContextTypes.DEFAULT_TYPE):
    """Pulizia periodica delle sessioni scadute."""
    now = time.time()
    expired = [uid for uid, data in user_data.items() 
               if now - data.get('timestamp', 0) > TIMEOUT_SECONDS]
    
    for uid in expired:
        user_data.pop(uid, None)

# Configurazione logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

def clean_text(text):
    """Pulisce il testo rimuovendo caratteri speciali SENZA limitare la lunghezza"""
    text = text.strip('"\'')  # Rimuove apici all'inizio/fine
    text = re.sub(r'[^\w\s\-.,!?@#&%â‚¬:/\U0001F300-\U0001FAFF]', '', text, flags=re.UNICODE)
    return text

def is_valid_url(url):
    """Verifica se una stringa è un URL valido."""
    return re.match(r'^https?://[^\s]+$', url)

def read_markers():
    """Legge tutti i marker dal file CSV."""
    if not os.path.exists(FILE):
        return []
    
    with open(FILE, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        if reader.fieldnames and reader.fieldnames[0].startswith('\ufeff'):
            reader.fieldnames[0] = reader.fieldnames[0].replace('\ufeff', '')
        
        fieldnames = ['lat', 'lon', 'name', 'desc', 'node_type', 'frequency', 'link', 'ID', 'user', 'timestamp']
        markers = []
        
        for row in reader:
            if not row.get('lat') or not row.get('lon') or not row.get('ID'):
                continue
            
            marker = {field: row.get(field, '') for field in fieldnames}
            if not marker['user']:
                marker['user'] = 'anonimo'
                
            markers.append(marker)
        
        return markers

def safe_write_markers(markers):
    """Scrive i marker su file in modo sicuro con file temporaneo."""
    fieldnames = ['lat', 'lon', 'name', 'desc', 'node_type', 'frequency', 'link', 'ID', 'user', 'timestamp']
    
    temp_file = tempfile.NamedTemporaryFile('w', newline='', delete=False, encoding='utf-8-sig')
    with temp_file as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for marker in markers:
            clean_marker = {field: marker.get(field, '') for field in fieldnames}
            writer.writerow(clean_marker)
    
    shutil.move(temp_file.name, FILE)

# -------------- MENU ADMIN --------------

async def send_log_to_admins(context: ContextTypes.DEFAULT_TYPE, message: str):
    """Invia un messaggio di log a tutti gli admin se i log sono abilitati"""
    global LOG_ENABLED
    if not LOG_ENABLED:
        return
        
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=f"📢 LOG:\n{message}"
            )
        except Exception as e:
            logging.error(f"Errore invio log all'admin {admin_id}: {e}")

async def admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu di gestione per admin"""
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text(MESSAGES["not_authorized"])
        return
    
    keyboard = [
        [InlineKeyboardButton("🔈 Abilita Log", callback_data="log_on")],
        [InlineKeyboardButton("🔇 Disabilita Log", callback_data="log_off")],
        [InlineKeyboardButton("📊 Statistiche", callback_data="stats")],
        [InlineKeyboardButton("📤 Esporta dati", callback_data="export")]
    ]
    
    await update.message.reply_text(
        "🛠️ *Menu Admin*:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# Handler per i pulsanti inline
async def admin_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce tutte le azioni dal menu admin"""
    global LOG_ENABLED
    
    query = update.callback_query
    await query.answer()  # Chiude l'indicatore di caricamento
    
    # Verifica che l'utente sia un admin
    if query.from_user.id not in ADMIN_IDS:
        await query.edit_message_text(MESSAGES["not_authorized"])
        return
    
    # Gestione delle diverse azioni
    if query.data == "log_on":
        LOG_ENABLED = True
        save_log_state(True)  # Salva lo stato su file
        await query.edit_message_text(
            "✅ Log abilitati\n\n"
            "Tutte le azioni degli utenti verranno inviate agli admin",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Torna al menu", callback_data="back_to_menu")]
            ])
        )
        
    elif query.data == "log_off":
        LOG_ENABLED = False
        save_log_state(False)  # Salva lo stato su file
        await query.edit_message_text(
            "❌ Log disabilitati\n\n"
            "Nessuna notifica verrà inviata agli admin",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Torna al menu", callback_data="back_to_menu")]
            ])
        )
        
    elif query.data == "stats":
        await admin_stats(update, context)
        
    elif query.data == "export":
        await admin_export(update, context)
        
    elif query.data == "back_to_menu":
        # Ricrea il menu principale
        keyboard = [
            [InlineKeyboardButton("🔈 Abilita Log" if not LOG_ENABLED else "🔇 Disabilita Log", 
             callback_data="log_off" if LOG_ENABLED else "log_on")],
            [InlineKeyboardButton("📊 Statistiche", callback_data="stats")],
            [InlineKeyboardButton("📤 Esporta dati", callback_data="export")]
        ]
        await query.edit_message_text(
            "🛠️ *Menu Admin* - Stato log: " + ("✅ ON" if LOG_ENABLED else "❌ OFF"),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra le statistiche agli admin."""
    query = update.callback_query
    await query.answer()  # Chiude l'indicatore di caricamento
    
    if query.from_user.id not in ADMIN_IDS:
        await query.edit_message_text(MESSAGES["not_authorized"])
        return

    markers = read_markers()
    total_markers = len(markers)
    
    # Statistiche utenti
    users = {}
    for marker in markers:
        user_id = marker['ID']
        users[user_id] = users.get(user_id, 0) + 1
    
    top_users = sorted(users.items(), key=lambda x: x[1], reverse=True)[:5]
    markers_with_links = sum(1 for m in markers if m['link'])
    
    # Costruisci il messaggio
    stats_message = (
        "📊 <b>Statistiche Admin</b>\n\n"
        f"📍 <b>Marker totali:</b> {total_markers}\n"
        f"👥 <b>Utenti unici:</b> {len(users)}\n"
        f"🔗 <b>Marker con link:</b> {markers_with_links} ({markers_with_links/total_markers:.1%})\n\n"
        "🏆 <b>Top contributor:</b>\n"
    )
    
    for i, (user_id, count) in enumerate(top_users, 1):
        user_info = next((m for m in markers if m['ID'] == user_id), None)
        username = f"@{user_info['user']}" if user_info and user_info.get('user') else f"Utente #{user_id}"
        stats_message += f"{i}. {username}: {count} marker\n"
    
    stats_message += (
        f"\n⭐ <b>Utenti speciali:</b> {sum(1 for uid in users if int(uid) in SPECIAL_USERS)}\n"
        f"🔢 <b>Max marker per utente:</b> {MAX_MARKERS_PER_USER} (normali), {MAX_MARKERS_FOR_SPECIAL_USERS} (speciali)"
    )
    
    await query.edit_message_text(
        stats_message, 
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Torna al menu", callback_data="back_to_menu")]
        ])
    )

async def admin_export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Esporta tutti i marker in un file CSV."""
    query = update.callback_query
    await query.answer()  # Chiude l'indicatore di caricamento
    
    if query.from_user.id not in ADMIN_IDS:
        await query.edit_message_text(MESSAGES["not_authorized"])
        return
    
    try:
        with open(FILE, 'rb') as f:
            await context.bot.send_document(
                chat_id=query.from_user.id,
                document=f,
                filename='markers_export.csv',
                caption='📤 Esportazione completa dei marker'
            )
        await query.edit_message_text(
            "✅ File esportato con successo!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Torna al menu", callback_data="back_to_menu")]
            ])
        )
    except Exception as e:
        logging.error(f"Errore esportazione: {str(e)}")
        await query.edit_message_text(MESSAGES["error_generic"])


#########################################
#                                       #
#          HANDLER DEI COMANDI          #
#                                       #
#########################################

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce il comando /start."""
    uid = str(update.effective_user.id)
    
    if uid in user_data and 'state' in user_data[uid]:
        if check_timeout(uid):
            user_data.pop(uid, None)
        else:
            await update.message.reply_text(MESSAGES["operation_in_progress"])
            return ConversationHandler.END

    await update.message.reply_text(
        MESSAGES["start"],
        parse_mode=ParseMode.HTML
    )

async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce il comando /help."""
    await start(update, context)

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce comandi sconosciuti."""
    await update.message.reply_text(MESSAGES["unknown_command"])

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if isinstance(context.error, TimeoutError):
        uid = str(update.effective_user.id)
        user_data.pop(uid, None)
        await update.message.reply_text(
            MESSAGES["timed_out"],
            reply_markup=ReplyKeyboardRemove()
        )
    else:
        logging.error(f"Errore: {context.error}")

#######################################################
#                                                     #
#       HANDLER AGGIUNTA MARKER (CONVERSAZIONE)       #
#                                                     #
#######################################################

async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Avvia il processo di aggiunta marker."""
    uid = str(update.effective_user.id)

    # Controllo timeout
    timeout_resp = await timeout_checker(update, context)
    if timeout_resp == ConversationHandler.END:
        return ConversationHandler.END
    
    # Controllo se un'altra operazione è in corso
    if uid in user_data and 'state' in user_data[uid]:
        await update.message.reply_text(MESSAGES["operation_in_progress"])
        return ConversationHandler.END
    
    markers = read_markers()
    user_markers = [m for m in markers if m['ID'] == uid]
    max_markers = MAX_MARKERS_FOR_SPECIAL_USERS if int(uid) in SPECIAL_USERS else MAX_MARKERS_PER_USER

    if len(user_markers) >= max_markers:
        await update.message.reply_text(MESSAGES["max_markers_reached"])
        return ConversationHandler.END
    
    user_data[uid] = {'state': 'adding', 'timestamp': time.time()}
    await update.message.reply_text(MESSAGES["add_lat"])
    return ADD_LAT

async def add_lat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce l'inserimento della latitudine."""
    uid = str(update.effective_user.id)  # Converti a stringa per consistenza
    
    try:
        # Inizializza user_data se non esiste
        if uid not in user_data:
            user_data[uid] = {'state': 'adding', 'timestamp': time.time()}
        
        # Se l'utente ha inviato la posizione
        if update.message.location:
            user_data[uid].update({
                'lat': update.message.location.latitude,
                'lon': update.message.location.longitude
            })
            logging.info(f"Posizione ricevuta da {uid}: {user_data[uid]['lat']}, {user_data[uid]['lon']}")
            
            await update.message.reply_text(MESSAGES["add_name"])
            return ADD_NAME
        
        # Se l'utente ha inserito manualmente la latitudine
        try:
            lat = float(update.message.text)
            user_data[uid]['lat'] = lat
            await update.message.reply_text(MESSAGES["add_lon"])
            return ADD_LON
            
        except ValueError:
            await update.message.reply_text(MESSAGES["error_position"])
            return ADD_LAT
            
    except Exception as e:
        logging.error(f"Errore in add_lat per {uid}: {str(e)}", exc_info=True)
        await update.message.reply_text(MESSAGES["error_generic"])
        user_data.pop(uid, None)
        return ConversationHandler.END

async def add_lon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce l'inserimento della longitudine."""
    uid = str(update.effective_user.id)
    
    try:
        if uid not in user_data or 'lat' not in user_data[uid]:
            await update.message.reply_text(MESSAGES["error_generic"])
            user_data.pop(uid, None)
            return ConversationHandler.END
            
        lon = float(update.message.text)
        user_data[uid]['lon'] = lon
        
        logging.info(f"Coordinate complete per {uid}: {user_data[uid]['lat']}, {user_data[uid]['lon']}")
        
        await update.message.reply_text(MESSAGES["add_name"])
        return ADD_NAME
        
    except ValueError:
        await update.message.reply_text(MESSAGES["error_value"])
        return ADD_LON
    except Exception as e:
        logging.error(f"Errore in add_lon per {uid}: {str(e)}", exc_info=True)
        await update.message.reply_text(MESSAGES["error_generic"])
        user_data.pop(uid, None)
        return ConversationHandler.END

async def add_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce l'inserimento del nome del marker."""
    uid = str(update.effective_user.id)  # Converti sempre a stringa
    
    try:
        # Verifica che esista il record utente
        if uid not in user_data:
            await update.message.reply_text(MESSAGES["error_generic"])
            return ConversationHandler.END

        name = clean_text(update.message.text)
        
        # Controllo lunghezza nome
        if len(name) > MAX_NAME_LENGTH:
            await update.message.reply_text(MESSAGES["name_too_long"])
            return ADD_NAME

        # Controllo duplicati
        existing_markers = read_markers()
        user_markers = [m for m in existing_markers if str(m['ID']) == uid]  # Confronta come stringa
        
        if any(m['name'].lower() == name.lower() for m in user_markers):
            await update.message.reply_text(MESSAGES["duplicate_name"])
            user_data.pop(uid, None)
            return ConversationHandler.END

        # Salva il nome
        user_data[uid]['name'] = name
        user_data[uid]['timestamp'] = time.time()  # Aggiorna timestamp
        
        # Mostra tastiera per selezione tipo nodo
        reply_keyboard = [[node_type] for node_type in NODE_TYPES]
        await update.message.reply_text(
            MESSAGES["select_node_type"],
            reply_markup=ReplyKeyboardMarkup(
                reply_keyboard,
                one_time_keyboard=True,
                resize_keyboard=True,
                input_field_placeholder="Scegli il tipo..."
            )
        )
        return SELECT_NODE_TYPE

    except Exception as e:
        logging.error(f"Errore in add_name per {uid}: {str(e)}", exc_info=True)
        await update.message.reply_text(MESSAGES["error_generic"])
        logging.error(traceback.format_exc())
        user_data.pop(uid, None)
        return ConversationHandler.END

async def select_node_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce la selezione del tipo di nodo."""
    uid = str(update.effective_user.id)
    
    try:
        node_type = update.message.text
        if node_type not in NODE_TYPES:
            await update.message.reply_text(
                MESSAGES["invalid_selection"],
                reply_markup=ReplyKeyboardMarkup(
                    [[node] for node in NODE_TYPES],
                    one_time_keyboard=True,
                    resize_keyboard=True
                )
            )
            return SELECT_NODE_TYPE
        
        user_data[uid]['node_type'] = node_type
        
        # Crea tastiera per frequenze
        freq_keyboard = ReplyKeyboardMarkup(
            [[freq] for freq in FREQUENCIES],
            one_time_keyboard=True,
            resize_keyboard=True,
            input_field_placeholder="Seleziona frequenza..."
        )
        
        await update.message.reply_text(
            MESSAGES["select_frequency"],
            reply_markup=freq_keyboard
        )
        return SELECT_FREQUENCY
        
    except Exception as e:
        logging.error(f"Errore in select_node_type per {uid}: {str(e)}")
        await update.message.reply_text(MESSAGES["error_select"])
        user_data.pop(uid, None)
        return ConversationHandler.END

# Gestire la selezione della frequenza
async def select_frequency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    frequency = update.message.text
    if frequency not in FREQUENCIES:
        await update.message.reply_text(MESSAGES["select_freq_kbd"])
        return SELECT_FREQUENCY
    
    user_data[uid]['frequency'] = frequency
    
    # Rimuovi la tastiera e passa alla descrizione libera
    await update.message.reply_text(
        MESSAGES["enter_description"],
        reply_markup=ReplyKeyboardRemove()
    )
    return ENTER_DESCRIPTION

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        MESSAGES["cancelled"],
        reply_markup=ReplyKeyboardRemove()
    )
    user_data.pop(update.effective_user.id, None)
    return ConversationHandler.END
    
# Gestire la descrizione libera
async def enter_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce l'inserimento della descrizione."""
    uid = str(update.effective_user.id)
    
    try:
        free_desc = clean_text(update.message.text)
        if len(free_desc) > MAX_DESC_LENGTH:
            await update.message.reply_text(
                MESSAGES["desc_too_long"],
                reply_markup=ReplyKeyboardRemove()
            )
            user_data.pop(uid, None)
            return ConversationHandler.END
        
        user_data[uid]['desc'] = free_desc
        
        # Crea tastiera per scelta link
        link_keyboard = ReplyKeyboardMarkup(
            [["Si", "No"]],
            one_time_keyboard=True,
            resize_keyboard=True,
            input_field_placeholder="Vuoi aggiungere un link?"
        )
        
        await update.message.reply_text(
            MESSAGES["add_link_ask"],
            reply_markup=link_keyboard
        )
        return ADD_LINK_ASK
        
    except Exception as e:
        logging.error(f"Errore in enter_description per {uid}: {str(e)}")
        await update.message.reply_text(MESSAGES["error_generic"])
        user_data.pop(uid, None)
        return ConversationHandler.END

async def add_link_ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)

    if update.message.text.lower() in ["si", "sì"]:
        await update.message.reply_text(
            MESSAGES["add_link"],
            reply_markup=ReplyKeyboardRemove()  # Assicura che non ci siano tastiere attive
        )
        return ADD_LINK
    else:
        user_data[uid]['link'] = ""
        return await finish_add(update, context)

async def add_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    link = update.message.text.strip()

    if len(link) > MAX_LINK_LENGTH:
        await update.message.reply_text(
            MESSAGES["link_too_long"],
            reply_markup=ReplyKeyboardRemove()
        )
    if not is_valid_url(link):
        await update.message.reply_text(
            MESSAGES["invalid_link"],
            reply_markup=ReplyKeyboardRemove()
        )
        return ADD_LINK

    user_data[uid]['link'] = link
    return await finish_add(update, context)

async def finish_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Completa il processo di aggiunta marker."""
    uid = str(update.effective_user.id)
    try:
        if uid not in user_data:
            await update.message.reply_text(MESSAGES["error_generic"])
            return ConversationHandler.END

        marker = user_data[uid]
        
        # Verifica campi obbligatori
        required_fields = ['lat', 'lon', 'name', 'node_type', 'frequency', 'desc']
        for field in required_fields:
            if field not in marker:
                await update.message.reply_text(f"❌ Manca il campo: {field}")
                return ConversationHandler.END

        # Completa con i campi aggiuntivi
        marker.update({
            'ID': uid,
            'user': update.effective_user.username or "anonimo",
            'link': marker.get('link', ''),
            'timestamp': int(time.time())
        })

        # Salvataggio
        markers = read_markers()
        markers.append(marker)
        safe_write_markers(markers)

        if LOG_ENABLED:  # Solo se i log sono abilitati
            log_message = (
                f"➕ Marker aggiunto\n"
                f"👤 Utente: {update.effective_user.username or 'anonimo'} (ID: {uid})\n"
                f"📍 Nome: {marker['name']}\n"
                f"📡 Tipo: {marker['node_type']}\n"
                f"📶 Frequenza: {marker['frequency']}\n"
            )
            if marker['link']:
                log_message += f"🔗 Link: {marker['link']}\n"
            await send_log_to_admins(context, log_message)


        await update.message.reply_text(MESSAGES["marker_added"])
        return ConversationHandler.END

    except Exception as e:
        logging.error(f"Errore in finish_add: {str(e)}")
        await update.message.reply_text(MESSAGES["error_generic"])
        return ConversationHandler.END
    finally:
        if uid in user_data:
            user_data.pop(uid)

#############################################
#                                           #
#               ALTRI HANDLER               #
#                                           #
#############################################

# RENAME
async def rename(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)

    # Controllo timeout
    timeout_resp = await timeout_checker(update, context)
    if timeout_resp == ConversationHandler.END:
        return ConversationHandler.END

    # Controllo se un'altra operazione è in corso
    if uid in user_data and 'state' in user_data[uid]:
        await update.message.reply_text(MESSAGES["operation_in_progress"])
        return ConversationHandler.END
        
    markers = [m for m in read_markers() if m['ID'] == uid]
    if not markers:
        await update.message.reply_text(MESSAGES["no_markers_to_rename"])
        return ConversationHandler.END
        
    msg = MESSAGES["rename_select"] + "\n".join(f"{i+1}. {m['name']}" for i, m in enumerate(markers))
    await update.message.reply_text(msg)
    user_data[uid] = {'markers': markers, 'state': 'renaming', 'timestamp': time.time()}
    return RENAME_SELECT

async def rename_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    try:
        idx = int(update.message.text.strip()) - 1
        if idx < 0 or idx >= len(user_data[uid]['markers']):
            raise ValueError
    except:
        await update.message.reply_text(MESSAGES["invalid_selection"])
        return RENAME_SELECT
    user_data[uid]['selected'] = idx
    await update.message.reply_text(MESSAGES["rename_new_name"])
    return RENAME_NEW_NAME

async def rename_new_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    idx = user_data[uid]['selected']
    new_name = update.message.text.strip().strip('"')

    if not new_name:
        await update.message.reply_text(MESSAGES["invalid_name"])
        return RENAME_NEW_NAME

    if len(new_name) > MAX_NAME_LENGTH:
        await update.message.reply_text(MESSAGES["name_too_long"])
        return RENAME_NEW_NAME

    if any(m['name'] == new_name for m in read_markers() if m['ID'] == uid):
        await update.message.reply_text(MESSAGES["duplicate_name"])
        user_data.pop(uid, None)
        return ConversationHandler.END

    markers = read_markers()
    count = -1
    old_name = None
    for m in markers:
        if m['ID'] == uid:
            count += 1
            if count == idx:
                old_name = m['name']  # Memorizza il vecchio nome prima di aggiornare
                m['name'] = new_name
                break

    safe_write_markers(markers)

    # Invia log agli admin
    if LOG_ENABLED:
        log_message = f"✏️ Marker rinominato\n"
        log_message += f"👤 Utente: {update.effective_user.username or 'anonimo'} (ID: {uid})\n"
        if old_name:
            log_message += f"📛 Vecchio nome: {old_name}\n"
        log_message += f"🆕 Nuovo nome: {new_name}\n"
        await send_log_to_admins(context, log_message)

    user_data.pop(uid, None)
    await update.message.reply_text(MESSAGES["name_updated"])
    return ConversationHandler.END

# DELETE
async def delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)

    # Controllo timeout
    timeout_resp = await timeout_checker(update, context)
    if timeout_resp == ConversationHandler.END:
        return ConversationHandler.END

    # Controllo se un'altra operazione è in corso
    if uid in user_data and 'state' in user_data[uid]:
        await update.message.reply_text(MESSAGES["operation_in_progress"])
        return ConversationHandler.END
        
    markers = [m for m in read_markers() if m['ID'] == uid]
    if not markers:
        await update.message.reply_text(MESSAGES["no_markers_to_delete"])
        return ConversationHandler.END
        
    msg = MESSAGES["delete_select"] + "\n".join(f"{i+1}. {m['name']}" for i, m in enumerate(markers))
    await update.message.reply_text(msg)
    user_data[uid] = {'state': 'deleting', 'markers': markers, 'timestamp': time.time()}
    return DELETE_SELECT

async def delete_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    idx = int(update.message.text.strip()) - 1
    all_markers = read_markers()
    count = -1
    to_delete = None
    deleted_marker = None

    for i, m in enumerate(all_markers):
        if m['ID'] == uid:
            count += 1
            if count == idx:
                to_delete = i
                deleted_marker = m
                break
    if to_delete is not None:
        del all_markers[to_delete]
        safe_write_markers(all_markers)

        if LOG_ENABLED:
            log_message = f"🗑️ Marker eliminato\n"
            log_message += f"👤 Utente: {update.effective_user.username or 'anonimo'} (ID: {uid})\n"
            log_message += f"📍 Nome: {deleted_marker['name']}\n"
            if deleted_marker['link']:
                log_message += f"🔗 Link: {deleted_marker['link']}\n"
            await send_log_to_admins(context, log_message)

        await update.message.reply_text(MESSAGES["marker_deleted"])
        
        updated = [m for m in read_markers() if m['ID'] == uid]
        if updated:
            msg = MESSAGES["your_markers"]
            for m in updated:
                msg += f"• {m['name']}"
                if m['link']:
                    msg += f" → {m['link']}"
                msg += "\n"
        else:
            msg = MESSAGES["no_markers_left"]
        await update.message.reply_text(msg)
    else:
        await update.message.reply_text(MESSAGES["error_generic"])
    user_data.pop(uid, None)
    return ConversationHandler.END

# LIST
async def list_markers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    if uid in user_data and 'state' in user_data[uid]:
        await update.message.reply_text(MESSAGES["operation_in_progress"])
        return ConversationHandler.END
        
    markers = [m for m in read_markers() if m['ID'] == uid]
    if not markers:
        await update.message.reply_text(MESSAGES["no_markers"])
    else:
        msg = MESSAGES["your_markers"]
        for m in markers:
            msg += f"• {m['name']}"
            if m['link']:
                msg += f" → {m['link']}"
            msg += "\n"
        await update.message.reply_text(msg)

############################################
#                                          #
#                   MAIN                   #
#                                          #
############################################

if __name__ == '__main__':
    # Inizializza i dati utente
    user_data = {}

    # Crea l'applicazione
    token = os.getenv("BOT_TOKEN")
    # app = ApplicationBuilder().token(token).build()
    app = (
        ApplicationBuilder()
        .token(token)
        .read_timeout(30)
        .write_timeout(30)
        .concurrent_updates(True)
        .job_queue(JobQueue())  # <-- Aggiungi questa linea
        .build()
    )

    # Configura i ConversationHandler
    add_conv = ConversationHandler(
        entry_points=[CommandHandler("add", add)],
        states={
            ADD_LAT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_lat),
                MessageHandler(filters.LOCATION, add_lat),
            ],
            ADD_LON: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_lon)],
            ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_name)],
            SELECT_NODE_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_node_type)],
            SELECT_FREQUENCY: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_frequency)],
            ENTER_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_description)],
            ADD_LINK_ASK: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_link_ask)],
            ADD_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_link)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        conversation_timeout=TIMEOUT_SECONDS,
        per_user=True
    )

    rename_conv = ConversationHandler(
        entry_points=[CommandHandler("rename", rename)],
        states={
            RENAME_SELECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, rename_select)],
            RENAME_NEW_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, rename_new_name)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        conversation_timeout=TIMEOUT_SECONDS,
        per_user=True
    )

    delete_conv = ConversationHandler(
        entry_points=[CommandHandler("delete", delete)],
        states={
            DELETE_SELECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_select)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        conversation_timeout=TIMEOUT_SECONDS,
        per_user=True
    )

    # Registra gli handler
    app.add_handler(CallbackQueryHandler(
        admin_button_handler, 
        pattern="^(log_on|log_off|stats|export|back_to_menu)$"
    ))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help))
    app.add_handler(CommandHandler("list", list_markers))
    app.add_handler(CommandHandler("stats", admin_stats))
    app.add_handler(CommandHandler("admin", admin_menu))
    app.add_handler(CommandHandler("export", admin_export))
    app.add_handler(add_conv)
    app.add_handler(rename_conv)
    app.add_handler(delete_conv)
    app.add_handler(MessageHandler(filters.COMMAND, unknown))
    app.add_error_handler(error_handler)

    # Controllo periodico timeout
    app.job_queue.run_repeating(
        cleanup_timeout,
        interval=TIMEOUT_CHECK_INTERVAL,
        first=10
    )
    
    # Avvia il bot
    app.run_polling()