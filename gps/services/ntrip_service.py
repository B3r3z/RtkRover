import logging
import time
import threading
import queue
from typing import List, Optional
from ..ntrip_client import NTRIPClient
from ..core.interfaces import NTRIPService
from config.nmea_utils import build_dummy_gga

logger = logging.getLogger(__name__)

class NTRIPServiceAdapter(NTRIPService):
    def __init__(self, config: dict):
        self.config = config
        self.client: Optional[NTRIPClient] = None
        self._last_reconnect_attempt = 0
        self._reconnect_interval = 30.0  # seconds
        self._max_reconnect_attempts = 5
        self._consecutive_failures = 0
        
        self._rtcm_queue = queue.Queue(maxsize=100)
        self._lock = threading.Lock()
        self._dummy_gga_data = build_dummy_gga().encode('ascii')
        
    def connect(self) -> bool:
        if not self.config.get('enabled', False):
            return False
            
        try:
            self.client = NTRIPClient(
                config=self.config,
                gga_callback=self._get_dummy_gga
            )
            
            if self.client.connect():
                success = self.client.start_data_reception(self._on_rtcm_data)
                if success:
                    logger.info("✅ NTRIP client connected and data reception started")
                    return True
                else:
                    logger.error("❌ Failed to start NTRIP data reception")
                    return False
            else:
                logger.error("❌ Failed to connect NTRIP client")
                return False
        except Exception as e:
            logger.error(f"NTRIP connection failed: {e}")
            return False
    
    def _on_rtcm_data(self, data: bytes):
        try:
            if data:
                if not self._rtcm_queue.full():
                    self._rtcm_queue.put(data, block=False)
                else:
                    logger.warning("⚠️ RTCM buffer full, dropping data")
        except Exception as e:
            logger.error(f"Error handling RTCM data: {e}")
    
    def _get_dummy_gga(self) -> Optional[bytes]:
        return self._dummy_gga_data
    
    def send_gga(self, gga_data: bytes) -> bool:
        if not self.client:
            self._attempt_reconnect()
            return False
            
        try:
            result = self.client.send_gga(gga_data)
            if result:
                self._consecutive_failures = 0
                # Suppressed verbose logging
                # logger.debug(f"GGA sent successfully ({result} bytes)")
                return True
            else:
                self._handle_connection_failure()
                return False
        except Exception as e:
            logger.debug(f"GGA send failed: {e}")
            self._handle_connection_failure()
            return False
    
    def _handle_connection_failure(self):
        self._consecutive_failures += 1
        logger.warning(f"NTRIP connection issue (failure #{self._consecutive_failures})")
        
        if self._consecutive_failures >= 3:
            logger.warning("Multiple NTRIP failures detected, disconnecting...")
            self.disconnect()
            self._attempt_reconnect()
    
    def _attempt_reconnect(self):
        current_time = time.time()
        
        if current_time - self._last_reconnect_attempt < self._reconnect_interval:
            return False
            
        if self._consecutive_failures >= self._max_reconnect_attempts:
            logger.error(f"Max NTRIP reconnect attempts ({self._max_reconnect_attempts}) exceeded")
            return False
            
        self._last_reconnect_attempt = current_time
        logger.info("🔄 Attempting NTRIP reconnection...")
        
        self.disconnect()
        
        if self.connect():
            logger.info("✅ NTRIP reconnected successfully")
            self._consecutive_failures = 0
            return True
        else:
            logger.warning("❌ NTRIP reconnection failed")
            return False
    
    def get_rtcm_data(self) -> List[bytes]:
        rtcm_messages = []
        try:
            while not self._rtcm_queue.empty():
                try:
                    data = self._rtcm_queue.get_nowait()
                    rtcm_messages.append(data)
                except queue.Empty:
                    break
            
        except Exception as e:
            logger.error(f"Error getting RTCM data: {e}")
        
        return rtcm_messages
    
    def disconnect(self):
        if self.client:
            self.client.disconnect()
            self.client = None
    
    def is_connected(self) -> bool:
        connected = self.client is not None and self.client.is_connected()
        # Optimized: Removed debug logging that fires too frequently
        return connected