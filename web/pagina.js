
// Variabile globale per le statistiche
const appStats = {
  totalNodes: 0,
  uniqueUsers: 0,
  lastUpdate: null
};

// Variabili per la funzione di ricerca nodi, le funzioni di ricerca sono alla fine
let allMarkersData = []; // Memorizza tutti i dati dei marker
const searchInput = document.getElementById('searchInput');
const searchResults = document.getElementById('searchResults');

// Funzione per aggiornare le statistiche nell'header
function updateHeaderStats() {
  document.getElementById('nodeCount').textContent = appStats.totalNodes;
  document.getElementById('userCount').textContent = appStats.uniqueUsers;
  document.getElementById('lastUpdate').textContent = appStats.lastUpdate ? 
    new Date(appStats.lastUpdate).toLocaleTimeString('it-IT') : 'N/D';
}

// Inizializzazione mappa con migliori impostazioni predefinite
const map = L.map('map', {
  preferCanvas: true, // Migliora le prestazioni con molti marker
  zoomControl: false // Aggiungeremo il nostro personalizzato
}).setView([45.5397, 10.2206], 10);

// Aggiungi controllo zoom personalizzato in basso a destra
L.control.zoom({
  position: 'bottomright'
}).addTo(map);

// Layer mappa con migliori opzioni
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  maxZoom: 19,
  detectRetina: true
}).addTo(map);

// Cluster per gestire meglio molti marker
const markersCluster = L.markerClusterGroup({
  maxClusterRadius: 60,
  spiderfyOnMaxZoom: true,
  showCoverageOnHover: false,
  zoomToBoundsOnClick: true,
  iconCreateFunction: function(cluster) {
    const count = cluster.getChildCount();
    return L.divIcon({
      html: `<div><span>${count}</span></div>`,
      className: 'cluster-icon',
      iconSize: L.point(40, 40)
    });
  }
});
map.addLayer(markersCluster);

let currentMarkers = [];
let activeFilters = {
  frequency: null,
  node_type: null
};
let autoRefreshInterval;
const statusBar = document.getElementById('statusBar');
const statusText = document.getElementById('statusText');
const statusIcon = statusBar.querySelector('i');

// Funzione per aggiornare la barra di stato
function updateStatus(type, message) {
  statusBar.style.display = 'flex';
  statusText.textContent = message;
  
  // Rimuovi tutte le classi di stato
  statusIcon.className = 'fas';
  statusBar.className = 'status-bar';
  
  switch(type) {
    case 'loading':
      statusIcon.classList.add('fa-circle-notch', 'fa-spin');
      statusBar.classList.add('status-updating');
      break;
    case 'success':
      statusIcon.classList.add('fa-check-circle');
      statusBar.classList.add('status-success');
      // Nascondi dopo 3 secondi
      setTimeout(() => {
        if (!statusBar.classList.contains('status-updating')) {
          statusBar.style.display = 'none';
        }
      }, 3000);
      break;
    case 'error':
      statusIcon.classList.add('fa-exclamation-circle');
      statusBar.classList.add('status-error');
      break;
  }
}

// Funzione per formattare il contenuto del popup
function formatPopupContent(row) {
  let content = `<div class="map-popup">
    <b>${row.name || 'Nodo LoRa'}</b>`;
  
  if (row.node_type) content += `<p><i class="fas fa-microchip"></i> Tipo: ${row.node_type}</p>`;
  if (row.frequency) content += `<p><i class="fas fa-wave-square"></i> Freq: ${row.frequency}</p>`;
  if (row.desc) content += `<p><i class="fas fa-info-circle"></i> ${row.desc}</p>`;
  
  if (row.link) {
    content += `<p><i class="fas fa-external-link-alt"></i> <a href="${row.link}" target="_blank">Maggiori informazioni</a></p>`;
  }
  
  if (row.user) {
    const username = row.user.startsWith('@') ? row.user : `@${row.user}`;
    content += `<p><i class="fas fa-user"></i> Utente: <a href="https://t.me/${username.replace('@', '')}" target="_blank">${username}</a></p>`;
  }
  
  if (row.timestamp) {
    const date = new Date(parseInt(row.timestamp) * 1000);
    const formattedDate = date.toLocaleDateString('it-IT');
    const formattedTime = date.toLocaleTimeString('it-IT');
    content += `<p class="timestamp-info"><i class="far fa-calendar-alt"></i> Inserito il ${formattedDate} alle ${formattedTime}</p>`;
  }
  
  content += `</div>`;
  return content;
}

// Funzione per formattare la data
function formatDate(dateString) {
  if (!dateString) return 'N/D';
  try {
    const date = new Date(dateString);
    return date.toLocaleString('it-IT');
  } catch {
    return dateString;
  }
}

