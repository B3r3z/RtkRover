#!/usr/bin/env python3
"""
Enhanced NTRIP Client for RTK Rover
Based on ntrip_client_new but adapted to the application architecture
Provides clean separation between GPS and NTRIP functionality
"""

import socket
import sys
import datetime
import base64
import time
import threading
import logging
import ssl
from typing import Optional, Callable, Dict, Any
from config.nmea_utils import build_dummy_gga

logger = logging.getLogger(__name__)

# Configuration constants
NTRIP_RECONNECT_INTERVAL = 1.0  # seconds between reconnection attempts
NTRIP_MAX_RECONNECT_ATTEMPTS = 5
NTRIP_CONNECTION_TIMEOUT = 10.0  # seconds
NTRIP_DATA_TIMEOUT = 3.0  # seconds for data reception
NTRIP_RESPONSE_BUFFER_SIZE = 4096
NTRIP_USER_AGENT = "RTKRover/1.0"

class NTRIPError(Exception):
    """Base exception for NTRIP-related errors"""
    pass

class NTRIPConnectionError(NTRIPError):
    """Exception for connection-related errors"""
    pass

class NTRIPAuthenticationError(NTRIPError):
    """Exception for authentication-related errors"""
    pass

class NTRIPClient:
    """
    Enhanced NTRIP Client adapted from ntrip_client_new
    Provides clean callback-based interface for RTK application
    """
    
    def __init__(self, config: Dict[str, Any], gga_callback: Optional[Callable] = None):
        """
        Initialize NTRIP client
        
        Args:
            config: Configuration dictionary with keys:
                   - caster: NTRIP caster hostname
                   - port: NTRIP caster port
                   - mountpoint: Mount point name
                   - username: Username for authentication
                   - password: Password for authentication
                   - ssl: Whether to use SSL (optional, default False)
                   - verbose: Verbose logging (optional, default False)
            gga_callback: Callback function to get current GGA data as bytes
        """
        self.config = config
        self.gga_callback = gga_callback
        self.socket: Optional[socket.socket] = None
        self.connected = False
        self.running = False
        self.bytes_received = 0
        self.connection_attempts = 0
        self.last_data_time = 0
        self._data_thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()
        
        # Configuration validation
        self._validate_config()
        
        # Prepare authentication
        self._prepare_auth()
        
        # SSL support
        self.use_ssl = config.get('ssl', False)
        self.verbose = config.get('verbose', False)
        
    def _validate_config(self):
        """Validate NTRIP configuration"""
        required_fields = ['caster', 'port', 'mountpoint', 'username', 'password']
        missing_fields = [field for field in required_fields if not self.config.get(field)]
        
        if missing_fields:
            raise NTRIPError(f"Missing required NTRIP configuration fields: {missing_fields}")
        
        # Validate port range
        port = self.config.get('port')
        if not isinstance(port, int) or port < 1 or port > 65535:
            raise NTRIPError(f"Invalid port number: {port}")
    
    def _prepare_auth(self):
        """Prepare authentication string"""
        auth_string = f"{self.config['username']}:{self.config['password']}"
        self.auth_b64 = base64.b64encode(auth_string.encode('utf-8')).decode('utf-8')
    
    def _build_request(self) -> bytes:
        """Build NTRIP HTTP request"""
        mountpoint = self.config["mountpoint"]
        if not mountpoint.startswith('/'):
            mountpoint = f"/{mountpoint}"
        
        request_string = f"GET {mountpoint} HTTP/1.1\r\n"
        request_string += f"User-Agent: {NTRIP_USER_AGENT}\r\n"
        request_string += f"Authorization: Basic {self.auth_b64}\r\n"
        request_string += f"Host: {self.config['caster']}:{self.config['port']}\r\n"
        request_string += "\r\n"
        
        if self.verbose:
            logger.debug(f"NTRIP request:\n{request_string}")
        
        return bytes(request_string, 'ascii')
    
    def _get_gga_data(self) -> Optional[bytes]:
        """Get GGA data from callback or build dummy"""
        try:
            if self.gga_callback:
                gga_data = self.gga_callback()
                if gga_data:
                    return gga_data
        except Exception as e:
            logger.warning(f"Failed to get GGA from callback: {e}")
        
        # Fallback to dummy GGA
        dummy_gga = build_dummy_gga()
        return dummy_gga.encode('utf-8')
    
    def connect(self) -> bool:
        """Connect to NTRIP caster"""
        with self._lock:
            if self.connected:
                logger.warning("NTRIP already connected")
                return True
            
            try:
                self.connection_attempts += 1
                logger.info(f"Connecting to NTRIP caster {self.config['caster']}:{self.config['port']} "
                           f"(attempt {self.connection_attempts})")
                
                # Create socket
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.socket.settimeout(NTRIP_CONNECTION_TIMEOUT)
                
                # SSL wrapper if needed
                if self.use_ssl:
                    self.socket = ssl.wrap_socket(self.socket)
                
                # Connect
                error_indicator = self.socket.connect_ex((self.config["caster"], self.config["port"]))
                if error_indicator != 0:
                    raise NTRIPConnectionError(f"Socket connection failed with error: {error_indicator}")
                
                # Send request
                request = self._build_request()
                self.socket.sendall(request)
                
                # Process response
                if self._process_response():
                    self.connected = True
                    logger.info("NTRIP connection established successfully")
                    
                    # Send initial GGA
                    self._send_initial_gga()
                    return True
                else:
                    self._cleanup_socket()
                    return False
                
            except Exception as e:
                logger.error(f"NTRIP connection error: {e}")
                self._cleanup_socket()
                return False
    
    def _process_response(self) -> bool:
        """Process NTRIP caster response"""
        found_header = False
        connection_accepted = False
        
        try:
            while not found_header:
                caster_response = self.socket.recv(NTRIP_RESPONSE_BUFFER_SIZE)
                if not caster_response:
                    raise NTRIPConnectionError("No response from NTRIP caster")
                
                response_text = caster_response.decode('utf-8', errors='ignore')
                header_lines = response_text.split("\r\n")
                
                for line in header_lines:
                    line = line.strip()
                    
                    if self.verbose and line:
                        logger.debug(f"NTRIP header: {line}")
                    
                    # Check for end of headers
                    if line == "":
                        found_header = True
                        if self.verbose:
                            logger.debug("End of NTRIP headers")
                        break
                    
                    # Check response status
                    if "SOURCETABLE" in line:
                        raise NTRIPConnectionError("Mount point does not exist - received source table")
                    elif "401 Unauthorized" in line:
                        raise NTRIPAuthenticationError("Unauthorized - check username/password")
                    elif "404 Not Found" in line:
                        raise NTRIPConnectionError("Mount point not found")
                    elif any(ok_response in line for ok_response in ["ICY 200 OK", "HTTP/1.0 200 OK", "HTTP/1.1 200 OK"]):
                        connection_accepted = True
                        if self.verbose:
                            logger.debug(f"NTRIP connection accepted: {line}")
            
            if not connection_accepted:
                raise NTRIPConnectionError("No valid acceptance response received")
            
            return True
            
        except Exception as e:
            logger.error(f"Error processing NTRIP response: {e}")
            return False
    
    def _send_initial_gga(self):
        """Send initial GGA sentence to caster"""
        try:
            gga_data = self._get_gga_data()
            if gga_data:
                self.socket.sendall(gga_data)
                if self.verbose:
                    logger.debug("Initial GGA sent to NTRIP caster")
        except Exception as e:
            logger.warning(f"Failed to send initial GGA: {e}")
    
    def start_data_reception(self, data_callback: Callable[[bytes], None]) -> bool:
        """
        Start receiving RTCM data in background thread
        
        Args:
            data_callback: Callback function to handle received RTCM data
        """
        if not self.connected:
            logger.error("Cannot start data reception - not connected")
            return False
        
        if self.running:
            logger.warning("Data reception already running")
            return True
        
        self.running = True
        self._data_thread = threading.Thread(
            target=self._data_reception_loop, 
            args=(data_callback,), 
            daemon=True,
            name="NTRIPDataReceiver"
        )
        self._data_thread.start()
        logger.info("NTRIP data reception started")
        return True
    
    def _data_reception_loop(self, data_callback: Callable[[bytes], None]):
        """Main data reception loop"""
        logger.info("NTRIP data reception loop started")
        
        reconnect_attempts = 0
        last_gga_time = 0
        gga_interval = 10.0  # Send GGA every 10 seconds
        
        while self.running and reconnect_attempts < NTRIP_MAX_RECONNECT_ATTEMPTS:
            try:
                # Set socket timeout for data reception
                if self.socket:
                    self.socket.settimeout(NTRIP_DATA_TIMEOUT)
                
                # Receive data
                data = self.socket.recv(NTRIP_RESPONSE_BUFFER_SIZE)
                
                if data:
                    self.bytes_received += len(data)
                    self.last_data_time = time.time()
                    
                    # Validate and process RTCM data
                    if self._validate_rtcm_data(data):
                        data_callback(data)
                        if self.verbose:
                            logger.debug(f"Received {len(data)} bytes of RTCM data")
                    else:
                        logger.warning(f"Received non-RTCM data: {data[:50]}...")
                    
                    # Send periodic GGA updates
                    current_time = time.time()
                    if current_time - last_gga_time >= gga_interval:
                        self._send_periodic_gga()
                        last_gga_time = current_time
                    
                    # Reset reconnect attempts on successful data
                    reconnect_attempts = 0
                else:
                    logger.warning("No data received from NTRIP caster")
                    break
                    
            except socket.timeout:
                logger.debug("NTRIP data timeout - continuing...")
                continue
            except Exception as e:
                logger.error(f"Error in NTRIP data reception: {e}")
                reconnect_attempts += 1
                
                if reconnect_attempts < NTRIP_MAX_RECONNECT_ATTEMPTS:
                    logger.info(f"Reconnecting to NTRIP... (attempt {reconnect_attempts})")
                    time.sleep(NTRIP_RECONNECT_INTERVAL * reconnect_attempts)
                    
                    # Try to reconnect
                    if self._reconnect():
                        logger.info("NTRIP reconnection successful")
                        reconnect_attempts = 0
                    else:
                        logger.warning("NTRIP reconnection failed")
                else:
                    logger.error("Max NTRIP reconnection attempts reached")
                    break
        
        logger.info("NTRIP data reception loop ended")
        self.running = False
    
    def _validate_rtcm_data(self, data: bytes) -> bool:
        """Validate if received data contains RTCM messages"""
        if not data or len(data) < 3:
            return False
        
        # Check for RTCM 3.x preamble (0xD3)
        for i in range(len(data) - 2):
            if data[i] == 0xD3:
                return True
        
        # Also allow raw binary data that might be RTCM
        return True
    
    def _send_periodic_gga(self):
        """Send periodic GGA update to caster"""
        try:
            gga_data = self._get_gga_data()
            if gga_data:
                self.socket.sendall(gga_data)
                if self.verbose:
                    logger.debug("Periodic GGA sent to NTRIP caster")
        except Exception as e:
            logger.warning(f"Failed to send periodic GGA: {e}")
    
    def _reconnect(self) -> bool:
        """Attempt to reconnect to NTRIP caster"""
        try:
            self._cleanup_socket()
            return self.connect()
        except Exception as e:
            logger.error(f"Reconnection failed: {e}")
            return False
    
    def send_gga(self, gga_data: bytes) -> bool:
        """Send GGA data to caster manually"""
        with self._lock:
            if not self.connected or not self.socket:
                return False
            
            try:
                self.socket.sendall(gga_data)
                return True
            except Exception as e:
                logger.error(f"Failed to send GGA: {e}")
                return False
    
    def disconnect(self):
        """Disconnect from NTRIP caster"""
        logger.info("Disconnecting from NTRIP caster...")
        
        self.running = False
        
        # Wait for data thread to finish
        if self._data_thread and self._data_thread.is_alive():
            self._data_thread.join(timeout=2)
        
        self._cleanup_socket()
        logger.info("NTRIP disconnected")
    
    def _cleanup_socket(self):
        """Clean up socket connection"""
        with self._lock:
            self.connected = False
            if self.socket:
                try:
                    self.socket.close()
                except:
                    pass
                finally:
                    self.socket = None
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get client statistics"""
        return {
            'connected': self.connected,
            'running': self.running,
            'bytes_received': self.bytes_received,
            'connection_attempts': self.connection_attempts,
            'last_data_time': self.last_data_time,
            'config': {
                'caster': self.config['caster'],
                'port': self.config['port'],
                'mountpoint': self.config['mountpoint'],
                'username': self.config['username'][:3] + '***' if self.config['username'] else 'None',
                'ssl': self.use_ssl
            }
        }
    
    def is_connected(self) -> bool:
        """Check if client is connected"""
        return self.connected and self.socket is not None
    
    def is_running(self) -> bool:
        """Check if client is running (receiving data)"""
        return self.running


# Backward compatibility - create alias for existing code
NTRIPClient = NTRIPClient
