import threading
import time
import logging
import queue
from typing import Optional, List
from .core.interfaces import (
    RTKSystemInterface, GPS, NTRIPService, PositionObserver,
    Position, RTKStats, RTKStatus
)

logger = logging.getLogger(__name__)

class RTKSystem(RTKSystemInterface):
    def __init__(self, gps: GPS, ntrip_service: Optional[NTRIPService] = None):
        self.gps = gps
        self.ntrip_service = ntrip_service
        self.observers: List[PositionObserver] = []
        
        self.running = False
        self.current_position: Optional[Position] = None
        self.rtcm_queue = queue.Queue(maxsize=100)
        
        self._position_lock = threading.Lock()
        self._threads: List[threading.Thread] = []
        self._stats = RTKStats(0, 0, 0.0, 0.0)
        self._start_time = 0
        self._position_count = 0
        self._last_position_log = 0
    
    def start(self) -> bool:
        if self.running:
            return True
            
        if not self.gps.connect():
            logger.error("GPS connection failed")
            return False
        
        self.running = True
        self._start_time = time.time()
        
        self._start_thread(self._position_loop, "PositionReader")
        self._start_thread(self._rtcm_writer_loop, "RTCMWriter")
        
        if self.ntrip_service:
            if self.ntrip_service.connect():
                self._start_thread(self._gga_upload_loop, "GGAUploader")
                self._start_thread(self._ntrip_monitor_loop, "NTRIPMonitor")
                self._start_thread(self._rtcm_reader_loop, "RTCMReader")
                logger.info("🌐 RTK system started with NTRIP connection")
            else:
                logger.warning("⚠️ NTRIP connection failed - running in GPS-only mode")
        else:
            logger.info("📍 RTK system started in GPS-only mode")
            
        return True
    
    def _start_thread(self, target, name: str):
        thread = threading.Thread(target=target, daemon=True, name=name)
        thread.start()
        self._threads.append(thread)
    
    def _position_loop(self):
        position_read_count = 0
        while self.running:
            position = self.gps.read_position()
            if position:
                position_read_count += 1
                logger.debug(f"📡 GPS read #{position_read_count}: {position.lat:.6f},{position.lon:.6f} {position.rtk_status.value}")
                self._update_position(position)
            else:
                # Prevent busy-waiting on read error
                time.sleep(0.1)
    
    def _update_position(self, position: Position):
        with self._position_lock:
            # Debug: Check if position actually changed
            position_changed = (not self.current_position or 
                              self.current_position.lat != position.lat or 
                              self.current_position.lon != position.lon or
                              self.current_position.rtk_status != position.rtk_status)
            
            if position_changed:
                old_pos = self.current_position
                logger.debug(f"🔄 Position UPDATE: {old_pos.lat:.6f},{old_pos.lon:.6f} -> {position.lat:.6f},{position.lon:.6f}" if old_pos else f"🔄 Position INITIAL: {position.lat:.6f},{position.lon:.6f}")
            
            self.current_position = position
            self._position_count += 1
            
        # Log position update every 1 second
        current_time = time.time()
        if current_time - self._last_position_log >= 1.0:
            logger.info(f"🎯 Position: {position.rtk_status.value}, "
                       f"Lat: {position.lat:.6f}, Lon: {position.lon:.6f}, "
                       f"Sats: {position.satellites}, HDOP: {position.hdop:.1f}")
            self._last_position_log = current_time
            
        for observer in self.observers:
            try:
                observer.on_position_update(position)
            except Exception as e:
                logger.error(f"Observer error: {e}")
    
    def _rtcm_reader_loop(self):
        """Read RTCM data from NTRIP service and add to queue"""
        rtcm_received_count = 0
        while self.running and self.ntrip_service:
            try:
                rtcm_messages = self.ntrip_service.get_rtcm_data()
                for rtcm_data in rtcm_messages:
                    rtcm_received_count += 1
                    
                    if not self.rtcm_queue.full():
                        self.rtcm_queue.put(rtcm_data, block=False)
                        
                    else:
                        logger.warning(f"⚠️ RTCM queue full, dropping message #{rtcm_received_count}")
                
                time.sleep(0.1)  # Check for new RTCM data every 100ms
            except Exception as e:
                logger.error(f"RTCM reader error: {e}")
                time.sleep(1.0)

    def _rtcm_writer_loop(self):
        rtcm_count = 0
        while self.running:
            try:
                rtcm_data = self.rtcm_queue.get(timeout=1.0)
                rtcm_count += 1
                
                if self.gps.write_rtcm(rtcm_data):
                    self._stats.rtcm_messages += 1
                else:
                    logger.warning(f"❌ RTCM #{rtcm_count}: Failed to write to GPS")
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"RTCM write error: {e}")
    
    def _gga_upload_loop(self):
        upload_count = 0
        while self.running and self.ntrip_service:
            try:
                gga_data = self._build_gga()
                if gga_data:
                    upload_count += 1
                    if not self.ntrip_service.send_gga(gga_data):
                        logger.warning("Failed to send GGA, backing off for 5s")
                        time.sleep(5.0)
                
                # Wait before sending next GGA
                time.sleep(1.0)
            except Exception as e:
                logger.error(f"GGA upload error: {e}")
                time.sleep(5.0) # Wait longer on error
    
    def _ntrip_monitor_loop(self):
        """Monitor NTRIP connection health"""
        last_status_log = 0
        while self.running and self.ntrip_service:
            try:
                current_time = time.time()
                is_connected = self.ntrip_service.is_connected()
                
                # Log status every 60 seconds at debug level
                if current_time - last_status_log >= 60.0:
                    status = "🌐 CONNECTED" if is_connected else "❌ DISCONNECTED"
                    logger.debug(f"NTRIP Status: {status}")
                    last_status_log = current_time
                
                # If disconnected, log more frequently
                if not is_connected and current_time - last_status_log >= 10.0:
                    logger.warning("⚠️ NTRIP connection lost - auto-reconnect will attempt")
                    last_status_log = current_time
                
                time.sleep(10.0)
            except Exception as e:
                logger.error(f"NTRIP monitor error: {e}")
                time.sleep(30.0)
    
    def _build_gga(self) -> Optional[bytes]:
        with self._position_lock:
            if not self.current_position:
                return None
            pos = self.current_position
        
        lat = abs(pos.lat)
        lat_deg = int(lat)
        lat_min = (lat - lat_deg) * 60
        lat_ns = "N" if pos.lat >= 0 else "S"
        
        lon = abs(pos.lon)
        lon_deg = int(lon)
        lon_min = (lon - lon_deg) * 60
        lon_ew = "E" if pos.lon >= 0 else "W"
        
        gga = (f"$GNGGA,{time.strftime('%H%M%S')},"
               f"{lat_deg:02d}{lat_min:07.4f},{lat_ns},"
               f"{lon_deg:03d}{lon_min:07.4f},{lon_ew},"
               f"1,{pos.satellites},{pos.hdop:.1f},{pos.altitude:.1f},M,0.0,M,,*00")
        
        return gga.encode('ascii')
    
    def stop(self):
        logger.info("Stopping RTK system")
        self.running = False
        
        for thread in self._threads:
            thread.join(timeout=2.0)
        
        if self.ntrip_service:
            self.ntrip_service.disconnect()
        
        self.gps.close()
        logger.info("RTK system stopped")
    
    def get_status(self) -> RTKStats:
        uptime = time.time() - self._start_time if self._start_time else 0
        return RTKStats(
            rtcm_messages=self._stats.rtcm_messages,
            nmea_errors=self._stats.nmea_errors,
            connection_uptime=uptime,
            avg_latency=0.0
        )
    
    def get_current_position(self) -> Optional[Position]:
        with self._position_lock:
            return self.current_position
    
    def add_position_observer(self, observer: PositionObserver):
        self.observers.append(observer)
