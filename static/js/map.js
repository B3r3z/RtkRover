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
    const st = { map:null, marker:null, track:[], poly:null, last:null, follow:true, precision:false, wps:[], wpLayer:null, minDist:0.00001 };
    const g = id=>document.getElementById(id);
    const ui = {lat:g('lat'),lon:g('lon'),alt:g('alt'),time:g('time'),mode:g('statusMode'),fix:g('statusFix'),sat:g('statusSat'),hdop:g('statusHdop'),
                            c:g('btnCenter'),p:g('btnPrecision'),clr:g('btnClearTrack'),wpName:g('wpName'),add:g('btnAddWp'),exp:g('btnExportWp'),wclr:g('btnClearWp'),list:g('waypointList')};

    function initMap(){
        st.map = L.map('map');
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:22,attribution:'OSM'}).addTo(st.map);
        st.map.setView([52,19],6);
        st.poly = L.polyline([], {color:'#1e90ff',weight:3}).addTo(st.map);
        st.wpLayer = L.layerGroup().addTo(st.map);
    }
    async function j(url){ try{ const r=await fetch(url,{cache:'no-store'}); if(!r.ok) throw new Error(r.status); return await r.json(); }catch(e){ return {error:e.message}; } }
    function updStatus(p){ if(!p||p.error){ ui.fix.textContent=p&&p.error?'Brak':'Błąd'; ui.fix.className='badge badge-error'; return;} ui.fix.textContent=p.rtk_status||'--'; ui.sat.textContent='Sats: '+(p.satellites??'--'); ui.hdop.textContent='HDOP: '+(p.hdop?.toFixed? p.hdop.toFixed(1):'--'); ui.mode.textContent=p.rtk_status==='RTK_FIXED'?'RTK':'GPS'; ui.fix.className='badge '+(p.rtk_status==='RTK_FIXED'?'badge-fixed':p.rtk_status==='RTK_FLOAT'?'badge-float':'badge-gps'); }
    function need(lat,lon){ if(!st.last) return true; const dLat=lat-st.last[0], dLon=lon-st.last[1]; return Math.hypot(dLat,dLon)>=st.minDist; }
    function addPoint(lat,lon){ st.track.push([lat,lon]); st.poly.addLatLng([lat,lon]); st.last=[lat,lon]; }
    function setMarker(lat,lon){ if(!st.marker) st.marker=L.marker([lat,lon]).addTo(st.map); else st.marker.setLatLng([lat,lon]); }
    async function poll(){ const d=await j(API.position); if(d && !d.error){ ui.lat.textContent=d.lat?.toFixed?d.lat.toFixed(7):'--'; ui.lon.textContent=d.lon?.toFixed?d.lon.toFixed(7):'--'; ui.alt.textContent=d.altitude?.toFixed?d.altitude.toFixed(1):'--'; ui.time.textContent=d.timestamp||'--'; if(typeof d.lat==='number'&& typeof d.lon==='number'){ setMarker(d.lat,d.lon); if(need(d.lat,d.lon)) addPoint(d.lat,d.lon); if(st.follow) st.map.setView([d.lat,d.lon], st.map.getZoom()<17?18:st.map.getZoom()); if(st.precision && d.rtk_status==='RTK_FIXED' && st.map.getZoom()<20) st.map.setZoom(20);} }
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
