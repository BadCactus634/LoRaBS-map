# -*- coding: utf-8 -*-

import csv
import re
import os
import tempfile
import shutil
import logging
from telegram.constants import ParseMode
from telegram import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove, Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters, ConversationHandler

# Constants
FILE = "shared/dati.csv"
ENCODING = "utf-8"
MAX_NAME_LENGTH = 14
MAX_DESC_LENGTH = 50
MAX_LINK_LENGTH = 40
MAX_MARKERS_PER_USER = 3
ADMIN_IDS = [1608289624]  # ID Telegram degli admin
SPECIAL_USERS = [1608289624]  # ID Telegram degli utenti speciali
MAX_MARKERS_FOR_SPECIAL_USERS = 6
NODE_TYPES = ["Mehstastic", "MeshCore", "Altro"]
FREQUENCIES = ["433 MHz", "868 MHz"]

# Messages
MESSAGES = {
    "start": "👋 <b>Benvenuto!</b> Scegli un'azione:\n\n"
             "➕ Aggiungi marker - /add\n"
             "✏️ Rinomina marker - /rename\n"
             "🗑️ Elimina marker - /delete\n"
             "📍 Lista marker - /list\n"
             "ℹ️ Help - /help",
    "unknown_command": "Comando non riconosciuto. Usa /help per la lista dei comandi.",
    "operation_in_progress": "Hai già un'operazione in corso. Completa o annulla prima quella.",
    "max_markers_reached": f"Hai già {MAX_MARKERS_PER_USER} marker. Elimina uno per aggiungerne un altro.",
    "no_markers": "Non hai ancora aggiunto marker.",
    "no_markers_to_rename": "Non hai marker da rinominare.",
    "no_markers_to_delete": "Non hai marker da eliminare.",
    "marker_added": "Marker aggiunto con successo!",
    "marker_deleted": "Marker eliminato.",
    "name_updated": "Nome aggiornato!",
    "invalid_selection": "Selezione non valida.",
    "invalid_name": "Nome non valido.",
    "name_too_long": f"Il nome è troppo lungo. Massimo {MAX_NAME_LENGTH} caratteri.",
    "desc_too_long": f"La descrizione è troppo lunga. Massimo {MAX_DESC_LENGTH} caratteri.",
    "link_too_long": f"Il link è troppo lungo. Massimo {MAX_LINK_LENGTH} caratteri.",
    "invalid_link": "Il link non è valido. Deve iniziare con http:// o https://",
    "duplicate_name": "Hai già un marker con questo nome. Ripeti l'operazione",
    "add_lat": "Inserisci la latitudine oppure invia la posizione:",
    "add_lon": "Inserisci la longitudine:",
    "add_name": f"Inserisci il nome del marker (max {MAX_NAME_LENGTH} caratteri):",
    "add_desc": f"Inserisci una descrizione (max {MAX_DESC_LENGTH} caratteri):",
    "add_link_ask": "Vuoi aggiungere un link?",
    "add_link": "Inserisci il link:",
    "rename_select": "Quale marker vuoi rinominare?\n\n",
    "rename_new_name": "Inserisci il nuovo nome:",
    "delete_select": "Quale marker vuoi eliminare?\n\n",
    "your_markers": "I tuoi marker:\n\n",
    "no_markers_left": "Non hai più marker salvati.",
    "deletion_error": "Errore durante l'eliminazione.",
    "select_node_type": "📡 Seleziona il tipo di nodo:",
    "select_frequency": "📶 Seleziona la frequenza di utilizzo:",
    "enter_description": "✏️ Inserisci una descrizione (max 50 caratteri):"
}

# Log
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Stati del ConversationHandler
ADD_LAT, ADD_LON, ADD_NAME, ADD_DESC, ADD_LINK_ASK, ADD_LINK, RENAME_SELECT, RENAME_NEW_NAME, DELETE_SELECT, SELECT_NODE_TYPE, SELECT_FREQUENCY, ENTER_DESCRIPTION = range(12)

# Dati utente temporanei
user_data = {
    'lat': float,
    'lon': float,
    'name': str,
    'node_type': str,
    'frequency': str,
    'desc': str,
    'link': str
}

# Crea il file dati.csv solo se non esiste
if not os.path.exists(FILE):
    with open(FILE, "w", newline='', encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=['lat', 'lon', 'name', 'desc', 'link', 'ID', 'user', 'type', 'freq'])
        writer.writeheader()

