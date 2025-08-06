"""
RTK Manager - based on Waveshare LC29H examples
Simplified and adapted for RTK Mower project
"""

import socket
import base64
import serial
import threading
import time
import logging
import sys
from pynmeagps import NMEAReader

logger = logging.getLogger(__name__)

class RTKManager:
    def __init__(self):
        # Connection objects
        self.ntrip_socket = None
        self.gps_serial = None
        self.nmea_reader = None
        
        # State management
        self.running = False
        self.rtk_status = "Disconnected"
        self.position_callback = None
        self.current_position = None
        
        # Configuration
        from config.settings import rtk_config, uart_config
        self.ntrip_config = rtk_config
        self.uart_config = uart_config
        
        # NTRIP settings
        self.user_agent = "RTKMower/1.0"
        self.reconnect_attempts = 3
        self.reconnect_delay = 5
        
        # Threading
        self.rtcm_thread = None
        self.nmea_thread = None
        self.gga_thread = None
        self._demo_mode = False
        self._demo_thread = None
        
    def initialize(self):
        """Initialize RTK system"""
        try:
            logger.info("RTK Manager initializing...")
            return True
        except Exception as e:
            logger.error(f"RTK initialization error: {e}")
            return False
    
    def start(self):
        """Start RTK system - graceful degradation if NTRIP fails"""
        try:
            # 1. Always try to connect to GPS first
            self._connect_gps()
            
            # 2. Try to connect to NTRIP server (optional)
            ntrip_connected = self._connect_ntrip()
            
            if ntrip_connected:
                self.rtk_status = "RTK Connected"
                logger.info("Full RTK system started (GPS + NTRIP)")
            else:
                self.rtk_status = "GPS Only"
                logger.warning("Starting in GPS-only mode (NTRIP failed)")
            
            # 3. Start processing threads regardless
            self.running = True
            self._start_threads()
            
            logger.info(f"RTK system started successfully in mode: {self.rtk_status}")
            return True
                
        except Exception as e:
            logger.error(f"Failed to start RTK system: {e}")
            # Try demo mode if everything fails
            self._start_demo_mode()
            return True
    
    def _connect_gps(self):
        """Connect to GPS module via serial"""
        try:
            self.gps_serial = serial.Serial(
                port=self.uart_config["port"],
                baudrate=self.uart_config["baudrate"], 
                timeout=self.uart_config["timeout"]
            )
            
            # Initialize NMEA reader
            self.nmea_reader = NMEAReader(self.gps_serial)
            
            logger.info(f"Connected to GPS on {self.uart_config['port']} at {self.uart_config['baudrate']} baud")
            
        except Exception as e:
            logger.warning(f"Failed to connect to GPS: {e}")
            logger.info("Starting in DEMO mode - no physical GPS hardware")
            
            # Set demo mode
            self.gps_serial = None
            self.nmea_reader = None
            self._demo_mode = True
            
            # Start demo position simulation
            self._start_demo_simulation()
    
    def _start_demo_simulation(self):
        """Start demo position simulation for testing without hardware"""
        logger.info("Starting GPS demo simulation")
        
        # Demo coordinates (Warsaw, Poland area)
        self._demo_lat = 52.2297
        self._demo_lon = 21.0122
        self._demo_satellites = 8
        self._demo_hdop = 1.2
        self._demo_rtk_status = "RTK Fixed"
        
        # Start demo thread
        self._demo_thread = threading.Thread(target=self._demo_position_loop, daemon=True)
        self._demo_thread.start()
    
    def _demo_position_loop(self):
        """Demo position simulation loop"""
        while self.running and self._demo_mode:
            try:
                # Simulate small GPS movement
                import random
                lat_offset = random.uniform(-0.0001, 0.0001)  # ~10m variation
                lon_offset = random.uniform(-0.0001, 0.0001)
                
                position_data = {
                    "lat": self._demo_lat + lat_offset,
                    "lon": self._demo_lon + lon_offset,
                    "altitude": 100.0 + random.uniform(-2, 2),
                    "satellites": self._demo_satellites,
                    "hdop": self._demo_hdop + random.uniform(-0.2, 0.2),
                    "rtk_status": self._demo_rtk_status,
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")
                }
                
                # Update current position
                self.current_position = position_data
                
                # Call position callback
                if self.position_callback:
                    self.position_callback(position_data)
                    
                # Wait 1 second
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"Demo simulation error: {e}")
                break
    
    def _start_demo_mode(self):
        """Start demo mode when both GPS and NTRIP fail"""
        logger.info("Starting complete DEMO mode - no hardware available")
        
        self._demo_mode = True
        self.rtk_status = "Demo Mode"
        self.running = True
        
        # Start demo simulation
        self._start_demo_simulation()
        logger.info("Demo mode started successfully")
    
    def _connect_ntrip(self):
        """Connect to NTRIP caster"""
        if self._demo_mode:
            logger.info("DEMO MODE: Skipping NTRIP connection")
            return True
            
        try:
            # Create socket connection
            self.ntrip_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.ntrip_socket.settimeout(10)
            
            logger.info(f"Connecting to NTRIP caster {self.ntrip_config['caster']}:{self.ntrip_config['port']}")
            self.ntrip_socket.connect((self.ntrip_config["caster"], self.ntrip_config["port"]))
            
            # Prepare authentication
            auth_string = f"{self.ntrip_config['username']}:{self.ntrip_config['password']}"
            auth_b64 = base64.b64encode(auth_string.encode()).decode()
            
            # Send NTRIP request (based on Waveshare format)
            request = self._build_ntrip_request(auth_b64)
            self.ntrip_socket.send(request.encode())
            
            # Check response
            response = self.ntrip_socket.recv(1024).decode()
            
            if "200 OK" in response:
                logger.info("NTRIP connection successful")
                return True
            else:
                logger.error(f"NTRIP connection failed: {response}")
                return False
                
        except Exception as e:
            logger.error(f"NTRIP connection error: {e}")
            return False
    
    def _build_ntrip_request(self, auth_b64):
        """Build NTRIP request following Waveshare format"""
        mountpoint = self.ntrip_config["mountpoint"]
        if not mountpoint.startswith('/'):
            mountpoint = f"/{mountpoint}"
            
        request = (
            f"GET {mountpoint} HTTP/1.1\r\n"
            f"User-Agent: {self.user_agent}\r\n"
            f"Authorization: Basic {auth_b64}\r\n"
            f"Host: {self.ntrip_config['caster']}:{self.ntrip_config['port']}\r\n"
            f"\r\n"
        )
        
        logger.debug(f"NTRIP request:\n{request}")
        return request
    
    def _start_threads(self):
        """Start processing threads based on available connections"""
        if self._demo_mode:
            logger.info("DEMO MODE: Threads already started in simulation")
            return
        
        # Always start NMEA reading if GPS is connected
        if self.gps_serial and self.nmea_reader:
            self.nmea_thread = threading.Thread(target=self._nmea_loop, daemon=True)
            self.nmea_thread.start()
            logger.info("NMEA processing thread started")
        
        # Start RTCM and GGA threads only if NTRIP is connected
        if self.ntrip_socket:
            # RTCM receiving and forwarding thread
            self.rtcm_thread = threading.Thread(target=self._rtcm_loop, daemon=True)
            self.rtcm_thread.start()
            
            # GGA uploading thread (every 1 second)
            self.gga_thread = threading.Thread(target=self._gga_upload_loop, daemon=True)
            self.gga_thread.start()
            
            logger.info("RTCM and GGA threads started (NTRIP mode)")
        else:
            logger.info("GPS-only mode: Only NMEA processing active")
        
        logger.info("All available threads started")
    
    def _rtcm_loop(self):
        """Receive RTCM corrections and forward to GPS - based on Waveshare"""
        logger.info("RTCM forwarding loop started")
        
        while self.running and self.ntrip_socket:
            try:
                # Receive RTCM data from NTRIP server
                rtcm_data = self.ntrip_socket.recv(1024)
                
                if rtcm_data and self.gps_serial:
                    # Forward directly to GPS module (like Waveshare C code)
                    self.gps_serial.write(rtcm_data)
                    logger.debug(f"Forwarded {len(rtcm_data)} bytes of RTCM to GPS")
                    
            except socket.timeout:
                continue
            except Exception as e:
                logger.error(f"RTCM loop error: {e}")
                break
                
        logger.info("RTCM forwarding loop ended")
    
    def _nmea_loop(self):
        """Read and process NMEA sentences - based on Waveshare pynmeagps approach"""
        logger.info("NMEA processing loop started")
        
        while self.running and self.nmea_reader:
            try:
                # Use pynmeagps reader like in Waveshare example
                if self.gps_serial.in_waiting > 0:
                    raw_data, parsed_data = self.nmea_reader.read()
                    
                    if raw_data and parsed_data:
                        self._process_nmea_message(raw_data, parsed_data)
                        
            except Exception as e:
                logger.error(f"NMEA loop error: {e}")
                break
                
        logger.info("NMEA processing loop ended")
    
    def _gga_upload_loop(self):
        """Periodically send GGA to NTRIP server - based on Waveshare timing"""
        logger.info("GGA upload loop started")
        
        while self.running and self.ntrip_socket:
            try:
                # Wait 1 second between uploads (like Waveshare 10 * 100ms)
                time.sleep(1)
                
                if self.current_position and self.ntrip_socket:
                    gga_sentence = self._build_gga_sentence()
                    if gga_sentence:
                        # Upload GGA to NTRIP server
                        self._upload_gga(gga_sentence)
                        
            except Exception as e:
                logger.error(f"GGA upload error: {e}")
                # Continue loop even if upload fails
                
        logger.info("GGA upload loop ended")
    
    def _process_nmea_message(self, raw_data, parsed_data):
        """Process NMEA message and extract position data"""
        try:
            # Look for GGA sentences (like Waveshare searches for GNGGA)
            if hasattr(parsed_data, 'msgID') and parsed_data.msgID in ['GGA']:
                self._process_gga_message(parsed_data)
                
        except Exception as e:
            logger.debug(f"Error processing NMEA: {e}")
    
    def _process_gga_message(self, gga_data):
        """Process GGA message and update position"""
        try:
            if hasattr(gga_data, 'lat') and hasattr(gga_data, 'lon'):
                # Extract position data
                position_data = {
                    "lat": float(gga_data.lat) if gga_data.lat else 0.0,
                    "lon": float(gga_data.lon) if gga_data.lon else 0.0,
                    "altitude": float(gga_data.alt) if hasattr(gga_data, 'alt') and gga_data.alt else 0.0,
                    "satellites": int(gga_data.numSV) if hasattr(gga_data, 'numSV') and gga_data.numSV else 0,
                    "hdop": float(gga_data.HDOP) if hasattr(gga_data, 'HDOP') and gga_data.HDOP else 0.0,
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")
                }
                
                # Determine RTK status from quality indicator
                if hasattr(gga_data, 'quality'):
                    quality_map = {
                        0: "No Fix",
                        1: "Single",
                        2: "DGPS", 
                        4: "RTK Fixed",
                        5: "RTK Float"
                    }
                    position_data["rtk_status"] = quality_map.get(int(gga_data.quality), f"Unknown ({gga_data.quality})")
                else:
                    position_data["rtk_status"] = "Unknown"
                
                # Update status if changed
                if position_data["rtk_status"] != self.rtk_status:
                    self.rtk_status = position_data["rtk_status"]
                    logger.info(f"RTK Status: {self.rtk_status}")
                
                # Store current position
                self.current_position = position_data
                
                # Call position callback
                if self.position_callback:
                    self.position_callback(position_data)
                    
        except Exception as e:
            logger.debug(f"Error processing GGA: {e}")
    
    def _build_gga_sentence(self):
        """Build GGA sentence from current position for NTRIP upload"""
        if not self.current_position:
            return None
            
        try:
            # This is a simplified GGA builder - in real implementation
            # you'd want to get the actual GGA from the GPS stream
            pos = self.current_position
            
            # Convert decimal degrees to NMEA format (DDMM.MMMMM)
            lat = abs(pos["lat"])
            lat_deg = int(lat)
            lat_min = (lat - lat_deg) * 60
            lat_ns = "N" if pos["lat"] >= 0 else "S"
            
            lon = abs(pos["lon"])
            lon_deg = int(lon)
            lon_min = (lon - lon_deg) * 60
            lon_ew = "E" if pos["lon"] >= 0 else "W"
            
            # Build simplified GGA (you might want to store the actual raw GGA instead)
            gga = f"$GNGGA,{time.strftime('%H%M%S')},{lat_deg:02d}{lat_min:07.4f},{lat_ns},{lon_deg:03d}{lon_min:07.4f},{lon_ew},1,{pos['satellites']},{pos['hdop']:.1f},{pos['altitude']:.1f},M,0.0,M,,*00"
            
            return gga
            
        except Exception as e:
            logger.error(f"Error building GGA: {e}")
            return None
    
    def _upload_gga(self, gga_sentence):
        """Upload GGA sentence to NTRIP server"""
        try:
            if self.ntrip_socket:
                # Send GGA like in Waveshare qxwz_sdk_upload_gga
                gga_data = (gga_sentence + "\r\n").encode()
                self.ntrip_socket.send(gga_data)
                logger.debug(f"Uploaded GGA: {gga_sentence}")
                
        except Exception as e:
            logger.error(f"Error uploading GGA: {e}")
    
    def stop(self):
        """Stop RTK system"""
        logger.info("Stopping RTK system...")
        
        self.running = False
        self.rtk_status = "Disconnected"
        
        # Wait for threads to finish
        if self.rtcm_thread and self.rtcm_thread.is_alive():
            self.rtcm_thread.join(timeout=2)
        if self.nmea_thread and self.nmea_thread.is_alive():
            self.nmea_thread.join(timeout=2)
        if self.gga_thread and self.gga_thread.is_alive():
            self.gga_thread.join(timeout=2)
        
        self._cleanup_connections()
        logger.info("RTK system stopped")
    
    def _cleanup_connections(self):
        """Clean up all connections"""
        if self.ntrip_socket:
            try:
                self.ntrip_socket.close()
            except:
                pass
            self.ntrip_socket = None
            
        if self.gps_serial:
            try:
                self.gps_serial.close()
            except:
                pass
            self.gps_serial = None
            self.nmea_reader = None
    
    def set_position_callback(self, callback):
        """Set callback for position updates"""
        self.position_callback = callback
    
    def get_status(self):
        """Get RTK system status"""
        return {
            "rtk_status": self.rtk_status,
            "running": self.running,
            "ntrip_connected": self.ntrip_socket is not None,
            "gps_connected": self.gps_serial is not None,
            "current_position": self.current_position
        }
    
    def get_current_position(self):
        """Get current GPS position"""
        if not self.current_position:
            return None
            
        return {
            "lat": self.current_position.get("lat"),
            "lon": self.current_position.get("lon"),
            "altitude": self.current_position.get("altitude", 0),
            "rtk_status": self.current_position.get("rtk_status", "No Fix"),
            "satellites": self.current_position.get("satellites", 0),
            "hdop": self.current_position.get("hdop", 0.0),
            "timestamp": self.current_position.get("timestamp")
        }
    
    def get_track_data(self):
        """Get track data - placeholder for position tracker integration"""
        return {"session_id": "", "points": []}

# Test function for debugging
def test_rtk_system():
    """Test RTK system with Waveshare-like approach"""
    logging.basicConfig(level=logging.INFO)
    
    rtk = RTKManager()
    
    def position_received(pos_data):
        print(f"Position: {pos_data['lat']:.6f}, {pos_data['lon']:.6f} - {pos_data['rtk_status']}")
    
    rtk.set_position_callback(position_received)
    
    if rtk.initialize():
        print("RTK Manager initialized")
        
        if rtk.start():
            print("RTK system started, monitoring for 60 seconds...")
            
            try:
                for i in range(60):
                    status = rtk.get_status()
                    print(f"Status: RTK={status['rtk_status']}, Running={status['running']}")
                    time.sleep(1)
                    
            except KeyboardInterrupt:
                print("\nStopping RTK system...")
                
            finally:
                rtk.stop()
        else:
            print("Failed to start RTK system")
    else:
        print("Failed to initialize RTK Manager")

if __name__ == "__main__":
    test_rtk_system()
