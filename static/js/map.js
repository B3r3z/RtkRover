/**
 * RTK ROVER - Neo-Brutalist Map Interface
 * Enhanced GPS tracking with modern brutalist design
 */

class RTKRoverMap {
    constructor() {
        this.map = null;
        this.currentMarker = null;
        this.trackPolyline = null;
        this.trackPoints = [];
        this.currentPosition = null;
        this.updateInterval = null;
        
        // Follow/centering behavior
        this.hasCenteredInitially = false;
        this.userInteracted = false;
        this.followMode = true;
        this.recenterPaddingRatio = 0.25;
        
        // Local track recording
        this.recordTrack = false;
        this.drawPolyline = null;
        this.localTrackPoints = [];
        this.minTrackPointDistance = 0.00001; // ~1.1m dla RTK precision (było 0.001 = ~111m)
        
        // Precision mode for RTK Fixed
        this.precisionMode = false;
        
        // Error handling
        this.consecutiveErrors = 0;
        this.maxConsecutiveErrors = 5;
        this.retryTimeout = null;
        this.lastSuccessfulUpdate = null;
        this.isOffline = false;
        
        // Adaptive polling
        this.basePollingInterval = 1000;
        this.currentPollingInterval = this.basePollingInterval;
        this.rtkStatus = 'Unknown';
        this.lastIntervalChange = 0; // Add throttling for interval changes
        
        // Cache DOM elements to avoid repeated queries
        this.domElements = {};
        
        this.init();
    }
    
    cacheControlElements() {
        console.log('📋 Cachowanie elementów DOM...');
        this.domElements = {
            followBtn: document.getElementById('follow-btn'),
            trackBtn: document.getElementById('track-btn'),
            clearBtn: document.getElementById('clear-btn'),
            precisionBtn: document.getElementById('precision-btn'),
            coordinates: document.getElementById('coordinates'),
            satellitesCount: document.getElementById('satellites-count'),
            rtkStatusBadge: document.getElementById('rtk-status-badge'),
            rtkStatusText: document.getElementById('rtk-status-text'),
            hdop: document.getElementById('hdop'),
            rtkFixStatus: document.getElementById('rtk-fix-status'),
            speed: document.getElementById('speed'),
            heading: document.getElementById('heading'),
            lastUpdate: document.getElementById('last-update'),
            trackPoints: document.getElementById('track-points'),
            sessionId: document.getElementById('session-id'),
            systemStatus: document.getElementById('system-status'),
            gpsDot: document.getElementById('gps-dot'),
            ntripDot: document.getElementById('ntrip-dot')
        };
        
        // Check for missing elements
        for (const [key, element] of Object.entries(this.domElements)) {
            if (!element) {
                console.warn(`⚠️ Element DOM nie znaleziony: ${key}`);
            }
        }
        console.log('✅ Elementy DOM zamieszkane');
    }
    
    init() {
        console.log('🚀 RTK Rover Map inicjalizacja...');
        this.initMap();
        this.cacheControlElements();
        this.setupControls();
        this.setupErrorHandling();
        this.startUpdates();
        console.log('✅ RTK Rover Map inicjalizacja zakończona');
    }
    
    setupErrorHandling() {
        window.addEventListener('online', () => {
            console.log('Połączenie przywrócone');
            this.isOffline = false;
            this.consecutiveErrors = 0;
            this.updateRTKBadge('single', 'ŁĄCZENIE...');
            this.startUpdates();
        });
        
        window.addEventListener('offline', () => {
            console.log('Utrata połączenia');
            this.isOffline = true;
            this.updateRTKBadge('no-fix', 'OFFLINE');
            this.stopUpdates();
        });
    }
    
    getAdaptivePollingInterval() {
        if (this.consecutiveErrors > 0) {
            return Math.min(this.basePollingInterval * Math.pow(2, this.consecutiveErrors), 30000);
        }
        
        switch (this.rtkStatus) {
            case 'RTK Fixed': return 1000;
            case 'RTK Float': return 1500;
            case 'DGPS': return 2000;
            default: return 3000;
        }
    }
    