####################################################
#                                                  #
# ---------- DEFINIZIONI FUNZIONI ASYNC ---------- #
#                                                  #
####################################################

# Invio log agli admin
async def send_log_to_admins(context: ContextTypes.DEFAULT_TYPE, message: str):
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(chat_id=admin_id, text=message)
        except Exception as e:
            logging.error(f"Errore nell'invio del log all'admin {admin_id}: {e}")

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Accesso negato. Non sei un amministratore.")
        return

    markers = read_markers()
    total_markers = len(markers)
    
    # Statistiche utenti
    users = {}
    for marker in markers:
        user_id = marker['ID']
        users[user_id] = users.get(user_id, 0) + 1
    
    top_users = sorted(users.items(), key=lambda x: x[1], reverse=True)[:5]  # Top 5 utenti
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
    
    # Aggiungi statistiche special users
    special_users_count = sum(1 for uid in users if int(uid) in SPECIAL_USERS)
    stats_message += (
        f"\n⭐ <b>Utenti speciali:</b> {special_users_count}\n"
        f"🔢 <b>Max marker per utente:</b> {MAX_MARKERS_PER_USER} (normali), {MAX_MARKERS_FOR_SPECIAL_USERS} (speciali)"
    )
    
    await update.message.reply_text(stats_message, parse_mode=ParseMode.HTML)

async def admin_export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Accesso negato")
        return
    
    # Crea e invia il file CSV
    with open(FILE, 'rb') as f:
        await update.message.reply_document(
            document=f,
            filename='markers_export.csv',
            caption='📤 Esportazione completa dei marker'
        )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.error(f"Errore: {context.error}")
    if update.message:
        await update.message.reply_text("❌ Si è verificato un errore. Riprova.")

