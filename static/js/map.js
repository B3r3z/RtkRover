// RTK Rover Frontend (rewritten)
// Features:
//  - Live position polling (/api/position)
//  - Track drawing (local in-browser polyline) with 1m granularity
//  - Clear track button
//  - Add waypoints at current position (named / auto numbering)
//  - Waypoint list: jump to (⤴) or delete (✖)
//  - Export waypoints to JSON (future path planning)
//  - Precision mode: forces higher zoom when RTK Fixed
//  - Center button: manual re-center
// Notes:
//  - No server persistence yet for waypoints/track (client memory only)
//  - Adjust st.minDist for different track resolution
//  - API errors degrade gracefully without breaking UI
//  - Keep script lean & framework-free
// TODO (future): persist waypoints via backend, import GPX, multi-track layers
(function(){
    const API = { position:'/api/position', track:'/api/track' };
        const st = { map:null, marker:null, track:[], poly:null, last:null, follow:true, precision:false, wps:[], wpLayer:null, minDist:0.00001, centered:false };
    const g = id=>document.getElementById(id);
    const ui = {lat:g('lat'),lon:g('lon'),alt:g('alt'),time:g('time'),speed:g('speed'),heading:g('heading'),mode:g('statusMode'),fix:g('statusFix'),sat:g('statusSat'),hdop:g('statusHdop'),
                            c:g('btnCenter'),p:g('btnPrecision'),clr:g('btnClearTrack'),wpName:g('wpName'),add:g('btnAddWp'),exp:g('btnExportWp'),wclr:g('btnClearWp'),list:g('waypointList')};
    // Basic missing element warning (in case template desync)
    Object.entries(ui).forEach(([k,v])=>{ if(!v) console.warn('UI element missing:',k); });
    let lastErrShown = 0;

    function initMap(){
        st.map = L.map('map');
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:22,attribution:'OSM'}).addTo(st.map);
        st.map.setView([52,19],6);
        st.poly = L.polyline([], {color:'#66cfff',weight:3,opacity:0.85}).addTo(st.map);
        st.wpLayer = L.layerGroup().addTo(st.map);
        setTimeout(()=> st.map.invalidateSize(), 150);
    }
    async function j(url){
        try{
            const r=await fetch(url,{cache:'no-store'});
            if(!r.ok) throw new Error(r.status);
            return await r.json();
        }catch(e){
            const now=Date.now();
            if(now-lastErrShown>5000){
                console.error('Fetch error', url, e);
                const bar=document.getElementById('rtkBar');
                if(bar) { bar.textContent='RTK: błąd połączenia'; bar.className='rtk-bar rtk-unknown'; }
                lastErrShown=now;
            }
            return {error:e.message};
        }
    }
        function updStatus(p){
            const bar=document.getElementById('rtkBar');
            if(!p||p.error){
                ui.fix.textContent=p&&p.error?'Brak':'Błąd';
                ui.fix.className='badge badge-error';
                if(bar){ bar.className='rtk-bar rtk-unknown'; bar.textContent='RTK: brak danych'; }
                return;
            }
            // Normalize status variants (e.g., 'RTK Float', 'RTK_FLOAT')
            let raw = p.rtk_status||'--';
            let norm = raw.replace(/\s+/g,'_').toUpperCase();
            ui.fix.textContent = raw; // show as server returns
            ui.sat.textContent='Sats: '+(p.satellites??'--');
            const hd=p.hdop; ui.hdop.textContent='HDOP: '+(typeof hd==='number'? hd.toFixed(1):'--');
            ui.mode.textContent= norm==='RTK_FIXED'?'RTK':'GPS';
            let fixClass='badge-gps';
            if(norm==='RTK_FIXED') fixClass='badge-fixed'; else if(norm==='RTK_FLOAT') fixClass='badge-float';
            ui.fix.className='badge '+fixClass;
            if(bar){
                let barCls='rtk-unknown';
                if(norm==='RTK_FIXED') barCls='rtk-fixed';
                else if(norm==='RTK_FLOAT') barCls='rtk-float';
                else if(norm==='DGPS') barCls='rtk-dgps';
                else if(norm==='SINGLE') barCls='rtk-single';
                else if(norm==='NO_FIX') barCls='rtk-nofix';
                bar.className='rtk-bar '+barCls;
                bar.textContent='RTK: '+raw;
            }
        }
    function need(lat,lon){ if(!st.last) return true; const dLat=lat-st.last[0], dLon=lon-st.last[1]; return Math.hypot(dLat,dLon)>=st.minDist; }
    function addPoint(lat,lon){ st.track.push([lat,lon]); st.poly.addLatLng([lat,lon]); st.last=[lat,lon]; }
    function setMarker(lat,lon){ if(!st.marker) st.marker=L.marker([lat,lon]).addTo(st.map); else st.marker.setLatLng([lat,lon]); }
        async function poll(){ const dRaw=await j(API.position); let d=dRaw; // Normalizacja pól
            if(d && !d.error){
                if(typeof d.lat==='string') d.lat=parseFloat(d.lat);
                if(typeof d.lon==='string') d.lon=parseFloat(d.lon);
                if(typeof d.altitude==='string') d.altitude=parseFloat(d.altitude);
                if(typeof d.speed_knots==='string') d.speed_knots=parseFloat(d.speed_knots);
                if(typeof d.heading==='string') d.heading=parseFloat(d.heading);
            }
            if(d && !d.error && typeof d.lat==='number' && typeof d.lon==='number'){
                ui.lat.textContent=d.lat.toFixed(7);
                ui.lon.textContent=d.lon.toFixed(7);
                ui.alt.textContent= typeof d.altitude==='number'? d.altitude.toFixed(1):'--';
                ui.time.textContent=d.timestamp||'--';
                ui.speed.textContent= (typeof d.speed_knots==='number' && !isNaN(d.speed_knots))? d.speed_knots.toFixed(2): '--';
                ui.heading.textContent= (typeof d.heading==='number' && !isNaN(d.heading))? d.heading.toFixed(1): '--';
                setMarker(d.lat,d.lon);
                if(need(d.lat,d.lon)) addPoint(d.lat,d.lon);
                if(!st.centered){ st.map.setView([d.lat,d.lon],18); st.centered=true; }
                if(st.follow) st.map.panTo([d.lat,d.lon]);
                if(st.precision && d.rtk_status==='RTK_FIXED' && st.map.getZoom()<20) st.map.setZoom(20);
            } else if(d && d.error){ ui.time.textContent=new Date().toISOString(); }
            updStatus(d); setTimeout(poll,1000); }
    function renderWps(){ ui.list.innerHTML=''; st.wpLayer.clearLayers(); st.wps.forEach((w,i)=>{ const li=document.createElement('li'); li.className='waypoint-item'; li.innerHTML=`<span>${i+1}. ${w.name}</span><span class="coord">${w.lat.toFixed(6)}, ${w.lon.toFixed(6)}</span><button data-i="${i}" class="go">⤴</button><button data-i="${i}" class="del">✖</button>`; ui.list.appendChild(li); L.circleMarker([w.lat,w.lon],{radius:6,color:'#ff9500',fillColor:'#ff9500',fillOpacity:.9}).bindTooltip(w.name).addTo(st.wpLayer); }); }
    function addWp(name){ if(!st.last) return; const label=name&&name.trim()?name.trim(): 'WP'+(st.wps.length+1); st.wps.push({name:label,lat:st.last[0],lon:st.last[1]}); ui.wpName.value=''; renderWps(); }
    function expWp(){ const data='data:application/json,'+encodeURIComponent(JSON.stringify(st.wps,null,2)); const a=document.createElement('a'); a.href=data; a.download='waypoints.json'; document.body.appendChild(a); a.click(); a.remove(); }
    function clrWp(){ st.wps=[]; renderWps(); }
    function clrTrack(){ st.track=[]; st.poly.setLatLngs([]); st.last=null; }
    function events(){ ui.c.addEventListener('click', ()=>{ if(st.last) st.map.setView(st.last,19); }); ui.p.addEventListener('click', ()=>{ st.precision=!st.precision; ui.p.classList.toggle('active', st.precision); }); ui.clr.addEventListener('click', clrTrack); ui.add.addEventListener('click', ()=> addWp(ui.wpName.value)); ui.exp.addEventListener('click', expWp); ui.wclr.addEventListener('click', clrWp); ui.list.addEventListener('click', e=>{ const i=e.target.getAttribute('data-i'); if(i===null) return; if(e.target.classList.contains('go')) st.map.setView([st.wps[i].lat, st.wps[i].lon],20); else if(e.target.classList.contains('del')){ st.wps.splice(i,1); renderWps(); } }); }
    function init(){ initMap(); events(); poll(); }
    document.addEventListener('DOMContentLoaded', init);
})();