// Funzione per analizzare il CSV con gestione delle virgole nei valori
function parseCSV(csvText) {
  const lines = csvText.split('\n').filter(line => line.trim() !== '');
  if (lines.length < 2) return [];
  
  const headers = lines[0].split(',').map(h => h.trim());
  const results = [];
  
  // Regex migliorata per gestire valori con virgole e caratteri speciali
  const csvRegex = /(?:,|\n|^)("(?:(?:"")*[^"]*)*"|[^",\n]*|(?:\n|$))/g;
  
  for (let i = 1; i < lines.length; i++) {
    const line = lines[i];
    const values = [];
    let match;
    
    // Reset regex e trova tutti i match
    csvRegex.lastIndex = 0;
    while ((match = csvRegex.exec(line)) !== null) {
      if (match.index === csvRegex.lastIndex) {
        csvRegex.lastIndex++;
      }
      
      let value = match[0];
      if (value.startsWith(',')) {
        value = value.substring(1);
      }
      
      // Gestione dei valori tra virgolette
      if (value.startsWith('"') && value.endsWith('"')) {
        value = value.substring(1, value.length - 1)
                  .replace(/""/g, '"'); // Sostituisce doppie virgolette
      }
      
      values.push(value.trim());
    }
    
    const row = {};
    headers.forEach((header, index) => {
      row[header] = (values[index] || '').trim();
    });
    
    results.push(row);
  }
  
  return results;
}

async function loadMarkers() {
  const refreshBtn = document.querySelector('.refresh-btn');
  refreshBtn.classList.add('loading');
  updateStatus('loading', 'Caricamento dati in corso...');
  
  try {
    const response = await fetch('/shared/dati.csv?t=' + Date.now());
    if (!response.ok) throw new Error(`Errore HTTP: ${response.status}`);
    
    const csv = await response.text();
    const data = parseCSV(csv);
    allMarkersData = data; // Salva tutti i dati per la ricerca
    
    // Calcola le statistiche
    const uniqueUsers = new Set(data.map(row => row.user || row.ID));
    appStats.totalNodes = data.length;
    appStats.uniqueUsers = uniqueUsers.size;
    appStats.lastUpdate = new Date();
    
    // Aggiorna l'header
    updateHeaderStats();
    
    // Memorizza la vista corrente prima di aggiornare i marker
    const currentZoom = map.getZoom();
    const currentCenter = map.getCenter();

    // Rimuovi i vecchi marker
    markersCluster.clearLayers();
    currentMarkers = [];

    // Filtra e aggiungi i nuovi marker
    const validMarkers = data.filter(row => {
      const lat = parseFloat(row.lat);
      const lon = parseFloat(row.lon);
      return !isNaN(lat) && !isNaN(lon);
    });

    if (validMarkers.length === 0) {
      updateStatus('error', 'Nessun dato valido trovato');
      return;
    }

    validMarkers.forEach(row => {
      const lat = parseFloat(row.lat);
      const lon = parseFloat(row.lon);
      
      const marker = L.marker([lat, lon], {
        title: row.name || 'Nodo LoRa',
        riseOnHover: true,
        data: row
      }).bindPopup(formatPopupContent(row));
      
      currentMarkers.push(marker);
    });

    markersCluster.addLayers(currentMarkers);

    // Ripristina la vista precedente invece di zoommare sui marker
    map.setView(currentCenter, currentZoom);
        
        updateStatus('success', `Caricati ${validMarkers.length} nodi`);
    
  } catch (error) {
    console.error("Errore nel caricamento:", error);
    updateStatus('error', `Errore: ${error.message}`);
  } finally {
    refreshBtn.classList.remove('loading');
  }

  if (window.initFilters) initFilters();

}

// Gestione dell'aggiornamento automatico
function setupAutoRefresh(interval = 30000) {
  if (autoRefreshInterval) {
    clearInterval(autoRefreshInterval);
  }
  autoRefreshInterval = setInterval(loadMarkers, interval);
}

// Al caricamento della pagina, carica i marker e imposta intervallo
document.addEventListener('DOMContentLoaded', () => {
  loadMarkers();
  setupAutoRefresh();
  setInterval(updateHeaderStats, 60000); // Aggiorna l'orario nell'header ogni minuto
  initSearch(); // Inizializza la ricerca
  initFilters();
  initShareButton(); // Inizializza pulsante di condivisione
  loadInitialPosition();
});

// Pulsante per forzare l'aggiornamento
document.querySelector('.refresh-btn').addEventListener('click', () => {
  loadMarkers();
  // Resetta l'intervallo dopo un aggiornamento manuale
  setupAutoRefresh();
});

// Funzione per inizializzare la ricerca
function initSearch() {
  searchInput.addEventListener('input', handleSearch);
  searchResults.addEventListener('click', handleSearchResultClick);
}

// Filtri di ricerca
function initFilters() {
  const frequencyFilter = document.getElementById('frequency-filter');
  const typeFilter = document.getElementById('type-filter');
  const resetBtn = document.getElementById('reset-filters');

  // Funzione per resettare tutto
  const resetAllFilters = () => {
    frequencyFilter.value = '';
    typeFilter.value = '';
    activeFilters = { frequency: null, node_type: null };
    applyFilters();
    updateStatus('success', 'Filtri resettati');
  };

  // Event listeners
  frequencyFilter.addEventListener('change', function() {
    activeFilters.frequency = this.value || null;
    applyFilters();
  });

  typeFilter.addEventListener('change', function() {
    activeFilters.node_type = this.value || null;
    applyFilters();
  });

  resetBtn.addEventListener('click', resetAllFilters);
}