def read_markers():
    with open(FILE, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        if reader.fieldnames and reader.fieldnames[0].startswith('\ufeff'):
            reader.fieldnames[0] = reader.fieldnames[0].replace('\ufeff', '')

        fieldnames = ['lat', 'lon', 'name', 'desc', 'node_type', 'frequency', 'link', 'ID', 'user']
        markers = []
        for row in reader:
            if not row.get('lat') or not row.get('lon') or not row.get('ID'):
                continue
            
            # Normalizza i campi
            marker = {field: row.get(field, '') for field in fieldnames}
            if not marker['user']:
                marker['user'] = 'anonimo'
                
            markers.append(marker)

        return markers

def safe_write_markers(markers):
    fieldnames = ['lat', 'lon', 'name', 'desc', 'node_type', 'frequency', 'link', 'ID', 'user']
    temp_file = tempfile.NamedTemporaryFile('w', newline='', delete=False, encoding='utf-8-sig')
    with temp_file as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for marker in markers:
            # Assicura che tutti i campi siano presenti
            clean_marker = {field: marker.get(field, '') for field in fieldnames}
            writer.writerow(clean_marker)
    shutil.move(temp_file.name, FILE)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    if uid in user_data and 'state' in user_data[uid]:
        await update.message.reply_text(MESSAGES["operation_in_progress"])
        return ConversationHandler.END

    await update.message.reply_text(
        MESSAGES["start"],
        parse_mode=ParseMode.HTML
    )

async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(MESSAGES["unknown_command"])

# CONTROLLO URL
def is_valid_url(url):
    return re.match(r'^https?://[^\s]+$', url)

# AGGIUNTA MARKER
async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    if uid in user_data and 'state' in user_data[uid]:
        await update.message.reply_text(MESSAGES["operation_in_progress"])
        return ConversationHandler.END
    
    markers = read_markers()
    user_markers = [m for m in markers if m['ID'] == uid]

    # Controllo se è un utente speciale
    max_markers = MAX_MARKERS_FOR_SPECIAL_USERS if int(uid) in SPECIAL_USERS else MAX_MARKERS_PER_USER

    if len(user_markers) >= max_markers:
        await update.message.reply_text(f"Hai già {max_markers} marker. Elimina uno per aggiungerne un altro.")
        return ConversationHandler.END
    
    await update.message.reply_text(MESSAGES["add_lat"])
    return ADD_LAT

async def add_lat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.location:
        lat = update.message.location.latitude
        lon = update.message.location.longitude
        user_data[update.effective_user.id] = {'lat': lat, 'lon': lon}
        await update.message.reply_text(MESSAGES["add_name"])
        return ADD_NAME

    try:
        lat = float(update.message.text)
        user_data[update.effective_user.id] = {'lat': lat}
        await update.message.reply_text(MESSAGES["add_lon"])
        return ADD_LON
    except (ValueError, TypeError):
        await update.message.reply_text("Valore non valido. " + MESSAGES["add_lat"])
        return ADD_LAT

async def add_lon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        lon = float(update.message.text)
        user_data[update.effective_user.id]['lon'] = lon
        await update.message.reply_text(MESSAGES["add_name"])
        return ADD_NAME
    except ValueError:
        await update.message.reply_text("Valore non valido. " + MESSAGES["add_lon"])
        return ADD_LON

def clean_text(text, max_len=50):
    text = text.strip('"')
    text = re.sub(r'[^\w\s\-.,!?@#&%â‚¬:/]', '', text)
    return text[:max_len]

async def add_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        uid = update.effective_user.id
        name = update.message.text.strip().strip('"').strip("'")
        
        # Controllo lunghezza nome
        if len(name) > MAX_NAME_LENGTH:
            await update.message.reply_text(MESSAGES["name_too_long"])
            return ADD_NAME

        # Controllo duplicati
        existing_markers = read_markers()
        user_markers = [m for m in existing_markers if m['ID'] == uid]
        if any(m['name'].lower() == name.lower() for m in user_markers):
            await update.message.reply_text(MESSAGES["duplicate_name"])
            user_data.pop(uid, None)
            return ConversationHandler.END

        # Conserva tutti i dati esistenti
        user_data[uid]['name'] = name
        
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
        logging.error(f"Errore in add_name: {str(e)}")
        await update.message.reply_text("❌ Errore durante l'operazione")
        return ConversationHandler.END

async def select_node_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        node_type = update.message.text
        if node_type not in NODE_TYPES:
            await update.message.reply_text("Seleziona un tipo valido dalla tastiera")
            return SELECT_NODE_TYPE
        
        # Conserva tutti i dati esistenti
        user_data[update.effective_user.id]['node_type'] = node_type
        
        reply_keyboard = [[freq] for freq in FREQUENCIES]
        await update.message.reply_text(
            MESSAGES["select_frequency"],
            reply_markup=ReplyKeyboardMarkup(
                reply_keyboard,
                one_time_keyboard=True,
                resize_keyboard=True
            )
        )
        return SELECT_FREQUENCY
    except Exception as e:
        logging.error(f"Errore in select_node_type: {str(e)}")
        await update.message.reply_text("❌ Errore nella selezione tipo nodo")
        return ConversationHandler.END

# Gestire la selezione della frequenza
async def select_frequency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    frequency = update.message.text
    if frequency not in FREQUENCIES:
        await update.message.reply_text("Seleziona una frequenza valida dalla tastiera")
        return SELECT_FREQUENCY
    
    user_data[update.effective_user.id]['frequency'] = frequency
    
    # Rimuovi la tastiera e passa alla descrizione libera
    await update.message.reply_text(
        MESSAGES["enter_description"],
        reply_markup=ReplyKeyboardRemove()
    )
    return ENTER_DESCRIPTION

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Operazione annullata",
        reply_markup=ReplyKeyboardRemove()
    )
    user_data.pop(update.effective_user.id, None)
    return ConversationHandler.END
    
# Gestire la descrizione libera
async def enter_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    free_desc = update.message.text.strip().strip('"').strip("'")
    if len(free_desc) > MAX_DESC_LENGTH:
        await update.message.reply_text(MESSAGES["desc_too_long"])
        return ENTER_DESCRIPTION
    
    # Salva i campi separatamente
    user_data[update.effective_user.id]['desc'] = free_desc  # Solo la parte libera
    # node_type e frequency sono già salvati nei passaggi precedenti
    
    reply_keyboard = [["Si", "No"]]
    await update.message.reply_text(
        MESSAGES["add_link_ask"], 
        reply_markup=ReplyKeyboardMarkup(
            reply_keyboard,
            one_time_keyboard=True,
            resize_keyboard=True,
            input_field_placeholder="Scegli un'opzione..."
        )
    )
    return ADD_LINK_ASK

async def add_link_ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "Si":
        await update.message.reply_text(MESSAGES["add_link"])
        return ADD_LINK
    else:
        user_data[update.effective_user.id]['link'] = ""
        return await finish_add(update, context)

async def add_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    link = update.message.text.strip()

    if len(link) > MAX_LINK_LENGTH:
        await update.message.reply_text(MESSAGES["link_too_long"])
        return ADD_LINK
    if not is_valid_url(link):
        await update.message.reply_text(MESSAGES["invalid_link"])
        return ADD_LINK

    user_data[update.effective_user.id]['link'] = link
    return await finish_add(update, context)

