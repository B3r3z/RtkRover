/**
 * RTK Mower Map Interface
 * Handles map display, position updates, and track visualization
 * Enhanced with error handling and adaptive polling
 */

class RTKMowerMap {
    constructor() {
        this.map = null;
        this.currentMarker = null;
        this.trackPolyline = null;
        this.trackPoints = [];
        this.currentPosition = null;
        this.updateInterval = null;
        
        // Error handling and retry logic
        this.consecutiveErrors = 0;
        this.maxConsecutiveErrors = 5;
        this.retryTimeout = null;
        this.lastSuccessfulUpdate = null;
        this.isOffline = false;
        
        // Adaptive polling
        this.basePollingInterval = 1000; // 1 second
        this.currentPollingInterval = this.basePollingInterval;
        this.rtkStatus = 'Unknown';
        
        this.init();
    }
    
    init() {
        this.initMap();
        this.setupErrorHandling();
        this.startUpdates();
    }
    
    setupErrorHandling() {
        /**
         * Setup global error handling for the application
         */
        window.addEventListener('online', () => {
            console.log('Connection restored');
            this.isOffline = false;
            this.consecutiveErrors = 0;
            this.updateStatusIndicator('connecting', 'Reconnecting...');
            this.startUpdates();
        });
        
        window.addEventListener('offline', () => {
            console.log('Connection lost');
            this.isOffline = true;
            this.updateStatusIndicator('disconnected', 'Offline');
            this.stopUpdates();
        });
    }
    
    getAdaptivePollingInterval() {
        /**
         * Calculate adaptive polling interval based on RTK status and error count
         */
        if (this.consecutiveErrors > 0) {
            // Exponential backoff for errors
            return Math.min(this.basePollingInterval * Math.pow(2, this.consecutiveErrors), 30000);
        }
        
        // Adaptive timing based on RTK status
        switch (this.rtkStatus) {
            case 'RTK Fixed':
                return 2000; // 2 seconds for stable RTK
            case 'RTK Float':
                return 1500; // 1.5 seconds for RTK Float
            case 'DGPS':
            case 'Single':
                return 1000; // 1 second for standard GPS
            case 'Demo Mode':
                return 1000; // 1 second for demo
            default:
                return 1000; // Default 1 second
        }
    }
    
    handleError(error, context = '') {
        /**
         * Centralized error handling with retry logic
         */
        this.consecutiveErrors++;
        const errorMsg = `${context}: ${error.message || error}`;
        
        console.error(`Error ${this.consecutiveErrors}/${this.maxConsecutiveErrors} - ${errorMsg}`);
        
        if (this.consecutiveErrors >= this.maxConsecutiveErrors) {
            console.error('Too many consecutive errors, switching to error mode');
            this.updateStatusIndicator('disconnected', 'Connection Error');
            this.scheduleRetry(30000); // Retry after 30 seconds
        } else {
            this.updateStatusIndicator('error', `Error (${this.consecutiveErrors})`);
            this.scheduleRetry();
        }
    }
    
    scheduleRetry(customDelay = null) {
        /**
         * Schedule retry with exponential backoff
         */
        if (this.retryTimeout) {
            clearTimeout(this.retryTimeout);
        }
        
        const delay = customDelay || this.getAdaptivePollingInterval();
        console.log(`Scheduling retry in ${delay}ms`);
        
        this.retryTimeout = setTimeout(() => {
            if (!this.isOffline) {
                this.updatePosition();
                this.updateTrack();
                this.updateStatus();
            }
        }, delay);
    }
    
    resetErrorState() {
        /**
         * Reset error state on successful operation
         */
        if (this.consecutiveErrors > 0) {
            console.log('Connection restored, resetting error state');
            this.consecutiveErrors = 0;
            this.lastSuccessfulUpdate = Date.now();
        }
        
        if (this.retryTimeout) {
            clearTimeout(this.retryTimeout);
            this.retryTimeout = null;
        }
    }
    
