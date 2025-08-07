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
        
        # NTRIP settings - compatible with ASG-EUPOS
        self.user_agent = "NTRIP RTKMower/1.0"
        self.reconnect_attempts = 3
        self.reconnect_delay = 5
        
        # Threading
        self.rtcm_thread = None
        self.nmea_thread = None
        self.gga_thread = None
        self._demo_mode = False
        self._demo_thread = None
        
        # Reconnection synchronization
        self._reconnect_lock = threading.Lock()
        self._reconnecting = False
        
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
        if self.running:
            logger.warning("RTK system is already running")
            return True
            
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
                # Clean up failed NTRIP socket
                if self.ntrip_socket:
                    try:
                        self.ntrip_socket.close()
                    except:
                        pass
                    self.ntrip_socket = None
            
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
        """Connect to GPS module via serial with auto baudrate detection"""
        # Common GPS baudrates to try (based on Waveshare documentation)
        baudrates_to_try = [115200, 38400, 9600]  # LC29H default is 115200
        
        for baudrate in baudrates_to_try:
            try:
                logger.info(f"Trying GPS connection at {baudrate} baud...")
                
                # Try to open serial connection
                test_serial = serial.Serial(
                    port=self.uart_config["port"],
                    baudrate=baudrate,
                    timeout=2.0  # Shorter timeout for testing
                )
                
                # Test if we get valid NMEA data
                if self._test_gps_communication(test_serial):
                    # Connection successful
                    self.gps_serial = test_serial
                    self.uart_config["baudrate"] = baudrate  # Update config
                    
                    # Initialize NMEA reader
                    self.nmea_reader = NMEAReader(self.gps_serial)
                    
                    logger.info(f"GPS communication successful at {baudrate} baud")
                    logger.info(f"Connected to GPS on {self.uart_config['port']} at {baudrate} baud")
                    return
                else:
                    # Close failed connection
                    test_serial.close()
                    
            except Exception as e:
                logger.debug(f"Failed at {baudrate} baud: {e}")
                continue
        
        # No working baudrate found
        logger.warning("Failed to connect to GPS: No working baudrate found")
        logger.info("Starting in DEMO mode - no physical GPS hardware")
        
        # Set demo mode
        self.gps_serial = None
        self.nmea_reader = None
        self._demo_mode = True
        
        # Start demo position simulation
        self._start_demo_simulation()
    
    def _test_gps_communication(self, serial_connection):
        """Test if GPS communication works at given baudrate"""
        try:
            # Clear input buffer
            serial_connection.reset_input_buffer()
            
            # Wait up to 3 seconds for NMEA data
            start_time = time.time()
            while time.time() - start_time < 3.0:
                if serial_connection.in_waiting > 0:
                    try:
                        line = serial_connection.readline().decode('ascii', errors='ignore').strip()
                        # Look for valid NMEA sentences
                        if line.startswith('$') and ('GGA' in line or 'RMC' in line or 'GSV' in line):
                            logger.debug(f"Valid NMEA received: {line[:50]}...")
                            return True
                    except:
                        continue
                time.sleep(0.1)
            
            return False
            
        except Exception as e:
            logger.debug(f"GPS communication test failed: {e}")
            return False
    
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
            # Create socket connection with keep-alive
            self.ntrip_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.ntrip_socket.settimeout(10)  # Connection timeout
            
            # Enable keep-alive for ASG-EUPOS compatibility
            self.ntrip_socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            
            logger.info(f"Connecting to NTRIP caster {self.ntrip_config['caster']}:{self.ntrip_config['port']}")
            self.ntrip_socket.connect((self.ntrip_config["caster"], self.ntrip_config["port"]))
            
            # Prepare authentication
            auth_string = f"{self.ntrip_config['username']}:{self.ntrip_config['password']}"
            auth_b64 = base64.b64encode(auth_string.encode()).decode()
            
            # Send NTRIP request (based on Waveshare format)
            request = self._build_ntrip_request(auth_b64)
            logger.debug(f"Sending NTRIP request...")
            self.ntrip_socket.send(request.encode())
            
            # Check response
            logger.debug("Waiting for NTRIP response...")
            response = self.ntrip_socket.recv(1024).decode()
            logger.debug(f"NTRIP response: {response}")
            
            if "200 OK" in response:
                logger.info("NTRIP connection successful")
                # Set socket timeout for data reception
                self.ntrip_socket.settimeout(3.0)
                return True
            elif "401" in response:
                logger.error(f"NTRIP authentication failed: {response}")
                self._cleanup_ntrip_socket()
                return False
            elif "404" in response:
                logger.error(f"NTRIP mountpoint not found: {response}")
                self._cleanup_ntrip_socket()
                return False
            else:
                logger.error(f"NTRIP connection failed: {response}")
                self._cleanup_ntrip_socket()
                return False
                
        except Exception as e:
            logger.error(f"NTRIP connection error: {e}")
            self._cleanup_ntrip_socket()
            return False
    
    def _cleanup_ntrip_socket(self):
        """Clean up NTRIP socket connection"""
        if self.ntrip_socket:
            try:
                self.ntrip_socket.close()
            except:
                pass
            self.ntrip_socket = None
    
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
        
        threads_started = []
        
        # Always start NMEA reading if GPS is connected
        if self.gps_serial and self.nmea_reader:
            self.nmea_thread = threading.Thread(target=self._nmea_loop, daemon=True)
            self.nmea_thread.start()
            threads_started.append("NMEA processing")
        
        # Start RTCM and GGA threads ONLY if NTRIP is actually connected
        if self.ntrip_socket:
            # RTCM receiving and forwarding thread
            self.rtcm_thread = threading.Thread(target=self._rtcm_loop, daemon=True)
            self.rtcm_thread.start()
            threads_started.append("RTCM forwarding")
            
            # GGA uploading thread (every 1 second)  
            self.gga_thread = threading.Thread(target=self._gga_upload_loop, daemon=True)
            self.gga_thread.start()
            threads_started.append("GGA uploading")
            
            logger.info(f"NTRIP mode: Started threads: {', '.join(threads_started)}")
        else:
            logger.info(f"GPS-only mode: Started threads: {', '.join(threads_started)}")
        
        if threads_started:
            logger.info(f"All available threads started: {', '.join(threads_started)}")
        else:
            logger.warning("No processing threads started - no connections available")
    
    def _rtcm_loop(self):
        """Receive RTCM corrections and forward to GPS - based on Waveshare"""
        logger.info("RTCM forwarding loop started")
        
        reconnect_attempts = 0
        max_reconnect_attempts = 3
        
        while self.running and reconnect_attempts < max_reconnect_attempts:
            try:
                if not self.ntrip_socket:
                    # Wait a moment before attempting reconnection to avoid rapid retries
                    time.sleep(1)
                    logger.info("NTRIP socket lost, attempting reconnection...")
                    if self._reconnect_ntrip():
                        reconnect_attempts = 0  # Reset on successful reconnect
                    else:
                        reconnect_attempts += 1
                        logger.warning(f"NTRIP reconnection failed ({reconnect_attempts}/{max_reconnect_attempts})")
                        time.sleep(5)  # Wait before retry
                        continue
                
                # Receive RTCM data from NTRIP server
                rtcm_data = self.ntrip_socket.recv(1024)
                
                if rtcm_data and self.gps_serial:
                    # Forward directly to GPS module (like Waveshare C code)
                    self.gps_serial.write(rtcm_data)
                    
                    # Track RTCM data for diagnostics
                    if not hasattr(self, '_rtcm_bytes_received'):
                        self._rtcm_bytes_received = 0
                        self._last_rtcm_log_time = time.time()
                    
                    self._rtcm_bytes_received += len(rtcm_data)
                    
                    # Log RTCM statistics every 60 seconds
                    current_time = time.time()
                    if (current_time - self._last_rtcm_log_time) > 60:
                        logger.info(f"RTCM data: {self._rtcm_bytes_received} bytes received in last 60s")
                        self._rtcm_bytes_received = 0
                        self._last_rtcm_log_time = current_time
                    
                    logger.debug(f"Forwarded {len(rtcm_data)} bytes of RTCM to GPS")
                    
            except socket.timeout:
                continue
            except Exception as e:
                logger.error(f"RTCM loop error: {e}")
                # Mark socket as broken so reconnection can be attempted
                self._cleanup_ntrip_socket()
                # Don't attempt immediate reconnect - let main logic handle it
                time.sleep(1)
                
        logger.info("RTCM forwarding loop ended")
    
    def _reconnect_ntrip(self):
        """Attempt to reconnect to NTRIP server with synchronization"""
        with self._reconnect_lock:
            if self._reconnecting:
                logger.debug("Reconnection already in progress, waiting...")
                return self.ntrip_socket is not None
                
            self._reconnecting = True
            
            try:
                logger.info("Attempting NTRIP reconnection...")
                self._cleanup_ntrip_socket()
                
                if self._connect_ntrip():
                    logger.info("NTRIP reconnection successful")
                    return True
                else:
                    logger.warning("NTRIP reconnection failed")
                    return False
                    
            except Exception as e:
                logger.error(f"NTRIP reconnection error: {e}")
                return False
            finally:
                self._reconnecting = False
    
    def _nmea_loop(self):
        """Read and process NMEA sentences - based on Waveshare pynmeagps approach"""
        logger.info("NMEA processing loop started")
        
        consecutive_errors = 0
        max_consecutive_errors = 10  # Zwiększone z 5 bo checksum errors nie są krytyczne
        nmea_errors = 0
        
        while self.running and self.nmea_reader and consecutive_errors < max_consecutive_errors:
            try:
                # Use pynmeagps reader like in Waveshare example
                if self.gps_serial and self.gps_serial.in_waiting > 0:
                    try:
                        raw_data, parsed_data = self.nmea_reader.read()
                        
                        if raw_data and parsed_data:
                            self._process_nmea_message(raw_data, parsed_data)
                            consecutive_errors = 0  # Reset error counter on success
                        else:
                            # No data available, wait a bit
                            time.sleep(0.1)
                            
                    except Exception as nmea_error:
                        # Checksum errors from pynmeagps are not fatal
                        if "checksum" in str(nmea_error) or "invalid" in str(nmea_error):
                            nmea_errors += 1
                            if nmea_errors % 10 == 0:  # Log every 10th error to avoid spam
                                logger.debug(f"NMEA checksum errors: {nmea_errors} (non-fatal)")
                            time.sleep(0.1)
                        else:
                            # Other NMEA errors might be more serious
                            consecutive_errors += 1
                            logger.warning(f"NMEA parsing error: {nmea_error}")
                            time.sleep(0.5)
                else:
                    # No data waiting, short sleep
                    time.sleep(0.1)
                        
            except Exception as e:
                consecutive_errors += 1
                logger.error(f"NMEA loop error ({consecutive_errors}/{max_consecutive_errors}): {e}")
                
                if consecutive_errors >= max_consecutive_errors:
                    logger.error("Too many consecutive NMEA errors, stopping loop")
                    break
                    
                # Wait before retry
                time.sleep(1)
                
        logger.info(f"NMEA processing loop ended (total checksum errors: {nmea_errors})")
    
    def _gga_upload_loop(self):
        """Periodically send GGA to NTRIP server - based on Waveshare timing"""
        if not self.ntrip_socket:
            logger.warning("GGA upload loop: No NTRIP connection, exiting")
            return
            
        logger.info("GGA upload loop started")
        
        failed_uploads = 0
        max_failed_uploads = 3
        reconnect_attempts = 0
        max_reconnect_attempts = 3
        
        # Send initial GGA to establish session
        self._send_initial_gga()
        
        while self.running and reconnect_attempts < max_reconnect_attempts:
            try:
                # Check if NTRIP connection exists
                if not self.ntrip_socket:
                    # Wait a moment before attempting reconnection to avoid rapid retries
                    time.sleep(1)
                    logger.info("NTRIP socket lost in GGA loop, attempting reconnection...")
                    if self._reconnect_ntrip():
                        reconnect_attempts = 0  # Reset on successful reconnect
                        failed_uploads = 0
                    else:
                        reconnect_attempts += 1
                        logger.warning(f"NTRIP reconnection failed in GGA loop ({reconnect_attempts}/{max_reconnect_attempts})")
                        time.sleep(5)  # Wait before retry
                        continue
                
                # Wait between uploads - adaptive timing based on signal quality
                gga_interval = self._get_adaptive_gga_interval()
                time.sleep(gga_interval)
                
                # Send GGA tylko jeśli mamy realną pozycję (nie wysyłaj dummy GGA)
                if self.current_position:
                    gga_sentence = self._build_gga_sentence()
                    if gga_sentence:
                        # Upload GGA to NTRIP server
                        upload_success = self._upload_gga(gga_sentence)
                        if upload_success:
                            failed_uploads = 0  # Reset counter on success
                        else:
                            failed_uploads += 1
                            if failed_uploads >= max_failed_uploads:
                                logger.warning("Too many GGA upload failures, marking connection as lost")
                                self._cleanup_ntrip_socket()
                                failed_uploads = 0
                else:
                    # Bez pozycji, nie wysyłaj nic - pozwól na natural keep-alive
                    logger.debug("No GPS position available, skipping GGA upload")
                        
            except Exception as e:
                failed_uploads += 1
                logger.error(f"GGA upload loop error: {e}")
                time.sleep(1)
                
        logger.info("GGA upload loop ended")
    
    def _get_adaptive_gga_interval(self):
        """Get adaptive GGA upload interval based on signal quality and RTK status"""
        if not self.current_position:
            return 15  # Default interval when no position
        
        hdop = self.current_position.get("hdop", 10.0)
        rtk_status = self.current_position.get("rtk_status", "Unknown")
        satellites = self.current_position.get("satellites", 0)
        
        # Adaptive timing based on signal quality and RTK status
        if rtk_status == "RTK Fixed":
            return 20  # Longer interval for stable RTK Fixed
        elif rtk_status == "RTK Float":
            return 10  # Medium interval for RTK Float
        elif hdop <= 2.0 and satellites >= 12:
            return 8   # Shorter interval for excellent signal quality
        elif hdop <= 3.0 and satellites >= 8:
            return 12  # Medium interval for good signal quality  
        else:
            return 15  # Default interval for poor signal quality
    
    def _send_initial_gga(self):
        """Send initial GGA to establish NTRIP session"""
        try:
            # Wait a bit for GPS to get position
            time.sleep(1)
            
            # Use current position if available
            if self.current_position:
                gga_sentence = self._build_gga_sentence()
                hdop = self.current_position.get("hdop", 0.0)
                satellites = self.current_position.get("satellites", 0)
                logger.info(f"Using current GPS position for initial GGA (HDOP: {hdop:.1f}, Sats: {satellites})")
            else:
                # Use approximate Poland center for initial GGA
                gga_sentence = "$GNGGA,120000,5213.0000,N,02100.0000,E,1,08,1.0,100.0,M,0.0,M,,*00"
                logger.info("Using default position for initial GGA")
            
            if gga_sentence and self.ntrip_socket:
                self._upload_gga(gga_sentence)
                logger.info("Initial GGA sent to establish NTRIP session")
                
        except Exception as e:
            logger.warning(f"Failed to send initial GGA: {e}")
    
    def _build_dummy_gga(self):
        """Build dummy GGA for keep-alive when no position available"""
        try:
            # Use approximate location for keep-alive
            # Poland center coordinates
            current_time = time.strftime('%H%M%S')
            dummy_gga = f"$GNGGA,{current_time},5213.0000,N,02100.0000,E,1,08,1.0,100.0,M,0.0,M,,*00"
            return dummy_gga
            
        except Exception as e:
            logger.error(f"Error building dummy GGA: {e}")
            return None
    
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
                
                # Log signal quality warnings
                self._log_signal_quality_warnings(position_data)
                
                # Store current position
                self.current_position = position_data
                
                # Call position callback
                if self.position_callback:
                    self.position_callback(position_data)
                    
        except Exception as e:
            logger.debug(f"Error processing GGA: {e}")
    
    def _log_signal_quality_warnings(self, position_data):
        """Log warnings about poor signal quality that affects RTK performance"""
        hdop = position_data.get("hdop", 0.0)
        satellites = position_data.get("satellites", 0)
        rtk_status = position_data.get("rtk_status", "Unknown")
        
        # Track time for periodic warnings (every 30 seconds)
        if not hasattr(self, '_last_warning_time'):
            self._last_warning_time = 0
        
        current_time = time.time()
        should_warn = (current_time - self._last_warning_time) > 30
        
        if should_warn:
            # High HDOP warning
            if hdop > 5.0:
                logger.warning(f"Poor HDOP: {hdop:.1f} (>5.0) - RTK Fixed unlikely. Check antenna position!")
                self._last_warning_time = current_time
            elif hdop > 2.0 and rtk_status == "Single":
                logger.info(f"Marginal HDOP: {hdop:.1f} (>2.0) - waiting for better satellite geometry for RTK")
                self._last_warning_time = current_time
            
            # Low satellite count warning  
            if satellites < 8:
                logger.warning(f"Low satellite count: {satellites} (<8) - may affect RTK performance")
                self._last_warning_time = current_time
            
            # RTK status analysis
            if rtk_status == "Single" and hdop <= 2.0 and satellites >= 8:
                logger.info(f"Good signal quality (HDOP:{hdop:.1f}, Sats:{satellites}) but no RTK - check NTRIP corrections")
                self._last_warning_time = current_time
    
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
                return True
            else:
                logger.debug("No NTRIP socket available for GGA upload")
                return False
                
        except Exception as e:
            logger.error(f"Error uploading GGA: {e}")
            # If socket error, mark it as disconnected
            if "Broken pipe" in str(e) or "Connection" in str(e) or "timed out" in str(e):
                logger.warning("NTRIP connection lost during GGA upload - marking for reconnection")
                self._cleanup_ntrip_socket()
                # Don't immediately return False - let connection check in loop handle it
                return False
            return False
    
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
        logger.debug("Cleaning up connections...")
        
        # Clean up NTRIP connection
        self._cleanup_ntrip_socket()
            
        # Clean up GPS serial connection
        if self.gps_serial:
            try:
                self.gps_serial.close()
                logger.debug("GPS serial connection closed")
            except:
                pass
            self.gps_serial = None
            self.nmea_reader = None
    
    def set_position_callback(self, callback):
        """Set callback for position updates"""
        self.position_callback = callback
    
    def get_status(self):
        """Get RTK system status with enhanced diagnostics"""
        status = {
            "rtk_status": self.rtk_status,
            "running": self.running,
            "ntrip_connected": self.ntrip_socket is not None,
            "gps_connected": self.gps_serial is not None,
            "current_position": self.current_position
        }
        
        # Add signal quality assessment
        if self.current_position:
            hdop = self.current_position.get("hdop", 0.0)
            satellites = self.current_position.get("satellites", 0)
            
            # Signal quality assessment
            if hdop <= 2.0 and satellites >= 12:
                status["signal_quality"] = "Excellent"
            elif hdop <= 3.0 and satellites >= 8:
                status["signal_quality"] = "Good"
            elif hdop <= 5.0 and satellites >= 6:
                status["signal_quality"] = "Fair"
            else:
                status["signal_quality"] = "Poor"
                
            # RTK readiness assessment
            if hdop <= 2.0 and satellites >= 8:
                status["rtk_ready"] = True
                status["rtk_ready_reason"] = "Signal quality good for RTK"
            else:
                status["rtk_ready"] = False
                if hdop > 2.0:
                    status["rtk_ready_reason"] = f"HDOP too high: {hdop:.1f} (need <2.0)"
                elif satellites < 8:
                    status["rtk_ready_reason"] = f"Too few satellites: {satellites} (need ≥8)"
        else:
            status["signal_quality"] = "Unknown"
            status["rtk_ready"] = False
            status["rtk_ready_reason"] = "No GPS position available"
            
        return status
    
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
