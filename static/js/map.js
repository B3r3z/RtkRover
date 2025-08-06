/**
 * RTK Mower Map Interface
 * Handles map display, position updates, and track visualization
 */

class RTKMowerMap {
    constructor() {
        this.map = null;
        this.currentMarker = null;
        this.trackPolyline = null;
        this.trackPoints = [];
        this.currentPosition = null;
        this.updateInterval = null;
        
        this.init();
    }
    
    init() {
        this.initMap();
        this.startUpdates();
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
        // Update every 1 second
        this.updateInterval = setInterval(() => {
            this.updatePosition();
            this.updateTrack();
            this.updateStatus();
        }, 1000);
        
        console.log('Started position updates');
    }
    
    stopUpdates() {
        if (this.updateInterval) {
            clearInterval(this.updateInterval);
            this.updateInterval = null;
        }
    }
    
    async updatePosition() {
        try {
            const response = await fetch('/api/position');
            const data = await response.json();
            
            if (response.ok && data.lat !== null && data.lon !== null) {
                this.currentPosition = data;
                this.updateMapPosition(data);
                this.updateUI(data);
            } else {
                console.log('No GPS position available:', data.error);
                this.updateStatusIndicator('disconnected', data.error || 'No GPS signal');
            }
        } catch (error) {
            console.error('Error fetching position:', error);
            this.updateStatusIndicator('disconnected', 'Connection error');
        }
    }
    
    async updateTrack() {
        try {
            const response = await fetch('/api/track');
            const data = await response.json();
            
            if (response.ok && data.points && data.points.length > 0) {
                this.updateTrackLine(data.points);
                this.updateTrackInfo(data);
            }
        } catch (error) {
            console.error('Error fetching track:', error);
        }
    }
    
    async updateStatus() {
        try {
            const response = await fetch('/api/status');
            const data = await response.json();
            
            if (response.ok) {
                this.updateSystemStatus(data);
            }
        } catch (error) {
            console.error('Error fetching status:', error);
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
        
        // Update GPS info
        document.getElementById('satellites').textContent = position.satellites || '--';
        document.getElementById('hdop').textContent = position.hdop ? position.hdop.toFixed(1) : '--';
        document.getElementById('speed').textContent = position.speed_knots ? 
            `${position.speed_knots.toFixed(1)} knots` : '-- knots';
        document.getElementById('heading').textContent = position.heading ? 
            `${position.heading.toFixed(0)}°` : '--°';
        
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
        // Additional system status info could be displayed here
        console.log('System status:', status);
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
