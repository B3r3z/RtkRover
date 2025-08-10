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
        this.minTrackPointDistance = 0.001;
        
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
        
        this.init();
    }
    
    init() {
        this.initMap();
        this.setupControls();
        this.setupErrorHandling();
        this.startUpdates();
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
        
        this.map = L.map('map').setView([defaultLat, defaultLon], 6);
        
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
            maxZoom: 19
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
            color: '#2DD4BF',
            weight: 4,
            opacity: 0.9
        }).addTo(this.map);
        
        console.log('Mapa zainicjalizowana');
    }
    
    setupControls() {
        // Follow button
        const followBtn = document.getElementById('follow-btn');
        if (followBtn) {
            followBtn.addEventListener('click', () => {
                this.setFollowMode(!this.followMode);
            });
        }
        
        // Track button
        const trackBtn = document.getElementById('track-btn');
        if (trackBtn) {
            trackBtn.addEventListener('click', () => {
                this.setRecordTrack(!this.recordTrack);
            });
        }
        
        // Clear button
        const clearBtn = document.getElementById('clear-btn');
        if (clearBtn) {
            clearBtn.addEventListener('click', () => {
                this.clearLocalTrack();
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
                if (newInterval !== this.currentPollingInterval) {
                    this.currentPollingInterval = newInterval;
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
    
    async updatePosition() {
        try {
            const response = await fetch('/api/position', {
                method: 'GET',
                headers: { 'Accept': 'application/json' },
                signal: AbortSignal.timeout(5000)
            });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const data = await response.json();
            this.resetErrorState();
            
            if (data.lat !== null && data.lon !== null) {
                this.updateMapPosition(data);
                this.updateUI(data);
                this.currentPosition = data;
                this.rtkStatus = data.rtk_status || 'Unknown';
            } else {
                console.warn('Brak pozycji GPS:', data.error || 'Nieznany powód');
                this.updateRTKBadge('no-fix', data.rtk_status || 'BRAK SYGNAŁU');
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
                signal: AbortSignal.timeout(3000)
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
                signal: AbortSignal.timeout(3000)
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
        const lat = position.lat;
        const lon = position.lon;
        
        if (this.currentMarker) {
            this.currentMarker.setLatLng([lat, lon]);
        } else {
            const roverIcon = L.divIcon({
                html: '🛸',
                iconSize: [40, 40],
                iconAnchor: [20, 40],
                className: 'rover-icon'
            });
            
            this.currentMarker = L.marker([lat, lon], { icon: roverIcon })
                .addTo(this.map)
                .bindPopup(this.createPopupContent(position));
        }
        
        this.currentMarker.setPopupContent(this.createPopupContent(position));
        
        if (this.recordTrack) {
            this.appendTrackPointIfNeeded(lat, lon);
        }
        
        if (!this.hasCenteredInitially) {
            this.map.setView([lat, lon], 17, { animate: false });
            this.hasCenteredInitially = true;
        } else if (this.followMode) {
            try {
                const bounds = this.map.getBounds();
                const inner = L.latLngBounds(bounds.getSouthWest(), bounds.getNorthEast()).pad(-this.recenterPaddingRatio);
                if (!inner.contains([lat, lon])) {
                    this.map.panTo([lat, lon], { animate: true });
                }
            } catch (e) {
                this.map.panTo([lat, lon], { animate: true });
            }
        }
    }
    
    updateTrackLine(points) {
        const trackCoords = points.map(point => [point.lat, point.lon]);
        this.trackPolyline.setLatLngs(trackCoords);
        this.trackPoints = points;
        
        if (points.length > 10 && !this.hasCenteredInitially && !this.userInteracted) {
            try {
                const bounds = this.trackPolyline.getBounds();
                if (bounds.isValid()) {
                    this.map.fitBounds(bounds, { padding: [20, 20] });
                    this.hasCenteredInitially = true;
                }
            } catch (e) {
                console.log('Nie można dopasować granic:', e);
            }
        }
    }
    
    updateUI(position) {
        // Update coordinates
        const coordsElement = document.getElementById('coordinates');
        if (coordsElement) {
            coordsElement.textContent = `${position.lat.toFixed(6)}, ${position.lon.toFixed(6)}`;
        }
        
        // Update satellites count
        const satElement = document.getElementById('satellites-count');
        if (satElement) {
            satElement.textContent = position.satellites || '--';
        }
        
        // Update RTK status badge
        this.updateRTKBadge(this.getRTKStatusClass(position.rtk_status), position.rtk_status);
        
        // Update HDOP
        const hdopElement = document.getElementById('hdop');
        if (hdopElement && position.hdop) {
            hdopElement.textContent = position.hdop.toFixed(1);
            hdopElement.className = `stat-value ${this.getHDOPClass(position.hdop)}`;
        }
        
        // Update RTK fix status
        const rtkFixElement = document.getElementById('rtk-fix-status');
        if (rtkFixElement) {
            rtkFixElement.textContent = position.rtk_status || '--';
            rtkFixElement.className = `stat-value ${this.getRTKStatusClass(position.rtk_status)}`;
        }
        
        // Update speed
        const speedElement = document.getElementById('speed');
        if (speedElement) {
            speedElement.textContent = position.speed_knots ? 
                `${position.speed_knots.toFixed(1)} węzłów` : '-- węzłów';
        }
        
        // Update heading
        const headingElement = document.getElementById('heading');
        if (headingElement) {
            headingElement.textContent = position.heading ? 
                `${position.heading.toFixed(0)}°` : '--°';
        }
        
        // Update last update time
        if (position.timestamp) {
            const updateElement = document.getElementById('last-update');
            if (updateElement) {
                const time = new Date(position.timestamp).toLocaleTimeString('pl-PL');
                updateElement.textContent = time;
            }
        }
    }
    
    updateTrackInfo(trackData) {
        const pointsElement = document.getElementById('track-points');
        if (pointsElement) {
            pointsElement.textContent = trackData.points.length;
        }
        
        const sessionElement = document.getElementById('session-id');
        if (sessionElement) {
            sessionElement.textContent = trackData.session_id || '--';
        }
    }
    
    updateSystemStatus(status) {
        // Update connection dots
        this.updateConnectionDot('gps-dot', status.gps_connected);
        this.updateConnectionDot('ntrip-dot', status.ntrip_connected);
        
        // Update system status
        const systemElement = document.getElementById('system-status');
        if (systemElement) {
            systemElement.textContent = status.system_mode || status.rtk_status || 'Nieznany';
        }
    }
    
    updateConnectionDot(elementId, isConnected) {
        const dot = document.getElementById(elementId);
        if (dot) {
            dot.className = `conn-dot ${isConnected ? 'connected' : 'disconnected'}`;
        }
    }
    
    updateRTKBadge(statusClass, statusText) {
        const badge = document.getElementById('rtk-status-badge');
        const textElement = document.getElementById('rtk-status-text');
        
        if (badge && textElement) {
            badge.className = `rtk-badge ${statusClass}`;
            textElement.textContent = statusText || 'NIEZNANY';
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
        
        if (!last || last.distanceTo(ll) >= this.minTrackPointDistance) {
            pts.push({ lat, lon });
            this.drawPolyline.setLatLngs(pts.map(p => [p.lat, p.lon]));
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
        const followBtn = document.getElementById('follow-btn');
        if (followBtn) {
            followBtn.classList.toggle('active', this.followMode);
            const textSpan = followBtn.querySelector('.btn-text');
            if (textSpan) {
                textSpan.textContent = this.followMode ? 'ŚLEDŹ' : 'ŚLEDŹ';
            }
        }
        
        // Track button
        const trackBtn = document.getElementById('track-btn');
        if (trackBtn) {
            trackBtn.classList.toggle('active', this.recordTrack);
            const textSpan = trackBtn.querySelector('.btn-text');
            if (textSpan) {
                textSpan.textContent = this.recordTrack ? 'STOP' : 'ŚLAD';
            }
        }
        
        // Clear button
        const clearBtn = document.getElementById('clear-btn');
        if (clearBtn) {
            clearBtn.disabled = this.localTrackPoints.length === 0;
            clearBtn.style.opacity = clearBtn.disabled ? '0.5' : '1';
        }
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