function applyFilters() {
  if (!currentMarkers.length) return;

  // Se nessun filtro attivo, mostra tutto
  if (!activeFilters.frequency && !activeFilters.node_type) {
    markersCluster.clearLayers();
    markersCluster.addLayers(currentMarkers);
    updateStatus('success', `Mostrati tutti i ${currentMarkers.length} nodi`);
    return;
  }

  // Altrimenti applica filtri
  const filtered = currentMarkers.filter(marker => {
    const data = marker.options.data || {};
    return (
      (!activeFilters.frequency || data.frequency === activeFilters.frequency) &&
      (!activeFilters.node_type || data.node_type === activeFilters.node_type)
    );
  });

  markersCluster.clearLayers();
  markersCluster.addLayers(filtered);
  
  // Aggiorna il contatore
  const statusText = `${filtered.length} nodi visibili`;
  updateStatus('success', statusText);
}

// --------------- Funzioni per gestire la ricerca ---------------
function handleSearch() {
  const searchTerm = searchInput.value.toLowerCase().trim();
  searchResults.innerHTML = '';
  
  if (searchTerm.length < 2) {
    searchResults.style.display = 'none';
    return;
  }
  
  const results = allMarkersData.filter(marker => 
    marker.name && marker.name.toLowerCase().includes(searchTerm))
    .slice(0, 10); // Limita a 10 risultati
  
  if (results.length > 0) {
    results.forEach(marker => {
      const resultItem = document.createElement('div');
      resultItem.className = 'search-result-item';
      resultItem.textContent = marker.name;
      resultItem.dataset.lat = marker.lat;
      resultItem.dataset.lon = marker.lon;
      searchResults.appendChild(resultItem);
    });
    searchResults.style.display = 'block';
  } else {
    searchResults.style.display = 'none';
  }
}

// Funzione per gestire il click su un risultato
function handleSearchResultClick(e) {
  if (e.target.classList.contains('search-result-item')) {
    const lat = parseFloat(e.target.dataset.lat);
    const lon = parseFloat(e.target.dataset.lon);
    
    map.setView([lat, lon], 16); // Zoom a livello 16
    markersCluster.getLayers().forEach(layer => {
      if (layer.getLatLng().lat === lat && layer.getLatLng().lng === lon) {
        layer.openPopup();
      }
    });
    
    searchResults.style.display = 'none';
    searchInput.value = e.target.textContent;
  }
}


// Funzione tasto di condivisione
function initShareButton() {
  const shareBtn = document.getElementById('share-btn');
  
  shareBtn.addEventListener('click', () => {
    // 1. Genera il link
    const center = map.getCenter();
    const url = new URL(window.location.href);
    url.searchParams.set('lat', center.lat.toFixed(6));
    url.searchParams.set('lng', center.lng.toFixed(6));
    url.searchParams.set('z', map.getZoom());
    const finalUrl = url.toString();

    // 2. Metodo moderno (HTTPS)
    if (navigator.clipboard) {
      navigator.clipboard.writeText(finalUrl)
        .then(() => showCopyFeedback(shareBtn))
        .catch(() => useFallbackMethod(finalUrl, shareBtn));
    } 
    // 3. Fallback per HTTP o browser vecchi
    else {
      useFallbackMethod(finalUrl, shareBtn);
    }
  });
}

// Metodo alternativo
function useFallbackMethod(url, button) {
  // Crea elemento temporaneo
  const textarea = document.createElement('textarea');
  textarea.value = url;
  textarea.style.position = 'fixed';  // Evita scroll
  document.body.appendChild(textarea);
  textarea.select();
  
  try {
    // Fallback principale
    const success = document.execCommand('copy');
    if (success) {
      showCopyFeedback(button);
    } else {
      showManualCopyPrompt(url, button);
    }
  } catch (err) {
    showManualCopyPrompt(url, button);
  } finally {
    document.body.removeChild(textarea);
  }
}

// Mostra prompt per copia manuale
function showManualCopyPrompt(url, button) {
  prompt("Premi Ctrl+C per copiare il link:", url);
  showCopyFeedback(button);
}

// Feedback visivo
function showCopyFeedback(button) {
  const originalText = button.innerHTML;
  button.innerHTML = '<i class="fas fa-check"></i> Copiato!';
  button.style.backgroundColor = '#e8f5e9';
  
  setTimeout(() => {
    button.innerHTML = originalText;
    button.style.backgroundColor = '';
  }, 2000);
}

// Funzione per caricare la posizione dal link
function loadInitialPosition() {
  const params = new URLSearchParams(window.location.search);
  if (params.has('lat') && params.has('lng')) {
    const lat = parseFloat(params.get('lat'));
    const lng = parseFloat(params.get('lng'));
    const zoom = params.has('z') ? parseInt(params.get('z')) : 15;
    
    map.setView([lat, lng], zoom);
  }
}