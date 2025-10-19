/**
 * RTK Rover - Map Interface with Navigation Integration
 * Supports GPS tracking, waypoint management, and autonomous navigation
 */
(function() {
    'use strict';
    
    // ==========================================
    // API ENDPOINTS
    // ==========================================
    const API = {
        position: '/api/position',
        track: '/api/track',
        // Navigation endpoints
        navStatus: '/api/navigation/status',
        addWaypoint: '/api/navigation/waypoint',
        getWaypoints: '/api/navigation/waypoints',
        clearWaypoints: '/api/navigation/waypoints',
        goto: '/api/navigation/goto',
        followPath: '/api/navigation/path',
        startNavigation: '/api/navigation/start',
        pause: '/api/navigation/pause',
        resume: '/api/navigation/resume',
        cancel: '/api/navigation/cancel',
        emergencyStop: '/api/navigation/emergency_stop',
        setSpeed: '/api/motor/speed'
    };
    
    // ==========================================
    // STATE
    // ==========================================
    const state = {
        // Map
        map: null,
        marker: null,
        track: [],
        poly: null,
        last: null,
        follow: true,
        drawing: true,
        centered: false,
        minDist: 0.00001,
        
        // Waypoints
        wps: [],
        wpLayer: null,
        
        // Navigation
        navEnabled: false,
        navRunning: false,
        clickToAddMode: false,
        currentTarget: null,
        targetMarker: null,
        
        // Rover system availability
        roverAvailable: null  // null=unknown, true/false
    };
    
    // ==========================================
    // UI ELEMENTS
    // ==========================================
    const g = id => document.getElementById(id);
    const ui = {
        // Position display
        lat: g('lat'),
        lon: g('lon'),
        alt: g('alt'),
        time: g('time'),
        speed: g('speed'),
        heading: g('heading'),
        
        // Status badges
        mode: g('statusMode'),
        fix: g('statusFix'),
        sat: g('statusSat'),
        hdop: g('statusHdop'),
        
        // Map controls
        c: g('btnCenter'),
        t: g('btnToggleTrack'),
        clr: g('btnClearTrack'),
        
        // Waypoint controls
        wpName: g('wpName'),
        add: g('btnAddWp'),
        toggleClickAdd: g('btnToggleClickAdd'),
        exp: g('btnExportWp'),
        wclr: g('btnClearWp'),
        list: g('waypointList'),
        
        // Navigation controls
        navSystemStatus: g('navSystemStatus'),
        btnStartNav: g('btnStartNav'),
        btnPauseNav: g('btnPauseNav'),
        btnResumeNav: g('btnResumeNav'),
        btnEmergencyStop: g('btnEmergencyStop'),
        btnCancelNav: g('btnCancelNav')
    };
    
    // Check for missing elements
    Object.entries(ui).forEach(([k, v]) => {
        if (!v) console.warn('UI element missing:', k);
    });
    
    let lastErrShown = 0;
    
    // ==========================================
    // MAP INITIALIZATION
    // ==========================================
    function initMap() {
        state.map = L.map('map');
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 22,
            attribution: 'OSM'
        }).addTo(state.map);
        
        state.map.setView([52, 19], 6);
        state.poly = L.polyline([], {
            color: '#66cfff',
            weight: 3,
            opacity: 0.85
        }).addTo(state.map);
        
        state.wpLayer = L.layerGroup().addTo(state.map);
        
        // Enable map click to add waypoints
        state.map.on('click', onMapClick);
        
        setTimeout(() => state.map.invalidateSize(), 150);
    }
    
    // ==========================================
    // NETWORK HELPERS
    // ==========================================
    async function fetchJSON(url, options = {}) {
        try {
            const r = await fetch(url, { 
                cache: 'no-store',
                ...options 
            });
            
            if (!r.ok) {
                throw new Error(`HTTP ${r.status}`);
            }
            
            return await r.json();
        } catch (e) {
            const now = Date.now();
            if (now - lastErrShown > 5000) {
                console.error('Fetch error', url, e);
                const bar = document.getElementById('rtkBar');
                if (bar) {
                    bar.textContent = 'RTK: błąd połączenia';
                    bar.className = 'rtk-bar rtk-unknown';
                }
                lastErrShown = now;
            }
            return { error: e.message };
        }
    }
    
    async function postJSON(url, data) {
        return fetchJSON(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
    }
    
    // ==========================================
    // ROVER SYSTEM CHECK
    // ==========================================
    async function checkRoverAvailability() {
        console.log('🔍 Checking rover system availability...');
        const result = await fetchJSON('/api/rover/test');
        
        console.log('📡 Rover test response:', result);
        
        if (result.error) {
            state.roverAvailable = false;
            state.navEnabled = false;
            updateNavSystemStatus('unavailable', 'Niedostępny');
            console.warn('❌ Rover system not available:', result.error);
            console.warn('📋 State:', { roverAvailable: state.roverAvailable, navEnabled: state.navEnabled });
            return false;
        }
        
        if (result.status === 'ok') {
            state.roverAvailable = true;
            state.navEnabled = true;
            updateNavSystemStatus('ready', 'Gotowy ✓');
            console.log('✅ Rover navigation system available');
            console.log('📋 State:', { roverAvailable: state.roverAvailable, navEnabled: state.navEnabled });
            return true;
        }
        
        // Fallback - jeśli odpowiedź jest inna niż oczekiwana
        state.roverAvailable = false;
        state.navEnabled = false;
        updateNavSystemStatus('unavailable', 'Niedostępny');
        console.warn('⚠️ Unexpected rover response format:', result);
        console.warn('📋 State:', { roverAvailable: state.roverAvailable, navEnabled: state.navEnabled });
        return false;
    }
    
    function updateNavSystemStatus(className, text) {
        if (ui.navSystemStatus) {
            ui.navSystemStatus.className = className;
            ui.navSystemStatus.textContent = text;
        }
    }
    
    // ==========================================
    // STATUS UPDATES
    // ==========================================
    function updateStatus(p) {
        const bar = document.getElementById('rtkBar');
        
        if (!p || p.error) {
            ui.fix.textContent = p && p.error ? 'Brak' : 'Błąd';
            ui.fix.className = 'badge badge-error';
            if (bar) {
                bar.className = 'rtk-bar rtk-unknown';
                bar.textContent = 'RTK: brak danych';
            }
            return;
        }
        
        // Normalize status variants
        let raw = p.rtk_status || '--';
        let norm = raw.replace(/\s+/g, '_').toUpperCase();
        
        ui.fix.textContent = raw;
        ui.sat.textContent = 'Sats: ' + (p.satellites ?? '--');
        const hd = p.hdop;
        ui.hdop.textContent = 'HDOP: ' + (typeof hd === 'number' ? hd.toFixed(1) : '--');
        ui.mode.textContent = norm === 'RTK_FIXED' ? 'RTK' : 'GPS';
        
        let fixClass = 'badge-gps';
        if (norm === 'RTK_FIXED') fixClass = 'badge-fixed';
        else if (norm === 'RTK_FLOAT') fixClass = 'badge-float';
        ui.fix.className = 'badge ' + fixClass;
        
        if (bar) {
            let barCls = 'rtk-unknown';
            if (norm === 'RTK_FIXED') barCls = 'rtk-fixed';
            else if (norm === 'RTK_FLOAT') barCls = 'rtk-float';
            else if (norm === 'DGPS') barCls = 'rtk-dgps';
            else if (norm === 'SINGLE') barCls = 'rtk-single';
            else if (norm === 'NO_FIX') barCls = 'rtk-nofix';
            
            bar.className = 'rtk-bar ' + barCls;
            bar.textContent = 'RTK: ' + raw;
        }
    }
    
    // ==========================================
    // GPS TRACKING
    // ==========================================
    function needsNewPoint(lat, lon) {
        if (!state.last) return true;
        const dLat = lat - state.last[0];
        const dLon = lon - state.last[1];
        return Math.hypot(dLat, dLon) >= state.minDist;
    }
    
    function addTrackPoint(lat, lon) {
        state.track.push([lat, lon]);
        state.poly.addLatLng([lat, lon]);
        state.last = [lat, lon];
    }
    
    function setMarker(lat, lon) {
        if (!state.marker) {
            state.marker = L.marker([lat, lon]).addTo(state.map);
        } else {
            state.marker.setLatLng([lat, lon]);
        }
    }
    
    async function pollPosition() {
        const dRaw = await fetchJSON(API.position);
        let d = dRaw;
        
        // Normalize fields
        if (d && !d.error) {
            if (typeof d.lat === 'string') d.lat = parseFloat(d.lat);
            if (typeof d.lon === 'string') d.lon = parseFloat(d.lon);
            if (typeof d.altitude === 'string') d.altitude = parseFloat(d.altitude);
            if (typeof d.speed_knots === 'string') d.speed_knots = parseFloat(d.speed_knots);
            if (typeof d.heading === 'string') d.heading = parseFloat(d.heading);
        }
        
        if (d && !d.error && typeof d.lat === 'number' && typeof d.lon === 'number') {
            ui.lat.textContent = d.lat.toFixed(7);
            ui.lon.textContent = d.lon.toFixed(7);
            ui.alt.textContent = typeof d.altitude === 'number' ? d.altitude.toFixed(1) : '--';
            ui.time.textContent = d.timestamp || '--';
            ui.speed.textContent = (typeof d.speed_knots === 'number' && !isNaN(d.speed_knots)) 
                ? d.speed_knots.toFixed(2) 
                : '--';
            ui.heading.textContent = (typeof d.heading === 'number' && !isNaN(d.heading)) 
                ? d.heading.toFixed(1) 
                : '--';
            
            setMarker(d.lat, d.lon);
            
            if (state.drawing && needsNewPoint(d.lat, d.lon)) {
                addTrackPoint(d.lat, d.lon);
            }
            
            if (!state.centered) {
                state.map.setView([d.lat, d.lon], 18);
                state.centered = true;
            }
            
            if (state.follow) {
                state.map.panTo([d.lat, d.lon]);
            }
        } else if (d && d.error) {
            ui.time.textContent = new Date().toISOString();
        }
        
        updateStatus(d);
        setTimeout(pollPosition, 1000);
    }
    
    // ==========================================
    // WAYPOINT MANAGEMENT
    // ==========================================
    function renderWaypoints() {
        ui.list.innerHTML = '';
        state.wpLayer.clearLayers();
        
        state.wps.forEach((w, i) => {
            const li = document.createElement('li');
            li.className = 'waypoint-item';
            li.innerHTML = `
                <span>${i + 1}. ${w.name}</span>
                <span class="coord">${w.lat.toFixed(6)}, ${w.lon.toFixed(6)}</span>
                <button data-i="${i}" class="go" title="Jedź do punktu">⤴</button>
                <button data-i="${i}" class="nav" title="Pokaż na mapie">👁</button>
                <button data-i="${i}" class="del" title="Usuń">✖</button>
            `;
            ui.list.appendChild(li);
            
            // Add marker
            L.circleMarker([w.lat, w.lon], {
                radius: 6,
                color: '#ff9500',
                fillColor: '#ff9500',
                fillOpacity: 0.9
            }).bindTooltip(w.name).addTo(state.wpLayer);
        });
    }
    
    async function addWaypoint(name, lat, lon) {
        // Use current position if lat/lon not provided
        if (lat === undefined || lon === undefined) {
            if (!state.last) {
                alert('Brak pozycji GPS');
                return false;
            }
            lat = state.last[0];
            lon = state.last[1];
        }
        
        const label = name && name.trim() ? name.trim() : 'WP' + (state.wps.length + 1);
        
        console.log('📍 Adding waypoint:', { name: label, lat, lon });
        console.log('🔍 Navigation state:', { 
            navEnabled: state.navEnabled, 
            roverAvailable: state.roverAvailable,
            willSendToBackend: state.navEnabled && state.roverAvailable
        });
        
        // If rover navigation available, send to backend
        if (state.navEnabled && state.roverAvailable) {
            console.log('📤 Sending waypoint to backend:', API.addWaypoint);
            const result = await postJSON(API.addWaypoint, { lat, lon, name: label });
            
            console.log('📥 Backend response:', result);
            
            if (result.error) {
                console.error('❌ Failed to add waypoint to navigation system:', result.error);
                alert(`⚠️ Błąd nawigacji: ${result.error}\n\nPunkt zostanie dodany lokalnie.`);
                // Fall back to local storage
            } else {
                console.log('✅ Waypoint added to navigation system:', result);
                // Success - no need for popup, user sees waypoint on map and in list
            }
        } else {
            console.warn('⚠️ Navigation not available - waypoint added to local storage only');
            console.warn('Reasons:', {
                navEnabled: state.navEnabled,
                roverAvailable: state.roverAvailable
            });
        }
        
        // Always add to local list for display
        state.wps.push({ name: label, lat, lon });
        ui.wpName.value = '';
        renderWaypoints();
        return true;
    }
    
    async function clearWaypoints() {
        if (state.navEnabled && state.roverAvailable) {
            const result = await fetchJSON(API.clearWaypoints, { method: 'DELETE' });
            if (result.error) {
                console.error('Failed to clear navigation waypoints:', result.error);
            } else {
                console.log('✅ Navigation waypoints cleared');
            }
        }
        
        state.wps = [];
        renderWaypoints();
    }
    
    function exportWaypoints() {
        const data = 'data:application/json,' + encodeURIComponent(JSON.stringify(state.wps, null, 2));
        const a = document.createElement('a');
        a.href = data;
        a.download = 'waypoints.json';
        document.body.appendChild(a);
        a.click();
        a.remove();
    }
    
    // ==========================================
    // NAVIGATION CONTROL
    // ==========================================
    async function startNavigation() {
        console.log('[START NAV] Button clicked');
        console.log('[START NAV] State:', {
            navEnabled: state.navEnabled,
            roverAvailable: state.roverAvailable,
            waypointCount: state.wps.length,
            navRunning: state.navRunning
        });
        
        if (!state.navEnabled || !state.roverAvailable) {
            const msg = `System nawigacji niedostępny\n\nnavEnabled: ${state.navEnabled}\nroverAvailable: ${state.roverAvailable}`;
            console.error('[START NAV] ' + msg);
            alert(msg);
            return;
        }
        
        if (state.wps.length === 0) {
            console.warn('[START NAV] No waypoints in queue');
            alert('⚠️ Brak punktów do nawigacji!\n\nDodaj co najmniej jeden punkt przed startem.');
            return;
        }
        
        try {
            console.log('[START NAV] Sending request to:', API.startNavigation);
            const result = await postJSON(API.startNavigation, {});
            console.log('[START NAV] Backend response:', result);
            
            if (result.error) {
                alert('Błąd rozpoczęcia nawigacji: ' + result.error);
                console.error('[START NAV] Error from backend:', result);
            } else {
                console.log('✅ [START NAV] Navigation started successfully');
                alert(`🚀 Nawigacja rozpoczęta!\n\nPunkty do osiągnięcia: ${state.wps.length}`);
                state.navRunning = true;
                
                // Show first waypoint as target
                if (state.wps.length > 0) {
                    const wp = state.wps[0];
                    console.log('[START NAV] Setting target marker at:', wp);
                    
                    if (state.targetMarker) {
                        state.targetMarker.setLatLng([wp.lat, wp.lon]);
                    } else {
                        state.targetMarker = L.marker([wp.lat, wp.lon], {
                            icon: L.icon({
                                iconUrl: 'data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0Ij48cGF0aCBmaWxsPSIjZmYwMDAwIiBkPSJNMTIgMmwtMSAxdi00bDEgMXYyem0wIDJsLTEgMS0xLTFoMnptMCAybC0xIDEtMS0xaDJ6bTAgMmwtMSAxLTEtMWgyem0wIDJsLTEgMS0xLTFoMnptMCAybC0xIDEtMS0xaDJ6bTAgMmwtMSAxLTEtMWgyeiIvPjwvc3ZnPg==',
                                iconSize: [32, 32],
                                iconAnchor: [16, 32]
                            })
                        }).addTo(state.map);
                    }
                }
                
                // Force refresh navigation status after start
                console.log('[START NAV] Refreshing navigation status...');
                setTimeout(async () => {
                    await pollNavStatus();
                }, 500);
            }
        } catch (err) {
            const errMsg = 'Błąd komunikacji z backendem: ' + err;
            console.error('[START NAV] Exception:', err);
            alert(errMsg);
        }
    }
    
    async function goToWaypoint(index) {
        if (!state.navEnabled || !state.roverAvailable) {
            alert('System nawigacji niedostępny');
            return;
        }
        
        const wp = state.wps[index];
        if (!wp) return;
        
        const result = await postJSON(API.goto, {
            lat: wp.lat,
            lon: wp.lon,
            name: wp.name
        });
        
        if (result.error) {
            alert('Błąd nawigacji: ' + result.error);
            console.error('Navigation error:', result);
        } else {
            console.log('✅ Navigation started to:', wp.name);
            alert(`🚀 Nawigacja do: ${wp.name}`);
            
            // Show target marker
            if (state.targetMarker) {
                state.targetMarker.setLatLng([wp.lat, wp.lon]);
            } else {
                state.targetMarker = L.marker([wp.lat, wp.lon], {
                    icon: L.icon({
                        iconUrl: 'data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0Ij48cGF0aCBmaWxsPSIjZmYwMDAwIiBkPSJNMTIgMmwtMSAxdi00bDEgMXYyem0wIDJsLTEgMS0xLTFoMnptMCAybC0xIDEtMS0xaDJ6bTAgMmwtMSAxLTEtMWgyem0wIDJsLTEgMS0xLTFoMnptMCAybC0xIDEtMS0xaDJ6bTAgMmwtMSAxLTEtMWgyeiIvPjwvc3ZnPg==',
                        iconSize: [32, 32],
                        iconAnchor: [16, 32]
                    })
                }).addTo(state.map);
            }
            
            state.currentTarget = wp;
            state.navRunning = true;
        }
    }
    
    async function emergencyStop() {
        console.log('[EMERGENCY STOP] Button clicked');
        
        if (!state.navEnabled || !state.roverAvailable) {
            console.warn('[EMERGENCY STOP] Navigation system not available');
            return;
        }
        
        if (!confirm('⚠️ AWARYJNE ZATRZYMANIE?\n\nTo natychmiast zatrzyma silniki i nawigację!')) {
            return;
        }
        
        console.log('[EMERGENCY STOP] Sending emergency stop request...');
        
        const stopResult = await postJSON(API.emergencyStop, {});
        
        if (stopResult.error) {
            console.error('[EMERGENCY STOP] Failed:', stopResult.error);
            alert('Błąd awaryjnego zatrzymania: ' + stopResult.error);
            return;
        }
        
        console.log('[EMERGENCY STOP] Success - motors stopped, navigation paused');
        alert('🛑 AWARYJNE ZATRZYMANIE aktywowane\n\nSilniki zatrzymane, nawigacja wstrzymana\n\nKliknij WZNÓW aby kontynuować lub ANULUJ aby zakończyć');
        
        // Update UI state
        state.navRunning = false;
        if (state.targetMarker) {
            state.map.removeLayer(state.targetMarker);
            state.targetMarker = null;
        }
        
        // Force refresh navigation status
        setTimeout(async () => {
            await pollNavStatus();
        }, 500);
    }
    
    async function pauseNavigation() {
        console.log('[PAUSE NAV] Button clicked');
        
        if (!state.navEnabled || !state.roverAvailable) {
            console.warn('[PAUSE NAV] Navigation system not available');
            return;
        }
        
        console.log('[PAUSE NAV] Sending pause request...');
        const result = await postJSON(API.pause, {});
        
        if (result.error) {
            console.error('[PAUSE NAV] Failed:', result.error);
            alert('Błąd pauzowania nawigacji: ' + result.error);
        } else {
            console.log('[PAUSE NAV] Success');
            alert('⏸️ Nawigacja wstrzymana\n\nKliknij WZNÓW aby kontynuować');
        }
        
        // Refresh status
        setTimeout(async () => {
            await pollNavStatus();
        }, 500);
    }
    
    async function resumeNavigation() {
        console.log('[RESUME NAV] Button clicked');
        
        if (!state.navEnabled || !state.roverAvailable) {
            console.warn('[RESUME NAV] Navigation system not available');
            return;
        }
        
        console.log('[RESUME NAV] Sending resume request...');
        const result = await postJSON(API.resume, {});
        
        if (result.error) {
            console.error('[RESUME NAV] Failed:', result.error);
            alert('Błąd wznawiania nawigacji: ' + result.error);
        } else {
            console.log('[RESUME NAV] Success');
            alert('▶️ Nawigacja wznowiona');
            state.navRunning = true;
        }
        
        // Refresh status
        setTimeout(async () => {
            await pollNavStatus();
        }, 500);
    }
    
    async function cancelNavigation() {
        console.log('[CANCEL NAV] Button clicked');
        
        if (!state.navEnabled || !state.roverAvailable) {
            console.warn('[CANCEL NAV] Navigation system not available');
            return;
        }
        
        if (!confirm('❌ Anulować nawigację?\n\nTo wyczyści wszystkie punkty i zatrzyma robota.')) {
            return;
        }
        
        console.log('[CANCEL NAV] Sending cancel request...');
        const result = await postJSON(API.cancel, {});
        
        if (result.error) {
            console.error('[CANCEL NAV] Failed:', result.error);
            alert('Błąd anulowania nawigacji: ' + result.error);
        } else {
            console.log('[CANCEL NAV] Success - navigation cancelled');
            alert('❌ Nawigacja anulowana\n\nWszystko zatrzymane i wyczyszczone');
            
            // Update UI state
            state.navRunning = false;
            if (state.targetMarker) {
                state.map.removeLayer(state.targetMarker);
                state.targetMarker = null;
            }
        }
        
        // Refresh status
        setTimeout(async () => {
            await pollNavStatus();
        }, 500);
    }
    
    // ==========================================
    // MAP INTERACTION
    // ==========================================
    async function onMapClick(e) {
        console.log('🖱️ [MAP CLICK] Event fired!', e.latlng);
        console.log('🖱️ [MAP CLICK] clickToAddMode:', state.clickToAddMode);
        console.log('🖱️ [MAP CLICK] Full state:', {
            clickToAddMode: state.clickToAddMode,
            navEnabled: state.navEnabled,
            roverAvailable: state.roverAvailable,
            waypointCount: state.wps.length
        });
        
        if (!state.clickToAddMode) {
            console.warn('🖱️ [MAP CLICK] Ignored - click mode is DISABLED');
            console.warn('🖱️ [MAP CLICK] Click the "🖱️ Klik" button to enable click-to-add mode');
            return;
        }
        
        console.log('🖱️ [MAP CLICK] Click mode ENABLED - showing prompt...');
        
        const { lat, lng } = e.latlng;
        const name = prompt('Nazwa punktu:', `WP${state.wps.length + 1}`);
        
        if (name !== null) {
            console.log('🖱️ [MAP CLICK] User entered name:', name);
            console.log('🖱️ [MAP CLICK] Adding waypoint at:', lat, lng);
            await addWaypoint(name, lat, lng);
        } else {
            console.log('🖱️ [MAP CLICK] User cancelled prompt');
        }
    }
    
    // ==========================================
    // TRACK CONTROL
    // ==========================================
    function clearTrack() {
        state.track = [];
        state.poly.setLatLngs([]);
        state.last = null;
    }
    
    // ==========================================
    // EVENT HANDLERS
    // ==========================================
    function setupEventListeners() {
        // Map controls
        ui.c.addEventListener('click', () => {
            if (state.last) state.map.setView(state.last, 19);
        });
        
        ui.t.addEventListener('click', () => {
            state.drawing = !state.drawing;
            ui.t.classList.toggle('active', state.drawing);
        });
        
        ui.clr.addEventListener('click', clearTrack);
        
        // Waypoint controls
        ui.add.addEventListener('click', () => addWaypoint(ui.wpName.value));
        
        // Toggle click-to-add mode
        console.log('[INIT] Setting up click-to-add toggle button...');
        console.log('[INIT] toggleClickAdd element:', ui.toggleClickAdd);
        
        if (ui.toggleClickAdd) {
            console.log('[INIT] Adding click listener to toggle button');
            ui.toggleClickAdd.addEventListener('click', () => {
                const oldMode = state.clickToAddMode;
                state.clickToAddMode = !state.clickToAddMode;
                ui.toggleClickAdd.classList.toggle('active', state.clickToAddMode);
                
                console.log('🖱️🖱️🖱️ [CLICK MODE TOGGLE] Clicked!');
                console.log('🖱️ [CLICK MODE] Changed from', oldMode, 'to', state.clickToAddMode);
                
                if (state.clickToAddMode) {
                    console.log('✅ [CLICK MODE] ENABLED - click on map to add waypoints');
                    ui.toggleClickAdd.textContent = '🖱️ Klik ✓';
                    ui.toggleClickAdd.title = 'Tryb dodawania WŁĄCZONY - kliknij na mapę aby dodać punkt';
                    alert('✅ Tryb klikania WŁĄCZONY\n\nKliknij na mapę aby dodać punkt');
                } else {
                    console.log('❌ [CLICK MODE] DISABLED');
                    ui.toggleClickAdd.textContent = '🖱️ Klik';
                    ui.toggleClickAdd.title = 'Przełącz tryb dodawania kliknięciem na mapę';
                }
            });
        } else {
            console.error('[INIT] ❌ Toggle button NOT FOUND! Check HTML for id="btnToggleClickAdd"');
        }
        
        ui.exp.addEventListener('click', exportWaypoints);
        ui.wclr.addEventListener('click', () => {
            if (confirm('Usunąć wszystkie punkty?')) {
                clearWaypoints();
            }
        });
        
        // Navigation controls
        console.log('[INIT] Setting up navigation controls...');
        
        if (ui.btnStartNav) {
            ui.btnStartNav.addEventListener('click', startNavigation);
        }
        
        if (ui.btnPauseNav) {
            ui.btnPauseNav.addEventListener('click', pauseNavigation);
        }
        
        if (ui.btnResumeNav) {
            ui.btnResumeNav.addEventListener('click', resumeNavigation);
        }
        
        if (ui.btnEmergencyStop) {
            ui.btnEmergencyStop.addEventListener('click', emergencyStop);
        }
        
        if (ui.btnCancelNav) {
            ui.btnCancelNav.addEventListener('click', cancelNavigation);
        }
        
        // Check rover button
        const btnCheckRover = document.getElementById('btnCheckRover');
        if (btnCheckRover) {
            btnCheckRover.addEventListener('click', async () => {
                console.log('🔄 Manual rover system check triggered');
                btnCheckRover.disabled = true;
                btnCheckRover.textContent = '⏳ Sprawdzanie...';
                
                await checkRoverAvailability();
                
                btnCheckRover.disabled = false;
                btnCheckRover.textContent = '🔄 Sprawdź ponownie';
            });
        }
        
        // Waypoint list actions
        ui.list.addEventListener('click', e => {
            const i = e.target.getAttribute('data-i');
            if (i === null) return;
            
            const index = parseInt(i);
            
            if (e.target.classList.contains('go')) {
                goToWaypoint(index);
            } else if (e.target.classList.contains('nav')) {
                const wp = state.wps[index];
                state.map.setView([wp.lat, wp.lon], 20);
            } else if (e.target.classList.contains('del')) {
                if (confirm(`Usunąć punkt ${state.wps[index].name}?`)) {
                    state.wps.splice(index, 1);
                    renderWaypoints();
                }
            }
        });
        
        // Keyboard shortcuts
        document.addEventListener('keydown', e => {
            if (e.key === 'Escape' && state.navRunning) {
                emergencyStop();
            }
        });
    }
    
    // ==========================================
    // INITIALIZATION
    // ==========================================
    async function init() {
        console.log('🚀 RTK Rover Map Interface starting...');
        
        initMap();
        setupEventListeners();
        
        // Check rover system availability
        await checkRoverAvailability();
        
        if (state.roverAvailable) {
            console.log('✅ Navigation system ready');
            console.log('💡 Tip: Kliknij "Go" przy punkcie aby rozpocząć nawigację');
        } else {
            console.log('ℹ️ Navigation system not available (modules not installed)');
            console.log('📍 Waypoints will be tracked locally only');
        }
        
        // Start position polling
        pollPosition();
    }
    
    // Start when DOM ready
    document.addEventListener('DOMContentLoaded', init);
    
    // Export for console debugging
    window.roverDebug = {
        state,
        API,
        addWaypoint,
        startNavigation,
        pauseNavigation,
        resumeNavigation,
        cancelNavigation,
        goToWaypoint,
        emergencyStop,
        checkRoverAvailability
    };
    
})();
