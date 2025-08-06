"""
NTRIP Client for ASG-EUPOS RTK corrections
Based on NTRIP v1.0 protocol
"""

import socket
import base64
import threading
import time
import logging
from config.settings import rtk_config

logger = logging.getLogger(__name__)

class NTRIPClient:
    def __init__(self, caster, port, mountpoint, username, password):
        self.caster = caster
        self.port = port
        self.mountpoint = mountpoint
        self.username = username
        self.password = password
        self.socket = None
        self.connected = False
        self.running = False
        self.rtcm_callback = None
        
    def connect(self):
        """Connect to NTRIP caster"""
        try:
            # Create socket connection
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(10.0)
            self.socket.connect((self.caster, self.port))
            
            # Prepare NTRIP request
            auth_string = f"{self.username}:{self.password}"
            auth_b64 = base64.b64encode(auth_string.encode()).decode()
            
            request = (
                f"GET /{self.mountpoint} HTTP/1.0\r\n"
                f"User-Agent: RTKMower/1.0\r\n"
                f"Authorization: Basic {auth_b64}\r\n"
                f"\r\n"
            )
            
            # Send request
            self.socket.send(request.encode())
            
            # Read response
            response = self.socket.recv(1024).decode()
            logger.info(f"NTRIP Response: {response.strip()}")
            
            if "200 OK" in response:
                self.connected = True
                logger.info(f"Connected to {self.caster}:{self.port}/{self.mountpoint}")
                return True
            else:
                logger.error(f"NTRIP connection failed: {response}")
                return False
                
        except Exception as e:
            logger.error(f"NTRIP connection error: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from NTRIP caster"""
        self.running = False
        self.connected = False
        if self.socket:
            self.socket.close()
            self.socket = None
        logger.info("Disconnected from NTRIP caster")
    
    def set_rtcm_callback(self, callback):
        """Set callback function for RTCM data"""
        self.rtcm_callback = callback
    
    def start_receiving(self):
        """Start receiving RTCM data in background thread"""
        if not self.connected:
            logger.error("Not connected to NTRIP caster")
            return False
            
        self.running = True
        self.receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
        self.receive_thread.start()
        return True
    
    def _receive_loop(self):
        """Main loop for receiving RTCM data"""
        logger.info("Starting RTCM receive loop")
        
        while self.running and self.connected:
            try:
                # Receive RTCM data
                data = self.socket.recv(1024)
                if not data:
                    logger.warning("No data received, connection lost")
                    break
                
                # Call callback if set
                if self.rtcm_callback:
                    self.rtcm_callback(data)
                    
            except socket.timeout:
                continue
            except Exception as e:
                logger.error(f"Error receiving RTCM data: {e}")
                break
        
        logger.info("RTCM receive loop ended")
        self.connected = False

def create_ntrip_client():
    """Factory function to create NTRIP client from config"""
    return NTRIPClient(
        caster=rtk_config["caster"],
        port=rtk_config["port"],
        mountpoint=rtk_config["mountpoint"],
        username=rtk_config["username"],
        password=rtk_config["password"]
    )

# Test function
def test_connection():
    """Test NTRIP connection"""
    client = create_ntrip_client()
    
    def rtcm_received(data):
        print(f"Received {len(data)} bytes of RTCM data")
    
    client.set_rtcm_callback(rtcm_received)
    
    if client.connect():
        print("NTRIP connection successful!")
        client.start_receiving()
        
        # Test for 30 seconds
        time.sleep(30)
        client.disconnect()
    else:
        print("NTRIP connection failed!")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_connection()
