"""
RTK Manager - connects NTRIP corrections with LC29H(DA) GPS module
"""

import logging
import time
from .ntrip_client import create_ntrip_client
from .lc29h_controller import LC29HController

logger = logging.getLogger(__name__)

class RTKManager:
    def __init__(self):
        self.ntrip_client = None
        self.gps_controller = None
        self.running = False
        self.rtk_status = "Disconnected"
        self.nmea_callback = None
        
    def initialize(self):
        """Initialize RTK system"""
        try:
            # Create NTRIP client
            self.ntrip_client = create_ntrip_client()
            
            # Create GPS controller
            self.gps_controller = LC29HController()
            
            # Set up callbacks
            self.ntrip_client.set_rtcm_callback(self._rtcm_received)
            self.gps_controller.set_nmea_callback(self._nmea_received)
            
            logger.info("RTK Manager initialized")
            return True
            
        except Exception as e:
            logger.error(f"RTK initialization error: {e}")
            return False
    
    def start(self):
        """Start RTK system"""
        if not self.ntrip_client or not self.gps_controller:
            logger.error("RTK system not initialized")
            return False
        
        # Connect to GPS first
        if not self.gps_controller.connect():
            logger.error("Failed to connect to LC29H(DA)")
            return False
        
        # Start GPS reading
        if not self.gps_controller.start_reading():
            logger.error("Failed to start GPS reading")
            return False
        
        # Connect to NTRIP
        if not self.ntrip_client.connect():
            logger.error("Failed to connect to NTRIP caster")
            self.gps_controller.disconnect()
            return False
        
        # Start RTCM receiving
        if not self.ntrip_client.start_receiving():
            logger.error("Failed to start RTCM receiving")
            self.stop()
            return False
        
        self.running = True
        self.rtk_status = "Connected"
        logger.info("RTK system started successfully")
        return True
    
    def stop(self):
        """Stop RTK system"""
        self.running = False
        self.rtk_status = "Disconnected"
        
        if self.ntrip_client:
            self.ntrip_client.disconnect()
        
        if self.gps_controller:
            self.gps_controller.disconnect()
        
        logger.info("RTK system stopped")
    
    def set_nmea_callback(self, callback):
        """Set callback for NMEA sentences"""
        self.nmea_callback = callback
    
    def get_status(self):
        """Get RTK system status"""
        return {
            "rtk_status": self.rtk_status,
            "running": self.running,
            "ntrip_connected": self.ntrip_client.connected if self.ntrip_client else False,
            "gps_connected": self.gps_controller.connected if self.gps_controller else False
        }
    
    def _rtcm_received(self, rtcm_data):
        """Callback for RTCM data from NTRIP"""
        if self.gps_controller and self.gps_controller.connected:
            self.gps_controller.send_rtcm(rtcm_data)
            logger.debug(f"Forwarded {len(rtcm_data)} bytes of RTCM to LC29H(DA)")
    
    def _nmea_received(self, sentence):
        """Callback for NMEA sentences from GPS"""
        # Forward to external callback if set
        if self.nmea_callback:
            self.nmea_callback(sentence)
        
        # Update RTK status based on NMEA quality
        if sentence.startswith('$GNGGA') or sentence.startswith('$GPGGA'):
            self._update_rtk_status_from_gga(sentence)
    
    def _update_rtk_status_from_gga(self, gga_sentence):
        """Update RTK status from GGA sentence"""
        try:
            fields = gga_sentence.split(',')
            if len(fields) > 6:
                quality = int(fields[6]) if fields[6] else 0
                
                quality_map = {
                    0: "No Fix",
                    1: "Single",
                    2: "DGPS", 
                    4: "RTK Fixed",
                    5: "RTK Float"
                }
                
                new_status = quality_map.get(quality, f"Unknown ({quality})")
                if new_status != self.rtk_status:
                    self.rtk_status = new_status
                    logger.info(f"RTK Status: {self.rtk_status}")
                    
        except (ValueError, IndexError) as e:
            logger.debug(f"Error parsing GGA quality: {e}")

# Test function
def test_rtk_system():
    """Test complete RTK system"""
    rtk = RTKManager()
    
    def nmea_received(sentence):
        print(f"NMEA: {sentence}")
    
    rtk.set_nmea_callback(nmea_received)
    
    if rtk.initialize():
        print("RTK Manager initialized")
        
        if rtk.start():
            print("RTK system started, monitoring for 60 seconds...")
            
            for i in range(60):
                status = rtk.get_status()
                print(f"Status: {status}")
                time.sleep(1)
            
            rtk.stop()
        else:
            print("Failed to start RTK system")
    else:
        print("Failed to initialize RTK Manager")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_rtk_system()
