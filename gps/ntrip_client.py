import socket
import base64
import time
import threading
import logging
import ssl
from typing import Optional, Callable, Dict, Any
from config.nmea_utils import build_dummy_gga
from .rtcm_parser import RTCMParser, RTCMValidator, RTCMMessage

logger = logging.getLogger(__name__)

NTRIP_RECONNECT_INTERVAL = 1.0 
NTRIP_MAX_RECONNECT_ATTEMPTS = 5
NTRIP_CONNECTION_TIMEOUT = 10.0
NTRIP_DATA_TIMEOUT = 3.0
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
    def __init__(self, config: Dict[str, Any], gga_callback: Optional[Callable] = None):
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
        
        self.rtcm_parser = RTCMParser()
        self.rtcm_validator = RTCMValidator()
        
        self._validate_config()
        
        self._prepare_auth()
        
        self.use_ssl = config.get('ssl', False)
        self.verbose = config.get('verbose', False)
        
    def _validate_config(self):
        required_fields = ['caster', 'port', 'mountpoint', 'username', 'password']
        missing_fields = [field for field in required_fields if not self.config.get(field)]
        
        if missing_fields:
            raise NTRIPError(f"Missing required NTRIP configuration fields: {missing_fields}")
        
        # Validate port range
        port = self.config.get('port')
        if not isinstance(port, int) or port < 1 or port > 65535:
            raise NTRIPError(f"Invalid port number: {port}")
    
    def _prepare_auth(self):
        auth_string = f"{self.config['username']}:{self.config['password']}"
        self.auth_b64 = base64.b64encode(auth_string.encode('utf-8')).decode('utf-8')
    
    def _build_request(self) -> bytes:
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
        with self._lock:
            if self.connected:
                logger.warning("NTRIP already connected")
                return True
            
            try:
                self.connection_attempts += 1
                logger.info(f"Connecting to NTRIP caster {self.config['caster']}:{self.config['port']} "
                           f"(attempt {self.connection_attempts})")
                
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.socket.settimeout(NTRIP_CONNECTION_TIMEOUT)
                
                if self.use_ssl:
                    self.socket = ssl.wrap_socket(self.socket)
                
                error_indicator = self.socket.connect_ex((self.config["caster"], self.config["port"]))
                if error_indicator != 0:
                    raise NTRIPConnectionError(f"Socket connection failed with error: {error_indicator}")
                
                request = self._build_request()
                self.socket.sendall(request)
                
                if self._process_response():
                    self.connected = True
                    logger.info("NTRIP connection established successfully")
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
                    
                    if line == "":
                        found_header = True
                        if self.verbose:
                            logger.debug("End of NTRIP headers")
                        break
                    
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
        try:
            gga_data = self._get_gga_data()
            if gga_data:
                self.socket.sendall(gga_data)
                if self.verbose:
                    logger.debug("Initial GGA sent to NTRIP caster")
        except Exception as e:
            logger.warning(f"Failed to send initial GGA: {e}")
    
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
            daemon=True,
            name="NTRIPDataReceiver"
        )
        self._data_thread.start()
        return True
    
    def _data_reception_loop(self, data_callback: Callable[[bytes], None]):
        reconnect_attempts = 0
        last_gga_time = 0
        gga_interval = 1.0
        
        while self.running and reconnect_attempts < NTRIP_MAX_RECONNECT_ATTEMPTS:
            try:                
                if self.socket:
                    self.socket.settimeout(NTRIP_DATA_TIMEOUT)

                data = self.socket.recv(NTRIP_RESPONSE_BUFFER_SIZE)
                
                if data:
                    self.bytes_received += len(data)
                    self.last_data_time = time.time()
                    
                    data_type = self.rtcm_validator.detect_data_type(data)
                    
                    if data_type == 'nmea':
                        text = data.decode('ascii', errors='ignore').strip()
                        logger.error(f"❌ CRITICAL: NTRIP Mount Point '{self.config.get('mountpoint', 'unknown')}' sending NMEA instead of RTCM!")
                        logger.error(f"   Received NMEA: {text[:100]}...")
                        logger.error(f"   🔧 FIX: Change mount point to one that provides RTCM corrections")
                        logger.error(f"   📡 Suggested mount points: NEAR, POZN, WROC (for Poland)")
                        continue
                    
                    elif data_type == 'rtcm':
                        logger.info(f"🔧 Processing RTCM data: {len(data)} bytes")
                        
                        rtcm_messages = self.rtcm_parser.add_data(data)

                        if rtcm_messages:
                            logger.info(f"📦 Parsed {len(rtcm_messages)} RTCM messages")
                            
                            for message in rtcm_messages:
                                if message.is_valid:
                                    #logger.info(f"✅ Forwarding RTCM {message.message_type}: {len(message.raw_message)} bytes")
                                    data_callback(message.raw_message)

                                    msg_name = self.rtcm_parser.rtcm_message_types.get(
                                        message.message_type, f"Type {message.message_type}"
                                    )
                                    #logger.debug(f"📡 RTCM {message.message_type} ({msg_name}): {len(message.raw_message)} bytes → GPS")
                                else:
                                    logger.warning(
                                        f"❌ Dropped RTCM type {message.message_type}: CRC invalid (len={message.length})"
                                    )
                        else:
                            logger.debug("📝 RTCM data buffered, waiting for complete messages")
                    
                    else:
                        hex_preview = ' '.join([f'{b:02x}' for b in data[:20]])
                        logger.debug(f"⚠️  Unknown data type from NTRIP. First 20 bytes: {hex_preview}")
                    
                    current_time = time.time()
                    if current_time - last_gga_time >= gga_interval:
                        self._send_periodic_gga()
                        last_gga_time = current_time
                    
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
    
    def _send_periodic_gga(self):
        try:
            gga_data = self._get_gga_data()
            if gga_data:
                self.socket.sendall(gga_data)
                if self.verbose:
                    logger.debug("Periodic GGA sent to NTRIP caster")
        except Exception as e:
            logger.warning(f"Failed to send periodic GGA: {e}")
    
    def _reconnect(self) -> bool:
        try:
            self._cleanup_socket()
            return self.connect()
        except Exception as e:
            logger.error(f"Reconnection failed: {e}")
            return False
    
    def send_gga(self, gga_data: bytes) -> bool:
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
        logger.info("Disconnecting from NTRIP caster...")
        self.running = False
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
                finally:
                    self.socket = None
    
    def get_statistics(self) -> Dict[str, Any]:
        base_stats = {
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
        
        rtcm_stats = self.rtcm_parser.get_statistics()
        base_stats['rtcm_parser'] = rtcm_stats
        
        return base_stats
    
    def is_connected(self) -> bool:
        return self.connected and self.socket is not None
    
    def is_running(self) -> bool:
        return self.running

NTRIPClient = NTRIPClient
