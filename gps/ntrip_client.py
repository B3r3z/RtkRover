#!/usr/bin/env python3
"""
NTRIP Client - based on Waveshare LC29H examples and NtripPerlClient
Adapted for RTK Rover project with ASG-EUPOS compatibility
"""

import socket
import base64
import time
import threading
import logging
from typing import Optional, Callable, Dict, Any

logger = logging.getLogger(__name__)


NTRIP_RECONNECT_INTERVAL = 1.0  # seconds between reconnection attempts
NTRIP_MAX_RECONNECT_ATTEMPTS = 5
NTRIP_CONNECTION_TIMEOUT = 10.0  # seconds
NTRIP_DATA_TIMEOUT = 3.0  # seconds for data reception
NTRIP_RESPONSE_BUFFER_SIZE = 4096

class NTRIPError(Exception):
    pass

class NTRIPConnectionError(NTRIPError):
    pass

class NTRIPAuthenticationError(NTRIPError):
    pass

class NTRIPClient:    
    def __init__(self, config: Dict[str, Any], gga_callback: Optional[Callable] = None):
        self.config = config
        self.gga_callback = gga_callback
        self.socket: Optional[socket.socket] = None
        self.connected = False
        self.running = False
        self.user_agent = "NTRIP RTKRover/1.0"
        self.bytes_received = 0
        self.connection_attempts = 0
        self.last_data_time = 0
        self._data_thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()
        self._prepare_auth()
    
    def _prepare_auth(self):
        auth_string = f"{self.config['username']}:{self.config['password']}"
        self.auth_b64 = base64.b64encode(auth_string.encode('utf-8')).decode('utf-8')
    
    def _build_request(self) -> bytes:
        mountpoint = self.config["mountpoint"]
        if not mountpoint.startswith('/'):
            mountpoint = f"/{mountpoint}"
        request_string = f"GET {mountpoint} HTTP/1.1\r\n"
        request_string += f"User-Agent: {self.user_agent}\r\n"
        request_string += f"Authorization: Basic {self.auth_b64}\r\n"
        
        request_string += f"Host: {self.config['caster']}:{self.config['port']}\r\n"
        request_string += "\r\n"
        
        logger.debug(f"NTRIP request:\n{request_string}")
        return bytes(request_string, 'ascii')
    
    def connect(self) -> bool:
        with self._lock:
            if self.connected:
                logger.warning("NTRIP already connected")
                return True
            
            try:
                self.connection_attempts += 1
                logger.info(f"Connecting to NTRIP caster {self.config['caster']}:{self.config['port']} (attempt {self.connection_attempts})")
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.socket.settimeout(NTRIP_CONNECTION_TIMEOUT)
                
                error_indicator = self.socket.connect_ex((self.config["caster"], self.config["port"]))
                if error_indicator != 0:
                    raise NTRIPConnectionError(f"Connection failed with error {error_indicator}")
                
                
                request = self._build_request()
                self.socket.sendall(request)
                
                
                if self._process_response():
                    self.connected = True
                    self.socket.settimeout(NTRIP_DATA_TIMEOUT)
                    logger.info("NTRIP connection established successfully")
                    return True
                else:
                    self._cleanup_socket()
                    return False
                
            except Exception as e:
                logger.error(f"NTRIP connection error: {e}")
                self._cleanup_socket()
                return False
    
    def _process_response(self) -> bool:
        found_header = False
        
        try:
            while not found_header:
                caster_response = self.socket.recv(NTRIP_RESPONSE_BUFFER_SIZE)
                if not caster_response:
                    raise NTRIPConnectionError("No response from caster")
                
                response_str = caster_response.decode('utf-8')
                header_lines = response_str.split("\r\n")
                
                logger.debug(f"NTRIP response: {response_str}")
                

                for line in header_lines:
                    if line == "":
                        if not found_header:
                            found_header = True
                            logger.debug("End of NTRIP headers")
                    else:
                        logger.debug(f"NTRIP Header: {line}")
                    
                    if line.find("SOURCETABLE") >= 0:
                        raise NTRIPAuthenticationError("Mount point does not exist (SOURCETABLE response)")
                    elif line.find("401 Unauthorized") >= 0:
                        raise NTRIPAuthenticationError("Unauthorized request - check username/password")
                    elif line.find("404 Not Found") >= 0:
                        raise NTRIPAuthenticationError("Mount point does not exist (404)")
                    
                    elif (line.find("ICY 200 OK") >= 0 or 
                          line.find("HTTP/1.0 200 OK") >= 0 or 
                          line.find("HTTP/1.1 200 OK") >= 0):
                        
                        logger.info(f"NTRIP connection accepted: {line}")
                        self._send_initial_gga()
                        return True
            
            raise NTRIPConnectionError("No valid response received")
            
        except Exception as e:
            logger.error(f"Error processing NTRIP response: {e}")
            return False
    
    def _send_initial_gga(self):

        try:
            if self.gga_callback:
                gga_data = self.gga_callback()
                if gga_data:
                    self.socket.sendall(gga_data)
                    logger.debug("Initial GGA sent to NTRIP caster")
                    return
            
            dummy_gga = self._build_dummy_gga()
            if dummy_gga:
                self.socket.sendall(dummy_gga.encode('ascii'))
                logger.debug("Dummy GGA sent to NTRIP caster")
                
        except Exception as e:
            logger.warning(f"Failed to send initial GGA: {e}")
    
    def _build_dummy_gga(self) -> str:
        current_time = time.strftime('%H%M%S')
        # Poland center coordinates for keep-alive
        dummy_gga = f"$GNGGA,{current_time},5213.0000,N,02100.0000,E,1,08,1.0,100.0,M,0.0,M,,*00\r\n"
        return dummy_gga
    
    def start_data_reception(self, data_callback: Callable[[bytes], None]) -> bool:
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
            daemon=True
        )
        self._data_thread.start()
        logger.info("NTRIP data reception started")
        return True
    
    def _data_reception_loop(self, data_callback: Callable[[bytes], None]):
        logger.info("NTRIP data reception loop started")
        
        reconnect_attempts = 0
        
        while self.running and reconnect_attempts < NTRIP_MAX_RECONNECT_ATTEMPTS:
            try:
                if not self.connected or not self.socket:
                    # Try to reconnect
                    logger.info("Attempting NTRIP reconnection...")
                    if self.connect():
                        reconnect_attempts = 0  # Reset counter on success
                    else:
                        reconnect_attempts += 1
                        logger.warning(f"NTRIP reconnection failed ({reconnect_attempts}/{NTRIP_MAX_RECONNECT_ATTEMPTS})")
                        time.sleep(NTRIP_RECONNECT_INTERVAL)
                        continue
                
                # Receive data
                data = self.socket.recv(1024)
                
                if data:
                    self.bytes_received += len(data)
                    self.last_data_time = time.time()
                    
                    # Forward data to callback
                    data_callback(data)
                    
                    logger.debug(f"Received {len(data)} bytes of RTCM data")
                else:
                    # No data received - connection might be lost
                    logger.warning("No data received from NTRIP - connection lost")
                    self._cleanup_socket()
                    
            except socket.timeout:
                # Timeout is normal - continue
                continue
            except Exception as e:
                logger.error(f"NTRIP data reception error: {e}")
                self._cleanup_socket()
                reconnect_attempts += 1
                time.sleep(NTRIP_RECONNECT_INTERVAL)
        
        logger.info("NTRIP data reception loop ended")
        self.running = False
    
    def send_gga(self, gga_data: bytes) -> bool:
        with self._lock:
            if not self.connected or not self.socket:
                return False
            
            try:
                self.socket.sendall(gga_data)
                logger.debug("GGA sent to NTRIP caster")
                return True
            except Exception as e:
                logger.error(f"Failed to send GGA: {e}")
                self._cleanup_socket()
                return False
    
    def disconnect(self):
        logger.info("Disconnecting from NTRIP caster...")
        
        self.running = False
        
        # Wait for data thread to finish
        if self._data_thread and self._data_thread.is_alive():
            self._data_thread.join(timeout=2)
        
        self._cleanup_socket()
        logger.info("NTRIP disconnected")
    
    def _cleanup_socket(self):
        with self._lock:
            self.connected = False
            if self.socket:
                try:
                    self.socket.close()
                except:
                    pass
                self.socket = None
    
    def get_statistics(self) -> Dict[str, Any]:
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
                'username': self.config['username'][:3] + '***' if self.config['username'] else 'None'
            }
        }
    
    def is_connected(self) -> bool:
        return self.connected and self.socket is not None
    
    def is_running(self) -> bool:
        return self.running
