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
        if self.client:
            return self.client.send_gga(gga_data)
        return False
    
    def get_rtcm_data(self) -> List[bytes]:
        return []
    
    def disconnect(self):
        if self.client:
            self.client.disconnect()
            self.client = None
