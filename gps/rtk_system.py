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
        
        if self.ntrip_service and self.ntrip_service.connect():
            self._start_thread(self._gga_upload_loop, "GGAUploader")
            logger.info("RTK system started with NTRIP")
        else:
            logger.info("RTK system started in GPS-only mode")
            
        return True
    
    def _start_thread(self, target, name: str):
        thread = threading.Thread(target=target, daemon=True, name=name)
        thread.start()
        self._threads.append(thread)
    
    def _position_loop(self):
        while self.running:
            position = self.gps.read_position()
            if position:
                self._update_position(position)
            time.sleep(0.1)
    
    def _update_position(self, position: Position):
        with self._position_lock:
            self.current_position = position
            
        for observer in self.observers:
            try:
                observer.on_position_update(position)
            except Exception as e:
                logger.error(f"Observer error: {e}")
    
    def _rtcm_writer_loop(self):
        while self.running:
            try:
                rtcm_data = self.rtcm_queue.get(timeout=1.0)
                if self.gps.write_rtcm(rtcm_data):
                    self._stats.rtcm_messages += 1
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"RTCM write error: {e}")
    
    def _gga_upload_loop(self):
        while self.running and self.ntrip_service:
            try:
                if self.current_position:
                    gga_data = self._build_gga()
                    if gga_data:
                        self.ntrip_service.send_gga(gga_data)
                time.sleep(10.0)
            except Exception as e:
                logger.error(f"GGA upload error: {e}")
    
    def _build_gga(self) -> Optional[bytes]:
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