    handleError(error, context = '') {
        this.consecutiveErrors++;
        const errorMsg = `${context}: ${error.message || error}`;
        
        console.error(`Błąd ${this.consecutiveErrors}/${this.maxConsecutiveErrors} - ${errorMsg}`);
        
        if (this.consecutiveErrors >= this.maxConsecutiveErrors) {
            this.updateRTKBadge('no-fix', 'BŁĄD SYSTEMU');
            this.stopUpdates();
            this.scheduleRetry(10000);
        } else {
            this.scheduleRetry();
        }
    }
    
    scheduleRetry(customDelay = null) {
        if (this.retryTimeout) {
            clearTimeout(this.retryTimeout);
        }
        
        const delay = customDelay || this.getAdaptivePollingInterval();
        console.log(`Ponowna próba za ${delay}ms`);
        
        this.retryTimeout = setTimeout(() => {
            this.retryTimeout = null;
            this.startUpdates();
        }, delay);
    }
    
    resetErrorState() {
        if (this.consecutiveErrors > 0) {
            console.log('Stan błędu zresetowany');
            this.consecutiveErrors = 0;
            this.lastSuccessfulUpdate = Date.now();
        }
        
        if (this.retryTimeout) {
            clearTimeout(this.retryTimeout);
            this.retryTimeout = null;
        }
    }
    
    initMap() {
        const defaultLat = 52.0;
        const defaultLon = 19.0;
        
        console.log('Inicjalizacja mapy...');
        
        try {
            this.map = L.map('map').setView([defaultLat, defaultLon], 6);
            
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
                maxZoom: 25
            }).addTo(this.map);
            
            this.map.on('dragstart zoomstart', () => {
                this.userInteracted = true;
                this.setFollowMode(false);
            });
            
            // Server track in muted color
            this.trackPolyline = L.polyline([], {
                color: '#9CA3AF',
                weight: 3,
                opacity: 0.8
            }).addTo(this.map);
            
            // Local track in teal accent
            this.drawPolyline = L.polyline([], {
                className: 'track-line rtk-fixed', // Domyślnie RTK Fixed
                color: '#10B981', // Success green dla RTK Fixed
                weight: 5,
                opacity: 0.9
            }).addTo(this.map);
            
            console.log('✅ Mapa zainicjalizowana pomyślnie');
            