    initMap() {
        // Default center (Poland center)
        const defaultLat = 52.0;
        const defaultLon = 19.0;
        
        // Initialize Leaflet map
        this.map = L.map('map').setView([defaultLat, defaultLon], 6);
        
        // Add OpenStreetMap tile layer
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
            maxZoom: 19
        }).addTo(this.map);
        
        // Initialize track polyline
        this.trackPolyline = L.polyline([], {
            color: 'blue',
            weight: 3,
            opacity: 0.7
        }).addTo(this.map);
        
        console.log('Map initialized');
    }
    
    startUpdates() {
        // Stop any existing updates
        this.stopUpdates();
        
        // Adaptive polling interval
        this.currentPollingInterval = this.getAdaptivePollingInterval();
        
        this.updateInterval = setInterval(() => {
            if (!this.isOffline) {
                this.updatePosition();
                this.updateTrack();
                this.updateStatus();
                
                // Adjust polling interval dynamically
                const newInterval = this.getAdaptivePollingInterval();
                if (newInterval !== this.currentPollingInterval) {
                    this.currentPollingInterval = newInterval;
                    this.stopUpdates();
                    this.startUpdates();
                }
            }
        }, this.currentPollingInterval);
        
        console.log(`Started position updates with ${this.currentPollingInterval}ms interval`);
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
                headers: {
                    'Accept': 'application/json',
                },
                // Add timeout for requests
                signal: AbortSignal.timeout(5000)
            });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const data = await response.json();
            
            // Reset error state on success
            this.resetErrorState();
            
            if (data.lat !== null && data.lon !== null) {
                this.updateMapPosition(data);
                this.updateUI(data);
                this.currentPosition = data;
                this.rtkStatus = data.rtk_status || 'Unknown';
            } else {
                console.warn('No GPS position available:', data.error || 'Unknown reason');
                this.updateStatusIndicator('no-fix', data.rtk_status || 'No Fix');
            }
        } catch (error) {
            if (error.name === 'AbortError') {
                this.handleError(new Error('Request timeout'), 'Position update');
            } else {
                this.handleError(error, 'Position update');
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
                console.warn('Track update failed:', error.message);
                // Don't count track errors as critical errors
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
            
            if (data) {
                this.updateSystemStatus(data);
                this.rtkStatus = data.rtk_status || 'Unknown';
            }
        } catch (error) {
            if (error.name !== 'AbortError') {
                console.warn('Status update failed:', error.message);
                // Don't count status errors as critical errors
            }
        }
    }
    
    updateMapPosition(position) {
        const lat = position.lat;
        const lon = position.lon;
        
        // Update or create current position marker
        if (this.currentMarker) {
            this.currentMarker.setLatLng([lat, lon]);
        } else {
            // Create marker with custom icon
            const roverIcon = L.divIcon({
                html: '🚜',
                iconSize: [30, 30],
                iconAnchor: [15, 15],
                className: 'rover-icon'
            });
            
            this.currentMarker = L.marker([lat, lon], { icon: roverIcon })
                .addTo(this.map)
                .bindPopup(this.createPopupContent(position));
        }
        
        // Update popup content
        this.currentMarker.setPopupContent(this.createPopupContent(position));
        
        // Center map on first fix or if far away
        if (this.trackPoints.length === 0) {
            this.map.setView([lat, lon], 18);
        } else {
            // Keep current view if position is visible
            if (!this.map.getBounds().contains([lat, lon])) {
                this.map.panTo([lat, lon]);
            }
        }
    }
    
    updateTrackLine(points) {
        // Convert points to lat/lon array
        const trackCoords = points.map(point => [point.lat, point.lon]);
        
        // Update polyline
        this.trackPolyline.setLatLngs(trackCoords);
        
        // Store points for reference
        this.trackPoints = points;
        
        // Fit map to track bounds if significant number of points
        if (points.length > 10) {
            try {
                const bounds = this.trackPolyline.getBounds();
                if (bounds.isValid()) {
                    this.map.fitBounds(bounds, { padding: [20, 20] });
                }
            } catch (e) {
                console.log('Could not fit bounds:', e);
            }
        }
    }
    
    updateUI(position) {
        // Update coordinates display
        document.getElementById('coordinates').textContent = 
            `${position.lat.toFixed(6)}, ${position.lon.toFixed(6)}`;
        
        // Update GPS info with signal quality analysis
        document.getElementById('satellites').textContent = position.satellites || '--';
        
        const hdop = position.hdop;
        const hdopElement = document.getElementById('hdop');
        const hdopWarning = document.getElementById('hdop-warning');
        
        if (hdop) {
            hdopElement.textContent = hdop.toFixed(1);
            
            // Color-code HDOP values
            hdopElement.className = 'hdop-value';
            if (hdop <= 2.0) {
                hdopElement.classList.add('good');
                hdopWarning.style.display = 'none';
            } else if (hdop <= 5.0) {
                hdopElement.classList.add('fair');
                hdopWarning.style.display = 'none';
            } else {
                hdopElement.classList.add('poor');
                hdopWarning.style.display = 'inline';
                hdopWarning.textContent = '⚠️ Poor signal';
            }
        } else {
            hdopElement.textContent = '--';
            hdopElement.className = 'hdop-value';
            hdopWarning.style.display = 'none';
        }
        
        // Update signal quality assessment
        this.updateSignalQuality(position.satellites, hdop);
        
        document.getElementById('speed').textContent = position.speed_knots ? 
            `${position.speed_knots.toFixed(1)} knots` : '-- knots';
        document.getElementById('heading').textContent = position.heading ? 
            `${position.heading.toFixed(0)}°` : '--°';
        
        // Update RTK status in info panel
        this.updateRTKStatus(position.rtk_status);
        
        // Update status indicator
        this.updateStatusIndicator(this.getStatusClass(position.rtk_status), position.rtk_status);
        
        // Update last update time
        if (position.timestamp) {
            const time = new Date(position.timestamp).toLocaleTimeString();
            document.getElementById('last-update').textContent = time;
        }
    }
    
    updateTrackInfo(trackData) {
        document.getElementById('track-points').textContent = trackData.points.length;
        document.getElementById('session-id').textContent = trackData.session_id || '--';
    }
    
    updateSystemStatus(status) {
        // Update connection indicators
        const gpsStatus = status.gps_connected;
        const ntripStatus = status.ntrip_connected;
        
        // Update connection dots in header
        this.updateConnectionDot('gps-dot', gpsStatus);
        this.updateConnectionDot('ntrip-dot', ntripStatus);
        
        // Update connection status text in info panel
        document.getElementById('gps-status').textContent = gpsStatus ? 'Connected' : 'Disconnected';
        document.getElementById('gps-status').className = `connection-status-text ${gpsStatus ? 'connected' : 'disconnected'}`;
        
        document.getElementById('ntrip-status').textContent = ntripStatus ? 'Connected' : 'Disconnected';
        document.getElementById('ntrip-status').className = `connection-status-text ${ntripStatus ? 'connected' : 'disconnected'}`;
        
        // Update RTK-FIX indicator
        const rtkFixElement = document.getElementById('rtk-fix-status');
        if (rtkFixElement && status.hasOwnProperty('rtk_fix_available')) {
            rtkFixElement.textContent = status.rtk_fix_status || 'Unavailable';
            rtkFixElement.className = `rtk-fix-indicator ${status.rtk_fix_available ? 'available' : 'unavailable'}`;
        }
        
        // Update system status
        document.getElementById('system-status').textContent = status.system_mode || status.rtk_status || 'Unknown';
        
        console.log('System status updated:', status);
    }
    
    updateConnectionDot(elementId, isConnected) {
        const dot = document.getElementById(elementId);
        if (dot) {
            dot.className = `connection-dot ${isConnected ? 'connected' : 'disconnected'}`;
        }
    }
    
    updateRTKStatus(rtkStatus) {
        const statusElement = document.getElementById('rtk-fix-status');
        const badgeElement = document.getElementById('rtk-fix-badge');
        
        if (statusElement) {
            statusElement.textContent = rtkStatus || '--';
            statusElement.className = `rtk-status-value ${this.getRTKStatusClass(rtkStatus)}`;
        }
        
        // Show/hide RTK Fixed badge
        if (badgeElement) {
            if (rtkStatus === 'RTK Fixed') {
                badgeElement.style.display = 'inline-block';
                badgeElement.textContent = '🎯 RTK FIXED';
            } else if (rtkStatus === 'RTK Float') {
                badgeElement.style.display = 'inline-block';
                badgeElement.textContent = '📍 RTK FLOAT';
                badgeElement.style.backgroundColor = '#ffc107';
            } else {
                badgeElement.style.display = 'none';
            }
        }
    }
    
    getRTKStatusClass(rtkStatus) {
        const statusClassMap = {
            'RTK Fixed': 'rtk-fixed',
            'RTK Float': 'rtk-float',
            'DGPS': 'single',
            'Single': 'single',
            'No Fix': 'no-fix'
        };
        
        return statusClassMap[rtkStatus] || 'no-fix';
    }
    
    updateSignalQuality(satellites, hdop) {
        const qualityElement = document.getElementById('signal-quality');
        
        if (!satellites || !hdop) {
            qualityElement.textContent = '--';
            qualityElement.className = 'signal-quality';
            return;
        }
        
        let quality, className;
        
        // Signal quality assessment based on satellites and HDOP
        if (satellites >= 12 && hdop <= 2.0) {
            quality = 'Excellent';
            className = 'excellent';
        } else if (satellites >= 8 && hdop <= 3.0) {
            quality = 'Good';
            className = 'good';
        } else if (satellites >= 6 && hdop <= 5.0) {
            quality = 'Fair';
            className = 'fair';
        } else {
            quality = 'Poor';
            className = 'poor';
        }
        
        qualityElement.textContent = quality;
        qualityElement.className = `signal-quality ${className}`;
        
        // Add additional info for poor signal
        if (className === 'poor') {
            if (hdop > 5.0) {
                quality += ' (High HDOP)';
            }
            if (satellites < 6) {
                quality += ' (Few sats)';
            }
            qualityElement.textContent = quality;
        }
    }
    
    updateStatusIndicator(statusClass, statusText) {
        const dot = document.getElementById('status-dot');
        const text = document.getElementById('status-text');
        
        // Remove all status classes
        dot.className = 'status-dot';
        
        // Add new status class
        if (statusClass) {
            dot.classList.add(statusClass);
        }
        
        // Update text
        text.textContent = statusText || 'Unknown';
    }
    
    getStatusClass(rtkStatus) {
        const statusMap = {
            'RTK Fixed': 'rtk-fixed',
            'RTK Float': 'rtk-float',
            'DGPS': 'connected',
            'Single': 'single',
            'No Fix': 'disconnected'
        };
        
        return statusMap[rtkStatus] || 'disconnected';
    }
    
    createPopupContent(position) {
        return `
            <div>
                <h4>🚜 RTK Mower</h4>
                <p><strong>Status:</strong> ${position.rtk_status}</p>
                <p><strong>Position:</strong> ${position.lat.toFixed(6)}, ${position.lon.toFixed(6)}</p>
                <p><strong>Altitude:</strong> ${position.altitude.toFixed(1)}m</p>
                <p><strong>Satellites:</strong> ${position.satellites}</p>
                <p><strong>HDOP:</strong> ${position.hdop.toFixed(1)}</p>
                ${position.speed_knots ? `<p><strong>Speed:</strong> ${position.speed_knots.toFixed(1)} knots</p>` : ''}
                ${position.heading ? `<p><strong>Heading:</strong> ${position.heading.toFixed(0)}°</p>` : ''}
            </div>
        `;
    }
}

// Initialize map when page loads
document.addEventListener('DOMContentLoaded', function() {
    console.log('Initializing RTK Mower Map...');
    window.rtkMap = new RTKMowerMap();
});

// Cleanup on page unload
window.addEventListener('beforeunload', function() {
    if (window.rtkMap) {
        window.rtkMap.stopUpdates();
    }
});
