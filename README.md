# 🌍 Mappa Interattiva Nodi LoRa Brescia

[![Licenza](https://img.shields.io/badge/Licenza-MIT-green.svg)](LICENSE)
[![Versione](https://img.shields.io/badge/Versione-2.0.0-blue.svg)](https://github.com/tuusername/lorabs-map/releases)

Una mappa interattiva per visualizzare i nodi di progetti diversi in tutta Italia (Meshtastic, MeshCore, ..), con funzionalità avanzate di filtraggio e condivisione.

![Visita la Mappa](https://map.natmus.net)

## ✨ Funzionalità

- **Mappa Interattiva** con clusterizzazione automatica
- **Filtri Avanzati** per frequenza e tipo di nodo
- **Ricerca** per nome nodo con autocompletamento
- **Condivisione** visualizzazione attuale con link copiabile
- **Inserimento Nodi** tramite un semplice bot Telegram
- **Dettagli Nodo** in modal popup
- **Responsive Design** per mobile/desktop

## 📁 Struttura cartelle
```
lorabs-map/
├── web/                  # Frontend principale
│   ├── index.html        # Pagina mappa
│   ├── styles.css        
│   └── app.js            # Logica mappa
├── shared/               
│   └── dati.csv          # Database nodi (autogenerato)
├── bot/                  # Bot Telegram
│   ├── bot.py            
│   └── log_state.json    # Memorizzazione dello stato dei log (attivo/disattivo)
├── LICENSE
└── README.md
```

## 🤖 Integrazione Bot Telegram
Il codice include un bot Telegram per inserire i nodi nella mappa con funzionalità di aggiunta, modifica e rimozione marker.

### Funzionalità principali

- ✅ Aggiungi nuovi marker con coordinate, nome, descrizione e link
- ✏️ Rinomina marker esistenti
- 🗑️ Elimina marker
- 📍 Visualizza la lista dei tuoi marker
- 📊 Statistiche per admin
- 🔒 Controllo degli accessi e limiti per utente

### Limitazioni

- Ogni utente normale può avere massimo 3 marker
- Utenti speciali possono avere fino a 6 marker
- Lunghezza massima:
  - Nome: 14 caratteri
  - Descrizione: 50 caratteri
  - Link: 40 caratteri
 
### Struttura dei dati

I marker sono salvati in un file CSV con i seguenti campi:
- lat: Latitudine
- lon: Longitudine
- name: Nome del marker
- desc: Descrizione
- node_type: Tipo di nodo (Mehstastic, MeshCore, Altro)
- frequency: Frequenza (433 MHz, 868 MHz)
- link: Link aggiuntivo (opzionale)
- ID: ID Telegram dell'utente
- timestamp: Timestamp di creazione

### Comandi disponibili

| Comando | Descrizione |
|---------|-------------|
| `/start` | Mostra il menu principale |
| `/help` | Mostra la guida |
| `/add` | Aggiungi un nuovo marker |
| `/rename` | Rinomina un marker esistente |
| `/delete` | Elimina un marker |
| `/list` | Mostra la lista dei tuoi marker |
| `/admin` | Menu amministratore (solo admin) |

## To-Do
- [ ] [BOT] Invio annunci a tutti gli utenti
- [ ] [BOT] Permettere agli utenti di votare i nodi più utili/affidabili
- [ ] [BOT] Geofencing: Notifiche quando nuovi nodi vengono aggiunti nella tua area
- [ ] [BOT] Invio notifica per conferma nodi inattivi ed eventuale rimozione
- [ ] Banner "Nodi aggiunti oggi"
- [ ] Implementare inserimento layer marker da progetto LoRa Italia
- [ ] Creazione API per integrazione con MapForHam
- [ ] Modal Info Avanzate (UI)
- [ ] Dark Mode

### Requisiti tecnici

- Python 3.8+
- Librerie Python:
  - `python-telegram-bot`
  - `csv`
  - `re`
  - `os`
  - `tempfile`
  - `shutil`
  - `logging`
  - `json`
  - `time`