            // Force resize after a short delay to handle any container sizing issues
            setTimeout(() => {
                this.map.invalidateSize();
                console.log('🔄 Rozmiar mapy odświeżony');
            }, 100);
            
        } catch (error) {
            console.error('❌ Błąd inicjalizacji mapy:', error);
        }
    }
    
    setupControls() {
        // Follow button
        if (this.domElements.followBtn) {
            this.domElements.followBtn.addEventListener('click', () => {
                this.setFollowMode(!this.followMode);
            });
        }
        
        // Track button
        if (this.domElements.trackBtn) {
            this.domElements.trackBtn.addEventListener('click', () => {
                this.setRecordTrack(!this.recordTrack);
            });
        }
        
        // Clear button
        if (this.domElements.clearBtn) {
            this.domElements.clearBtn.addEventListener('click', () => {
                this.clearLocalTrack();
            });
        }
        
        // Precision button
        if (this.domElements.precisionBtn) {
            this.domElements.precisionBtn.addEventListener('click', () => {
                this.togglePrecisionMode();
            });
        }
        
        this.updateControlsUI();
    }
    
    startUpdates() {
        this.stopUpdates();
        
        this.currentPollingInterval = this.getAdaptivePollingInterval();
        
        this.updateInterval = setInterval(() => {
            if (!this.isOffline) {
                this.updatePosition();
                this.updateTrack();
                this.updateStatus();
                
                const newInterval = this.getAdaptivePollingInterval();
                const now = Date.now();
                // Throttle interval changes to prevent rapid restarts
                if (newInterval !== this.currentPollingInterval && 
                    (now - this.lastIntervalChange) > 5000) {
                    this.currentPollingInterval = newInterval;
                    this.lastIntervalChange = now;
                    this.stopUpdates();
                    this.startUpdates();
                }
            }
        }, this.currentPollingInterval);
        
        console.log(`Aktualizacje rozpoczęte: ${this.currentPollingInterval}ms`);
    }
    
    stopUpdates() {
        if (this.updateInterval) {
            clearInterval(this.updateInterval);
            this.updateInterval = null;
        }
        if (this.retryTimeout) {
            clearTimeout(this.retryTimeout);
            this.retryTimeout = null;
        }
    }
    
    // Utility method for timeout signal with fallback
    createTimeoutSignal(timeoutMs) {
        if (typeof AbortSignal.timeout === 'function') {
            return AbortSignal.timeout(timeoutMs);
        } else {
            // Fallback for older browsers
            const controller = new AbortController();
            setTimeout(() => controller.abort(), timeoutMs);
            return controller.signal;
        }
    }

    async updatePosition() {
        try {
            const response = await fetch('/api/position', {
                method: 'GET',
                headers: { 'Accept': 'application/json' },
                signal: this.createTimeoutSignal(5000)
            });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const data = await response.json();
            
            // Validate JSON response structure
            if (!data || typeof data !== 'object') {
                throw new Error('Invalid JSON response structure');
            }
            
            this.resetErrorState();
            
            if (data.lat !== null && data.lat !== undefined && 
                data.lon !== null && data.lon !== undefined) {
                this.updateMapPosition(data);
                this.updateUI(data);
                this.currentPosition = data;
                this.rtkStatus = data.rtk_status || 'Unknown';
            } else {
                // Handle case when there's no GPS position available
                console.warn('Brak pozycji GPS:', data.error || 'Nieznany powód');
                this.updateUINoPosition(data);
                this.rtkStatus = data.rtk_status || 'No Fix';
            }
        } catch (error) {
            if (error.name === 'AbortError') {
                this.handleError(new Error('Timeout połączenia'), 'Aktualizacja pozycji');
            } else {
                this.handleError(error, 'Aktualizacja pozycji');
            }
        }
    }
    
    async updateTrack() {
        try {
            const response = await fetch('/api/track', {
                signal: this.createTimeoutSignal(3000)
            });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            
            const data = await response.json();
            
            if (data.points && data.points.length > 0) {
                this.updateTrackLine(data.points);
                this.updateTrackInfo(data);
            }
        } catch (error) {
            if (error.name !== 'AbortError') {
                console.warn('Błąd aktualizacji śladu:', error.message);
            }
        }
    }
    
    async updateStatus() {
        try {
            const response = await fetch('/api/status', {
                signal: this.createTimeoutSignal(3000)
            });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            
            const data = await response.json();
            this.updateSystemStatus(data);
        } catch (error) {
            if (error.name !== 'AbortError') {
                console.warn('Błąd aktualizacji statusu:', error.message);
            }
        }
    }
    
    updateMapPosition(position) {
        if (!this.map) return;

        const { lat, lon, rtk_status } = position;
        const latLng = [lat, lon];

        // Create a custom icon using L.divIcon for better control
        const rtkStatusClass = this.getRTKStatusClass(rtk_status);
        const roverIcon = L.divIcon({
            className: `rover-marker ${rtkStatusClass}`,
            iconSize: [24, 36], // Width of circle, height includes pointer
            iconAnchor: [12, 36], // Anchor at the tip of the pointer
            popupAnchor: [0, -38] // Position popup above the marker
        });

        if (!this.currentMarker) {
            this.currentMarker = L.marker(latLng, { icon: roverIcon }).addTo(this.map);
            this.currentMarker.bindPopup(this.createPopupContent(position), {
                offset: [0, -10]
            });
        } else {
            this.currentMarker.setLatLng(latLng);
            this.currentMarker.setIcon(roverIcon); // Update icon to reflect status changes
            this.currentMarker.setPopupContent(this.createPopupContent(position));
        }

        // Center map logic
        if (this.followMode && !this.userInteracted) {
            // Dla RTK Fixed używamy wyższego zoomu żeby zobaczyć precyzyjne zmiany
            let zoomLevel = this.map.getZoom() || 18;
            
            if (rtk_status === 'RTK Fixed') {
                zoomLevel = this.precisionMode ? 24 : 22;
            }
            
            this.map.setView(latLng, zoomLevel);
            this.hasCenteredInitially = true;
        } else if (this.followMode && this.userInteracted) {
            // Re-center if marker is out of view
            const bounds = this.map.getBounds().pad(-this.recenterPaddingRatio, -this.recenterPaddingRatio);
            if (!bounds.contains(latLng)) {
                this.map.panTo(latLng);
            }
        }

        // Add point to local track if recording is enabled
        if (this.recordTrack) {
            // Dostosuj precyzję śledzenia do statusu RTK
            this.updateTrackPrecision(rtk_status);
            this.appendTrackPointIfNeeded(lat, lon);
        }
    }

    updateTrackPrecision(rtkStatus) {
        // Dynamicznie dostosuj minimalną odległość w zależności od precyzji RTK
        switch (rtkStatus) {
            case 'RTK Fixed':
                this.minTrackPointDistance = 0.000005; // ~0.5m - bardzo wysoka precyzja
                this.updateTrackStyle('rtk-fixed', '#10B981', 5);
                break;
            case 'RTK Float':
                this.minTrackPointDistance = 0.00001; // ~1.1m - wysoka precyzja
                this.updateTrackStyle('rtk-float', '#F59E0B', 4);
                break;
            case 'DGPS':
                this.minTrackPointDistance = 0.00005; // ~5.5m - średnia precyzja
                this.updateTrackStyle('dgps', '#2DD4BF', 3);
                break;
            default:
                this.minTrackPointDistance = 0.0001; // ~11m - standardowa precyzja
                this.updateTrackStyle('no-fix', '#EF4444', 2);
        }
    }

    updateTrackStyle(cssClass, color, weight) {
        if (this.drawPolyline) {
            // Usuwamy stare klasy i dodajemy nowe
            const element = this.drawPolyline.getElement();
            if (element) {
                element.className = element.className.replace(/rtk-fixed|rtk-float|dgps|no-fix/g, '');
                element.classList.add(cssClass);
            }
            
            // Aktualizujemy także style inline dla pewności
            this.drawPolyline.setStyle({
                color: color,
                weight: weight
            });
        }
    }
    
    updateTrackLine(points) {
        if (!this.map || !points || points.length === 0) return;

        if (!this.trackPolyline) {
            this.trackPolyline = L.polyline(points, { 
                className: 'track-line' // Use a CSS class for styling
            }).addTo(this.map);
        } else {
            this.trackPolyline.setLatLngs(points);
        }
    }
    
    updateUI(position) {
        // Update coordinates
        if (this.domElements.coordinates) {
            this.domElements.coordinates.textContent = `${position.lat.toFixed(6)}, ${position.lon.toFixed(6)}`;
        }
        
        // Update satellites count
        if (this.domElements.satellitesCount) {
            this.domElements.satellitesCount.textContent = position.satellites || '--';
        }
        
        // Update RTK status badge
        this.updateRTKBadge(this.getRTKStatusClass(position.rtk_status), position.rtk_status);
        
        // Update HDOP
        if (this.domElements.hdop && position.hdop) {
            this.domElements.hdop.textContent = position.hdop.toFixed(1);
            this.domElements.hdop.className = `stat-value ${this.getHDOPClass(position.hdop)}`;
        }
        
        // Update RTK fix status
        if (this.domElements.rtkFixStatus) {
            this.domElements.rtkFixStatus.textContent = position.rtk_status || '--';
            this.domElements.rtkFixStatus.className = `stat-value ${this.getRTKStatusClass(position.rtk_status)}`;
        }
        
        // Update speed
        if (this.domElements.speed) {
            this.domElements.speed.textContent = position.speed_knots ? 
                `${position.speed_knots.toFixed(1)} węzłów` : '-- węzłów';
        }
        
        // Update heading
        if (this.domElements.heading) {
            this.domElements.heading.textContent = position.heading ? 
                `${position.heading.toFixed(0)}°` : '--°';
        }
        
        // Update last update time
        if (position.timestamp && this.domElements.lastUpdate) {
            const time = new Date(position.timestamp).toLocaleTimeString('pl-PL');
            this.domElements.lastUpdate.textContent = time;
        }
    }
    
    updateUINoPosition(data) {
        // Update coordinates to show no position
        if (this.domElements.coordinates) {
            this.domElements.coordinates.textContent = '---.------ , ---.------';
        }
        
        // Update satellites count
        if (this.domElements.satellitesCount) {
            this.domElements.satellitesCount.textContent = data.satellites || '--';
        }
        
        // Update RTK status badge
        this.updateRTKBadge('no-fix', data.rtk_status || 'BRAK SYGNAŁU');
        
        // Update HDOP
        if (this.domElements.hdop) {
            this.domElements.hdop.textContent = '--';
            this.domElements.hdop.className = 'stat-value poor';
        }
        
        // Update RTK fix status
        if (this.domElements.rtkFixStatus) {
            this.domElements.rtkFixStatus.textContent = data.rtk_status || 'No Fix';
            this.domElements.rtkFixStatus.className = 'stat-value no-fix';
        }
        
        // Update speed
        if (this.domElements.speed) {
            this.domElements.speed.textContent = '-- węzłów';
        }
        
        // Update heading
        if (this.domElements.heading) {
            this.domElements.heading.textContent = '--°';
        }
        
        // Update last update time
        if (data.timestamp && this.domElements.lastUpdate) {
            const time = new Date(data.timestamp).toLocaleTimeString('pl-PL');
            this.domElements.lastUpdate.textContent = time;
        }
    }
    
    updateTrackInfo(trackData) {
        if (this.domElements.trackPoints) {
            this.domElements.trackPoints.textContent = trackData.points.length;
        }
        
        if (this.domElements.sessionId) {
            this.domElements.sessionId.textContent = trackData.session_id || '--';
        }
    }
    
    updateSystemStatus(status) {
        // Update connection dots
        this.updateConnectionDot(this.domElements.gpsDot, status.gps_connected);
        this.updateConnectionDot(this.domElements.ntripDot, status.ntrip_connected);
        
        // Update system status
        if (this.domElements.systemStatus) {
            this.domElements.systemStatus.textContent = status.system_mode || status.rtk_status || 'Nieznany';
        }
    }
    
    updateConnectionDot(dotElement, isConnected) {
        if (dotElement) {
            dotElement.className = `conn-dot ${isConnected ? 'connected' : 'disconnected'}`;
        }
    }
    
    updateRTKBadge(statusClass, statusText) {
        if (this.domElements.rtkStatusBadge && this.domElements.rtkStatusText) {
            this.domElements.rtkStatusBadge.className = `rtk-badge ${statusClass}`;
            this.domElements.rtkStatusText.textContent = statusText || 'NIEZNANY';
        }
    }
    
    getRTKStatusClass(rtkStatus) {
        const statusMap = {
            'RTK Fixed': 'rtk-fixed',
            'RTK Float': 'rtk-float',
            'DGPS': 'single',
            'Single': 'single',
            'No Fix': 'no-fix'
        };
        
        return statusMap[rtkStatus] || 'no-fix';
    }
    
    getHDOPClass(hdop) {
        if (hdop <= 2.0) return 'good';
        if (hdop <= 5.0) return 'fair';
        return 'poor';
    }
    
    createPopupContent(position) {
        return `
            <div>
                <h4>🛸 RTK ROVER</h4>
                <p><strong>Status:</strong> ${position.rtk_status}</p>
                <p><strong>Pozycja:</strong> ${position.lat.toFixed(6)}, ${position.lon.toFixed(6)}</p>
                <p><strong>Wysokość:</strong> ${position.altitude ? position.altitude.toFixed(1) + 'm' : '--'}</p>
                <p><strong>Satelity:</strong> ${position.satellites || '--'}</p>
                <p><strong>HDOP:</strong> ${position.hdop ? position.hdop.toFixed(1) : '--'}</p>
                ${position.speed_knots ? `<p><strong>Prędkość:</strong> ${position.speed_knots.toFixed(1)} węzłów</p>` : ''}
                ${position.heading ? `<p><strong>Kierunek:</strong> ${position.heading.toFixed(0)}°</p>` : ''}
            </div>
        `;
    }
    
    setFollowMode(on) {
        this.followMode = !!on;
        if (this.followMode && this.currentMarker) {
            const ll = this.currentMarker.getLatLng();
            this.map.panTo(ll, { animate: true });
        }
        this.updateControlsUI();
    }
    
    setRecordTrack(on) {
        this.recordTrack = !!on;
        if (this.recordTrack && this.currentMarker) {
            const ll = this.currentMarker.getLatLng();
            this.appendTrackPointIfNeeded(ll.lat, ll.lng);
        }
        this.updateControlsUI();
    }
    
    appendTrackPointIfNeeded(lat, lon) {
        const ll = L.latLng(lat, lon);
        const pts = this.localTrackPoints;
        const last = pts.length ? L.latLng(pts[pts.length - 1].lat, pts[pts.length - 1].lon) : null;
        
        const distance = last ? last.distanceTo(ll) : Infinity;
        const shouldAdd = !last || distance >= this.minTrackPointDistance;
        
        console.log(`🎯 Track point check: dist=${distance.toFixed(6)}m, min=${(this.minTrackPointDistance*111000).toFixed(1)}m, add=${shouldAdd}`);
        
        if (shouldAdd) {
            pts.push({ lat, lon });
            this.drawPolyline.setLatLngs(pts.map(p => [p.lat, p.lon]));
            console.log(`✅ Added track point #${pts.length}: ${lat.toFixed(6)}, ${lon.toFixed(6)}`);
        }
    }
    
    clearLocalTrack() {
        this.localTrackPoints = [];
        if (this.drawPolyline) {
            this.drawPolyline.setLatLngs([]);
        }
        this.updateControlsUI();
    }
    
    updateControlsUI() {
        // Follow button
        if (this.domElements.followBtn) {
            this.domElements.followBtn.classList.toggle('active', this.followMode);
            this.domElements.followBtn.setAttribute('aria-pressed', this.followMode.toString());
            const textSpan = this.domElements.followBtn.querySelector('.btn-text');
            if (textSpan) {
                textSpan.textContent = this.followMode ? 'AKTYWNE' : 'ŚLEDŹ';
            }
        }
        
        // Track button
        if (this.domElements.trackBtn) {
            this.domElements.trackBtn.classList.toggle('active', this.recordTrack);
            this.domElements.trackBtn.setAttribute('aria-pressed', this.recordTrack.toString());
            const textSpan = this.domElements.trackBtn.querySelector('.btn-text');
            if (textSpan) {
                textSpan.textContent = this.recordTrack ? 'STOP' : 'ŚLAD';
            }
        }
        
        // Clear button
        if (this.domElements.clearBtn) {
            this.domElements.clearBtn.disabled = this.localTrackPoints.length === 0;
            this.domElements.clearBtn.style.opacity = this.domElements.clearBtn.disabled ? '0.5' : '1';
        }
        
        // Precision button
        if (this.domElements.precisionBtn) {
            this.domElements.precisionBtn.classList.toggle('active', this.precisionMode);
            this.domElements.precisionBtn.setAttribute('aria-pressed', this.precisionMode.toString());
            const textSpan = this.domElements.precisionBtn.querySelector('.btn-text');
            if (textSpan) {
                textSpan.textContent = this.precisionMode ? 'AKTYWNE' : 'PRECYZJA';
            }
        }
    }
    
    togglePrecisionMode() {
        this.precisionMode = !this.precisionMode;
        
        if (this.precisionMode) {
            // W trybie precyzyjnym dla RTK Fixed
            console.log('🎯 Tryb precyzyjny aktywowany');
            
            // Automatycznie włącz śledzenie pozycji
            this.followMode = true;
            
            // Automatycznie włącz nagrywanie śladu jeśli jeszcze nie
            if (!this.recordTrack) {
                this.setTrackRecording(true);
            }
            
            // Zwiększ zoom jeśli mamy RTK Fixed i aktualną pozycję
            if (this.rtkStatus === 'RTK Fixed' && this.map && this.currentMarker) {
                this.map.setView(this.currentMarker.getLatLng(), 23);
            }
        } else {
            console.log('🎯 Tryb precyzyjny wyłączony');
        }
        
        this.updateControlsUI();
    }
}

// Initialize when page loads
document.addEventListener('DOMContentLoaded', function() {
    console.log('Inicjalizacja RTK ROVER Map...');
    window.rtkMap = new RTKRoverMap();
});

// Cleanup on page unload
window.addEventListener('beforeunload', function() {
    if (window.rtkMap) {
        window.rtkMap.stopUpdates();
    }
});
