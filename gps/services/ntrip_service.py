import logging
import time
import threading
import queue
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
        
        # Buffer for RTCM data
        self._rtcm_queue = queue.Queue(maxsize=100)
        self._lock = threading.Lock()
        
    def connect(self) -> bool:
        if not self.config.get('enabled', False):
            return False
            
        try:
            self.client = NTRIPClient(
                config=self.config,
                gga_callback=self._get_dummy_gga
            )
            
            if self.client.connect():
                # Start data reception with our callback
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
        """Callback for receiving RTCM data from NTRIP client"""
        try:
            if data:
                logger.info(f"📡 NTRIP: Received {len(data)} bytes of data")
                if not self._rtcm_queue.full():
                    self._rtcm_queue.put(data, block=False)
                    logger.debug(f"✅ RTCM data added to buffer ({self._rtcm_queue.qsize()} in queue)")
                else:
                    logger.warning("⚠️ RTCM buffer full, dropping data")
        except Exception as e:
            logger.error(f"Error handling RTCM data: {e}")
    
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
        """Get all available RTCM data from buffer"""
        rtcm_messages = []
        try:
            # Get all available data from queue
            while not self._rtcm_queue.empty():
                try:
                    data = self._rtcm_queue.get_nowait()
                    rtcm_messages.append(data)
                except queue.Empty:
                    break
            
            if rtcm_messages:
                logger.debug(f"📡 Returning {len(rtcm_messages)} RTCM messages from buffer")
            
        except Exception as e:
            logger.error(f"Error getting RTCM data: {e}")
        
        return rtcm_messages
    
    def disconnect(self):
        if self.client:
            self.client.disconnect()
            self.client = None
    
    def is_connected(self) -> bool:
        """Check if NTRIP service is connected"""
        connected = self.client is not None and self.client.is_connected()
        if not connected:
            logger.debug("🔍 NTRIP connection check: NOT connected")
        return connected
