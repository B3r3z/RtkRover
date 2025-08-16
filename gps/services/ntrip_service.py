import logging
import time
from typing import List, Optional
from ..ntrip_client import NTRIPClient
from ..core.interfaces import NTRIPService

logger = logging.getLogger(__name__)

class NTRIPServiceAdapter(NTRIPService):
    def __init__(self, config: dict):
        self.config = config
        self.client: Optional[NTRIPClient] = None
        self._last_reconnect_attempt = 0
        self._reconnect_interval = 30.0  # seconds
        self._max_reconnect_attempts = 5
        self._consecutive_failures = 0
        
    def connect(self) -> bool:
        if not self.config.get('enabled', False):
            return False
            
        try:
            self.client = NTRIPClient(
                config=self.config,
                gga_callback=self._get_dummy_gga
            )
            return self.client.connect()
        except Exception as e:
            logger.error(f"NTRIP connection failed: {e}")
            return False
    
    def _get_dummy_gga(self) -> Optional[bytes]:
        from config.nmea_utils import build_dummy_gga
        return build_dummy_gga().encode('ascii')
    
    def send_gga(self, gga_data: bytes) -> bool:
        if not self.client:
            self._attempt_reconnect()
            return False
            
        try:
            result = self.client.send_gga(gga_data)
            if result:
                # Reset failure counter on success
                self._consecutive_failures = 0
                return True
            else:
                # Connection might be broken, try reconnect
                self._handle_connection_failure()
                return False
        except Exception as e:
            logger.debug(f"GGA send failed: {e}")
            self._handle_connection_failure()
            return False
    
    def _handle_connection_failure(self):
        """Handle connection failure and attempt reconnect"""
        self._consecutive_failures += 1
        logger.warning(f"NTRIP connection issue (failure #{self._consecutive_failures})")
        
        if self._consecutive_failures >= 3:
            logger.warning("Multiple NTRIP failures detected, disconnecting...")
            self.disconnect()
            self._attempt_reconnect()
    
    def _attempt_reconnect(self):
        """Attempt to reconnect to NTRIP service"""
        current_time = time.time()
        
        if current_time - self._last_reconnect_attempt < self._reconnect_interval:
            return False
            
        if self._consecutive_failures >= self._max_reconnect_attempts:
            logger.error(f"Max NTRIP reconnect attempts ({self._max_reconnect_attempts}) exceeded")
            return False
            
        self._last_reconnect_attempt = current_time
        logger.info("🔄 Attempting NTRIP reconnection...")
        
        # Clean disconnect first
        self.disconnect()
        
        # Attempt reconnect
        if self.connect():
            logger.info("✅ NTRIP reconnected successfully")
            self._consecutive_failures = 0
            return True
        else:
            logger.warning("❌ NTRIP reconnection failed")
            return False
    
    def get_rtcm_data(self) -> List[bytes]:
        return []
    
    def disconnect(self):
        if self.client:
            self.client.disconnect()
            self.client = None
    
    def is_connected(self) -> bool:
        """Check if NTRIP service is connected"""
        return self.client is not None and self.client.is_connected()
