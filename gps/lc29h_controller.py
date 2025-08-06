"""
LC29H(DA) GPS/RTK HAT Communication Module
Handles UART communication and RTCM injection
"""

import serial
import threading
import time
import logging
from config.settings import uart_config

logger = logging.getLogger(__name__)

class LC29HController:
    def __init__(self, port=None, baudrate=None):
        self.port = port or uart_config["port"]
        self.baudrate = baudrate or uart_config["baudrate"]
        self.timeout = uart_config["timeout"]
        
        self.serial_conn = None
        self.connected = False
        self.running = False
        self.nmea_callback = None
        
    def connect(self):
        """Connect to LC29H(DA) via UART"""
        try:
            self.serial_conn = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE
            )
            
            if self.serial_conn.is_open:
                self.connected = True
                logger.info(f"Connected to LC29H(DA) on {self.port} at {self.baudrate} baud")
                return True
            else:
                logger.error("Failed to open serial connection")
                return False
                
        except Exception as e:
            logger.error(f"Serial connection error: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from LC29H(DA)"""
        self.running = False
        self.connected = False
        
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
            self.serial_conn = None
        
        logger.info("Disconnected from LC29H(DA)")
    
    def set_nmea_callback(self, callback):
        """Set callback function for NMEA data"""
        self.nmea_callback = callback
    
    def start_reading(self):
        """Start reading NMEA data in background thread"""
        if not self.connected:
            logger.error("Not connected to LC29H(DA)")
            return False
            
        self.running = True
        self.read_thread = threading.Thread(target=self._read_loop, daemon=True)
        self.read_thread.start()
        return True
    
    def _read_loop(self):
        """Main loop for reading NMEA sentences"""
        logger.info("Starting NMEA read loop")
        
        while self.running and self.connected:
            try:
                if self.serial_conn.in_waiting > 0:
                    # Read line from serial
                    line = self.serial_conn.readline().decode('ascii', errors='ignore').strip()
                    
                    if line.startswith('$') and self.nmea_callback:
                        self.nmea_callback(line)
                        
            except Exception as e:
                logger.error(f"Error reading NMEA data: {e}")
                time.sleep(0.1)
        
        logger.info("NMEA read loop ended")
    
    def send_rtcm(self, rtcm_data):
        """Send RTCM correction data to LC29H(DA)"""
        if not self.connected:
            logger.warning("Cannot send RTCM: not connected")
            return False
            
        try:
            bytes_written = self.serial_conn.write(rtcm_data)
            logger.debug(f"Sent {bytes_written} bytes of RTCM data to LC29H(DA)")
            return True
        except Exception as e:
            logger.error(f"Error sending RTCM data: {e}")
            return False
    
    def send_command(self, command):
        """Send command to LC29H(DA)"""
        if not self.connected:
            logger.warning("Cannot send command: not connected")
            return False
            
        try:
            cmd_line = f"{command}\r\n"
            self.serial_conn.write(cmd_line.encode())
            logger.info(f"Sent command: {command}")
            return True
        except Exception as e:
            logger.error(f"Error sending command: {e}")
            return False

# Test function
def test_connection():
    """Test LC29H(DA) connection"""
    gps = LC29HController()
    
    def nmea_received(sentence):
        print(f"NMEA: {sentence}")
    
    gps.set_nmea_callback(nmea_received)
    
    if gps.connect():
        print("LC29H(DA) connection successful!")
        gps.start_reading()
        
        # Test for 30 seconds
        time.sleep(30)
        gps.disconnect()
    else:
        print("LC29H(DA) connection failed!")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_connection()
