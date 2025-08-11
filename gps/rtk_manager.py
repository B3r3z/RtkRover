import serial
import threading
import time
import logging
import sys
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Callable
from pynmeagps import NMEAReader
from .ntrip_client import NTRIPClient, NTRIPError, NTRIPConnectionError, NTRIPAuthenticationError
from config.nmea_utils import build_dummy_gga

logger = logging.getLogger(__name__)

NTRIP_RECONNECT_INTERVAL = 1.0  # seconds between NTRIP reconnection attempts
GPS_RECONNECT_INTERVAL = 5.0    # seconds between GPS reconnection attempts
GGA_UPLOAD_INTERVAL = 10.0      # seconds between GGA uploads to NTRIP

class RTKError(Exception):
    """Base exception for RTK-related errors"""
    pass

class RTKConnectionError(RTKError):
    """Exception for connection-related errors"""
    pass

class RTKConfigurationError(RTKError):
    """Exception for configuration-related errors"""
    pass

class RTKManager:

    def __init__(self):
        self.ntrip_client: Optional[NTRIPClient] = None
        self.gps_serial: Optional[serial.Serial] = None
        self.nmea_reader: Optional[NMEAReader] = None
        
        self.running = False
        self.rtk_status = "Disconnected"
        self.position_callback: Optional[Callable] = None
        self.current_position: Optional[Dict[str, Any]] = None
        
        self._state_lock = threading.RLock()
        self._position_lock = threading.Lock()
        
        try:
            from config.settings import rtk_config, uart_config
            self.ntrip_config = rtk_config
            self.uart_config = uart_config
            self._validate_configuration()
        except Exception as e:
            logger.error(f"Configuration error: {e}")
            raise RTKConfigurationError(f"Invalid configuration: {e}")
        
        self.nmea_thread: Optional[threading.Thread] = None
        self.gga_thread: Optional[threading.Thread] = None
        
        self._stats = {
            'rtcm_bytes_received': 0,
            'gga_uploads_sent': 0,
            'nmea_errors': 0,
            'connection_failures': 0,
            'last_rtcm_time': 0,
            'last_gga_time': 0,
            'rtcm_messages_processed': 0,
            'gga_real_vs_synthetic': {'real': 0, 'synthetic': 0, 'dummy': 0}
        }
        
    def _validate_configuration(self):
        required_uart_fields = ['port', 'baudrate']
        for field in required_uart_fields:
            if not self.uart_config.get(field):
                raise RTKConfigurationError(f"UART {field} is required")
        
        if not self.ntrip_config.get('enabled', False):
            logger.warning("NTRIP not configured - system will run in GPS-only mode")
            return
        
        required_ntrip_fields = ['caster', 'port', 'username', 'password']
        missing_fields = [field for field in required_ntrip_fields 
                         if not self.ntrip_config.get(field)]
        
        if missing_fields:
            logger.warning(f"NTRIP fields missing: {missing_fields} - NTRIP will be disabled")
            self.ntrip_config['enabled'] = False
    
    def get_statistics(self) -> Dict[str, Any]:
        with self._state_lock:
            ntrip_stats = {}
            if self.ntrip_client:
                ntrip_stats = self.ntrip_client.get_statistics()
            
            return {
                **self._stats,
                'running': self.running,
                'connections': {
                    'ntrip': self.ntrip_client and self.ntrip_client.is_connected(),
                    'gps': self.gps_serial is not None,
                },
                'threads_alive': {
                    'nmea': self.nmea_thread and self.nmea_thread.is_alive(),
                    'gga': self.gga_thread and self.gga_thread.is_alive(),
                },
                'ntrip': ntrip_stats
            }
        
    def initialize(self):
        try:
            logger.info("RTK Manager initializing...")
            return True
        except Exception as e:
            logger.error(f"RTK initialization error: {e}")
            return False
    
    def start(self):
        if self.running:
            logger.warning("RTK system is already running")
            return True
            
        try:
            self._connect_gps()
            
            ntrip_connected = self._connect_ntrip()
            
            if ntrip_connected:
                self.rtk_status = "RTK Connected"
                logger.info("Full RTK system started (GPS + NTRIP)")
            else:
                self.rtk_status = "GPS Only"
                logger.warning("Starting in GPS-only mode (NTRIP unavailable)")
            
            self.running = True
            self._start_threads()
            
            logger.info(f"RTK system started successfully in mode: {self.rtk_status}")
            return True
                
        except Exception as e:
            logger.error(f"Failed to start RTK system: {e}")
            return False
    
    def _connect_gps(self):
        baudrates_to_try = [115200, 38400, 9600]  # LC29H default is 115200
        
        for baudrate in baudrates_to_try:
            try:
                logger.info(f"Trying GPS connection at {baudrate} baud...")
                
                test_serial = serial.Serial(
                    port=self.uart_config["port"],
                    baudrate=baudrate,
                    timeout=2.0
                )
                
                if self._test_gps_communication(test_serial):
                    self.gps_serial = test_serial
                    self.uart_config["baudrate"] = baudrate  # Update config
                    
                    self.nmea_reader = NMEAReader(self.gps_serial)
                    
                    logger.info(f"GPS communication successful at {baudrate} baud")
                    logger.info(f"Connected to GPS on {self.uart_config['port']} at {baudrate} baud")
                    return
                else:
                    test_serial.close()
                    
            except Exception as e:
                logger.debug(f"Failed at {baudrate} baud: {e}")
                continue
        
        logger.warning("Failed to connect to GPS: No working baudrate found")
        self.gps_serial = None
        self.nmea_reader = None
        raise RTKConnectionError("Failed to establish GPS communication on any supported baudrate")
    
    def _test_gps_communication(self, serial_connection):
        """Test if GPS communication works at given baudrate"""
        try:
            serial_connection.reset_input_buffer()
            
            start_time = time.time()
            while time.time() - start_time < 3.0:
                if serial_connection.in_waiting > 0:
                    try:
                        line = serial_connection.readline().decode('ascii', errors='ignore').strip()
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
    
    def _connect_ntrip(self) -> bool:
        """
        Connect to NTRIP server using new NTRIPClient
        Returns True if connected, False if failed or not configured
        """
        # Check if NTRIP is configured
        if not self.ntrip_config.get('enabled', False):
            logger.info("NTRIP not configured - skipping NTRIP connection")
            return False
        
        try:
            # Create NTRIP client with callback for GGA data
            self.ntrip_client = NTRIPClient(
                config=self.ntrip_config,
                gga_callback=self._get_current_gga_bytes
            )
            
            # Attempt connection
            if self.ntrip_client.connect():
                # Start data reception with callback
                self.ntrip_client.start_data_reception(self._handle_rtcm_data)
                logger.info("NTRIP client connected and data reception started")
                return True
            else:
                logger.warning("NTRIP connection failed")
                self.ntrip_client = None
                return False
                
        except NTRIPAuthenticationError as e:
            logger.error(f"NTRIP authentication error: {e}")
            self.ntrip_client = None
            return False
        except NTRIPConnectionError as e:
            logger.error(f"NTRIP connection error: {e}")
            self.ntrip_client = None
            return False
        except Exception as e:
            logger.error(f"Unexpected NTRIP error: {e}")
            self.ntrip_client = None
            return False
    
    def _get_current_gga_bytes(self) -> Optional[bytes]:
        """
        Get current GGA sentence as bytes for NTRIP client.
        This callback should be quick and non-blocking.
        """
        try:
            # Primarily rely on the most recent position data.
            with self._position_lock:
                if self.current_position:
                    gga_sentence = self._build_gga_sentence()
                    if gga_sentence:
                        self._stats['gga_real_vs_synthetic']['synthetic'] += 1
                        return gga_sentence.encode('ascii')

            # If no position is available, fall back to a dummy GGA.
            dummy_gga = build_dummy_gga()
            self._stats['gga_real_vs_synthetic']['dummy'] += 1
            return dummy_gga.encode('ascii')
        except Exception as e:
            logger.debug(f"Error getting GGA bytes: {e}")
            return None
    
    def _get_real_gga_from_stream(self) -> Optional[bytes]:
        """
        Try to get real GGA sentence from GPS stream
        Similar to main.py getGGABytes() method
        """
        try:
            # Check if there's data available
            if self.gps_serial.in_waiting > 0:
                # Try to read a few messages to find GGA
                for _ in range(5):  # Limit attempts
                    try:
                        raw_data, parsed_data = self.nmea_reader.read()
                        if raw_data and (b"GNGGA" in raw_data or b"GPGGA" in raw_data):
                            logger.debug("Using real GGA from GPS stream")
                            self._stats['gga_real_vs_synthetic']['real'] += 1
                            return raw_data
                    except Exception:
                        continue
            
            return None
            
        except Exception as e:
            logger.debug(f"Error getting real GGA: {e}")
            return None
    
    def _build_dummy_gga(self) -> str:
        """Build dummy GGA using the centralized utility function."""
        self._stats['gga_real_vs_synthetic']['dummy'] += 1
        return build_dummy_gga()
    
    def _handle_rtcm_data(self, rtcm_data: bytes):
        """
        Handle RTCM data received from NTRIP client
        Forward it to GPS receiver (like in main.py pattern)
        """
        try:
            if self.gps_serial and rtcm_data:
                # Write RTCM data directly to GPS (like main.py: self.stream.write(data))
                bytes_written = self.gps_serial.write(rtcm_data)
                
                # Update statistics
                self._stats['rtcm_bytes_received'] += len(rtcm_data)
                self._stats['last_rtcm_time'] = time.time()
                self._stats['rtcm_messages_processed'] += 1
                
                # Verify write was successful
                if bytes_written != len(rtcm_data):
                    logger.warning(f"RTCM write incomplete: {bytes_written}/{len(rtcm_data)} bytes")
                else:
                    logger.debug(f"Forwarded {len(rtcm_data)} bytes of RTCM to GPS")
                
                # Force flush to ensure data reaches GPS immediately
                self.gps_serial.flush()
                
                # Read any immediate GPS response (like main.py pattern)
                self._process_immediate_gps_response()
            
        except Exception as e:
            logger.error(f"Error handling RTCM data: {e}")
            self._stats['connection_failures'] += 1
    
    def _process_immediate_gps_response(self):
        """
        Process any immediate GPS response after RTCM data
        Similar to main.py pattern: (raw_data, parsed_data) = self.nmr.read()
        """
        try:
            if self.gps_serial and self.nmea_reader and self.gps_serial.in_waiting > 0:
                # Try to read immediate response
                raw_data, parsed_data = self.nmea_reader.read()
                
                if raw_data and parsed_data:
                    # Check if it's a GGA message (position update)
                    if b"GNGGA" in raw_data or b"GPGGA" in raw_data:
                        logger.debug(f"GPS immediate response: {raw_data.decode('ascii', errors='ignore').strip()}")
                        self._process_nmea_message(raw_data, parsed_data)
                        
        except Exception as e:
            # Don't log errors here as it's optional processing
            pass
    
    def _start_threads(self):
        
        threads_started = []
        
        if self.gps_serial and self.nmea_reader:
            self.nmea_thread = threading.Thread(target=self._nmea_loop, daemon=True)
            self.nmea_thread.start()
            threads_started.append("NMEA processing")
        
        if self.ntrip_client and self.ntrip_client.is_connected():
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
    
    def _gga_upload_loop(self):
        if not self.ntrip_client or not self.ntrip_client.is_connected():
            logger.warning("GGA upload loop: No NTRIP connection, exiting")
            return
            
        logger.info("GGA upload loop started")
        
        while self.running and self.ntrip_client and self.ntrip_client.is_connected():
            try:
                time.sleep(GGA_UPLOAD_INTERVAL)
                
                if self.current_position:
                    gga_sentence = self._build_gga_sentence()
                    if gga_sentence:
                        gga_bytes = gga_sentence.encode('ascii')
                        if self.ntrip_client.send_gga(gga_bytes):
                            self._stats['gga_uploads_sent'] += 1
                            self._stats['last_gga_time'] = time.time()
                            logger.debug("GGA sent to NTRIP server")
                        else:
                            logger.warning("Failed to send GGA to NTRIP server")
                else:
                    logger.debug("No position available for GGA upload")
                        
            except Exception as e:
                logger.error(f"GGA upload loop error: {e}")
                break
                
        logger.info("GGA upload loop ended")
    
    def _nmea_loop(self):
        logger.info("NMEA processing loop started")
        
        consecutive_errors = 0
        max_consecutive_errors = 10
        
        while self.running and self.nmea_reader:
            try:
                # Check for serial port availability and data
                if not (self.gps_serial and self.gps_serial.is_open and self.gps_serial.in_waiting > 0):
                    time.sleep(0.1)
                    # If we lose connection, check for too many errors
                    if not (self.gps_serial and self.gps_serial.is_open):
                        consecutive_errors += 1
                    if consecutive_errors >= max_consecutive_errors:
                         logger.error("Lost GPS serial connection. Stopping NMEA loop.")
                         break
                    continue

                # Read and process data
                raw_data, parsed_data = self.nmea_reader.read()
                
                if raw_data and parsed_data:
                    self._process_nmea_message(raw_data, parsed_data)
                    consecutive_errors = 0  # Reset on success
                else:
                    # This can happen with incomplete messages
                    time.sleep(0.05)
            
            except serial.SerialException as se:
                logger.error(f"GPS serial error in NMEA loop: {se}")
                consecutive_errors += 1
                time.sleep(GPS_RECONNECT_INTERVAL)
            except Exception as e:
                # Handle checksum and other parsing errors from pynmeagps
                if "checksum" in str(e).lower() or "format" in str(e).lower():
                    self._stats['nmea_errors'] += 1
                    if self._stats['nmea_errors'] % 20 == 0: # Log periodically to avoid spam
                        logger.debug(f"NMEA format/checksum error: {e}")
                else:
                    logger.warning(f"Unhandled NMEA loop error: {e}")
                    consecutive_errors += 1
                
                time.sleep(0.1)

            # Check for exit condition
            if consecutive_errors >= max_consecutive_errors:
                logger.error("Too many consecutive errors in NMEA loop. Stopping.")
                self.running = False # Signal other threads to stop
                break
                
        logger.info(f"NMEA processing loop ended (total checksum errors: {self._stats['nmea_errors']})")
    
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
            
            # Update statistics
            self._stats['gga_real_vs_synthetic']['synthetic'] += 1
            
            return gga
            
        except Exception as e:
            logger.error(f"Error building GGA: {e}")
            return None
    
    def stop(self):
        """Stop RTK system"""
        logger.info("Stopping RTK system...")
        
        self.running = False
        self.rtk_status = "Disconnected"
        
        # Stop NTRIP client
        if self.ntrip_client:
            self.ntrip_client.disconnect()
            self.ntrip_client = None
        
        # Wait for threads to finish
        if self.nmea_thread and self.nmea_thread.is_alive():
            self.nmea_thread.join(timeout=2)
        if self.gga_thread and self.gga_thread.is_alive():
            self.gga_thread.join(timeout=2)
        
        self._cleanup_connections()
        logger.info("RTK system stopped")
    
    def _cleanup_connections(self):
        """Clean up all connections"""
        logger.debug("Cleaning up connections...")
        
        # Clean up NTRIP client (should already be done in stop())
        if self.ntrip_client:
            self.ntrip_client.disconnect()
            self.ntrip_client = None
            
        # Clean up GPS serial connection
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
        """Get RTK system status with enhanced diagnostics"""
        status = {
            "rtk_status": self.rtk_status,
            "running": self.running,
            "ntrip_connected": self.ntrip_client and self.ntrip_client.is_connected(),
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
                status["rtk_ready_reason"] = f"Poor signal: HDOP={hdop:.1f}, Satellites={satellites}"
        else:
            status["signal_quality"] = "No Signal"
            status["rtk_ready"] = False
            status["rtk_ready_reason"] = "No GPS position available"
            
        return status
    
    def get_current_position(self):
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