async def finish_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    try:
        if update.effective_user.id not in user_data:
            await update.message.reply_text("❌ Dati non trovati. Usa /add per ricominciare")
            return ConversationHandler.END

        marker = user_data[update.effective_user.id]
        
        # Verifica presenza di tutti i campi obbligatori
        required_fields = ['lat', 'lon', 'name', 'node_type', 'frequency', 'desc']
        for field in required_fields:
            if field not in marker:
                await update.message.reply_text(f"❌ Manca il campo: {field}")
                return ConversationHandler.END

        # Completa con i campi aggiuntivi
        marker.update({
            'ID': uid,
            'user': update.effective_user.username or "anonimo",
            'link': marker.get('link', '')
        })

        # Salvataggio
        markers = read_markers()
        markers.append(marker)
        safe_write_markers(markers)

        # Invia conferma
        await update.message.reply_text(MESSAGES["marker_added"])
        user_data.pop(uid, None)
        return ConversationHandler.END

    except Exception as e:
        logging.error(f"Errore in finish_add: {str(e)}")
        await update.message.reply_text("❌ Errore durante il salvataggio")
        user_data.pop(uid, None)
        return ConversationHandler.END
    finally:
        if uid in user_data:
            user_data.pop(uid)

# RENAME
async def rename(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    if uid in user_data and 'state' in user_data[uid]:
        await update.message.reply_text(MESSAGES["operation_in_progress"])
        return ConversationHandler.END
        
    markers = [m for m in read_markers() if m['ID'] == uid]
    if not markers:
        await update.message.reply_text(MESSAGES["no_markers_to_rename"])
        return ConversationHandler.END
        
    msg = MESSAGES["rename_select"] + "\n".join(f"{i+1}. {m['name']}" for i, m in enumerate(markers))
    await update.message.reply_text(msg)
    user_data[uid] = {'markers': markers, 'state': 'renaming'}
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
    for m in markers:
        if m['ID'] == uid:
            count += 1
            if count == idx:
                m['name'] = new_name
                break

    safe_write_markers(markers)

    # Invia log agli admin
    log_message = f"✏️ Marker rinominato\n"
    log_message += f"👤 Utente: {update.effective_user.username or 'anonimo'} (ID: {uid})\n"
    log_message += f"📛 Vecchio nome: {old_name}\n"
    log_message += f"🆕 Nuovo nome: {new_name}\n"
    await send_log_to_admins(context, log_message)

    user_data.pop(uid, None)
    await update.message.reply_text(MESSAGES["name_updated"])
    return ConversationHandler.END

# DELETE
async def delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    if uid in user_data and 'state' in user_data[uid]:
        await update.message.reply_text(MESSAGES["operation_in_progress"])
        return ConversationHandler.END
        
    markers = [m for m in read_markers() if m['ID'] == uid]
    if not markers:
        await update.message.reply_text(MESSAGES["no_markers_to_delete"])
        return ConversationHandler.END
        
    msg = MESSAGES["delete_select"] + "\n".join(f"{i+1}. {m['name']}" for i, m in enumerate(markers))
    await update.message.reply_text(msg)
    user_data[uid] = {'markers': markers}
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

        # Invia log agli admin
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
        await update.message.reply_text(MESSAGES["deletion_error"])
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

if __name__ == '__main__':
    # Crea l'applicazione
    token = os.getenv("BOT_TOKEN")
    app = ApplicationBuilder().token(token).build()

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
        fallbacks=[]
    )

    rename_conv = ConversationHandler(
        entry_points=[CommandHandler("rename", rename)],
        states={
            RENAME_SELECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, rename_select)],
            RENAME_NEW_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, rename_new_name)],
        },
        fallbacks=[]
    )

    delete_conv = ConversationHandler(
        entry_points=[CommandHandler("delete", delete)],
        states={
            DELETE_SELECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_select)],
        },
        fallbacks=[]
    )

    # Registra gli handler
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_stats))
    app.add_handler(CommandHandler("help", help))
    app.add_handler(CommandHandler("export", admin_export))
    app.add_handler(CommandHandler("list", list_markers))
    app.add_error_handler(error_handler)
    app.add_handler(add_conv)
    app.add_handler(rename_conv)
    app.add_handler(delete_conv)
    app.add_handler(MessageHandler(filters.COMMAND, unknown))
    
    # Avvia il bot
    app.run_polling()