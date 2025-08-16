import serial
import threading
import time
import logging
import sys
import queue
import collections
import statistics
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Callable, List, Tuple
from pynmeagps import NMEAReader
from .ntrip_client import NTRIPClient, NTRIPError, NTRIPConnectionError, NTRIPAuthenticationError
from .rtcm_parser import RTCMValidator
from config.nmea_utils import build_dummy_gga

logger = logging.getLogger(__name__)

NTRIP_RECONNECT_INTERVAL = 1.0  # seconds between NTRIP reconnection attempts
GPS_RECONNECT_INTERVAL = 5.0    # seconds between GPS reconnection attempts
GGA_UPLOAD_INTERVAL = 10.0      # seconds between GGA uploads to NTRIP

# Queue configuration
RTCM_QUEUE_SIZE = 100          # Maximum RTCM messages in queue
NMEA_BUFFER_SIZE = 200         # Maximum NMEA messages in buffer
PERFORMANCE_WINDOW_SIZE = 1000 # Number of operations to track for performance

class PerformanceMonitor:
    """Monitor RTK system performance metrics"""
    
    def __init__(self):
        self.metrics = {
            'nmea_read_latency': collections.deque(maxlen=PERFORMANCE_WINDOW_SIZE),
            'rtcm_write_latency': collections.deque(maxlen=PERFORMANCE_WINDOW_SIZE),
            'queue_depths': collections.deque(maxlen=PERFORMANCE_WINDOW_SIZE),
            'corruption_events': 0,
            'total_operations': 0
        }
        self._lock = threading.Lock()
    
    def track_operation(self, operation: str, duration: float):
        """Track operation performance"""
        with self._lock:
            if f'{operation}_latency' in self.metrics:
                self.metrics[f'{operation}_latency'].append(duration)
                self.metrics['total_operations'] += 1
    
    def track_queue_depth(self, depth: int):
        """Track queue depth"""
        with self._lock:
            self.metrics['queue_depths'].append(depth)
    
    def increment_corruption(self):
        """Increment corruption event counter"""
        with self._lock:
            self.metrics['corruption_events'] += 1
    
    def get_performance_report(self) -> Dict[str, Any]:
        """Generate performance analysis"""
        with self._lock:
            report = {}
            
            if self.metrics['nmea_read_latency']:
                report['avg_nmea_latency_ms'] = statistics.mean(self.metrics['nmea_read_latency']) * 1000
                report['max_nmea_latency_ms'] = max(self.metrics['nmea_read_latency']) * 1000
            
            if self.metrics['rtcm_write_latency']:
                report['avg_rtcm_latency_ms'] = statistics.mean(self.metrics['rtcm_write_latency']) * 1000
                report['max_rtcm_latency_ms'] = max(self.metrics['rtcm_write_latency']) * 1000
            
            if self.metrics['queue_depths']:
                report['avg_queue_depth'] = statistics.mean(self.metrics['queue_depths'])
                report['max_queue_depth'] = max(self.metrics['queue_depths'])
            
            if self.metrics['total_operations'] > 0:
                report['corruption_rate'] = self.metrics['corruption_events'] / self.metrics['total_operations']
            
            return report

class SerialBufferManager:
    """Manage serial data buffers and separation"""
    
    def __init__(self):
        self.nmea_buffer = bytearray()
        self.rtcm_buffer = bytearray()
        self.corruption_detector = RTCMValidator()
        self._buffer_lock = threading.Lock()
        
    def process_serial_data(self, data: bytes) -> Tuple[List[bytes], List[bytes]]:
        """Separate NMEA and RTCM data efficiently"""
        with self._buffer_lock:
            nmea_messages = []
            rtcm_messages = []
            
            # Add to buffer
            self.nmea_buffer.extend(data)
            
            # Extract complete messages
            while True:
                # Look for NMEA messages (start with $, end with \r\n)
                nmea_start = self.nmea_buffer.find(b'$')
                if nmea_start >= 0:
                    nmea_end = self.nmea_buffer.find(b'\r\n', nmea_start)
                    if nmea_end >= 0:
                        # Extract complete NMEA message
                        nmea_msg = bytes(self.nmea_buffer[nmea_start:nmea_end + 2])
                        nmea_messages.append(nmea_msg)
                        # Remove from buffer
                        del self.nmea_buffer[nmea_start:nmea_end + 2]
                        continue
                
                # Look for RTCM messages (start with 0xD3)
                rtcm_start = self.nmea_buffer.find(b'\xd3')
                if rtcm_start >= 0:
                    # Check if we have enough data for length
                    if len(self.nmea_buffer) >= rtcm_start + 3:
                        # Extract RTCM length
                        length_bytes = self.nmea_buffer[rtcm_start + 1:rtcm_start + 3]
                        rtcm_length = ((length_bytes[0] & 0x03) << 8) | length_bytes[1]
                        total_length = rtcm_length + 6  # Header (3) + Data + CRC (3)
                        
                        if len(self.nmea_buffer) >= rtcm_start + total_length:
                            # Extract complete RTCM message
                            rtcm_msg = bytes(self.nmea_buffer[rtcm_start:rtcm_start + total_length])
                            rtcm_messages.append(rtcm_msg)
                            # Remove from buffer
                            del self.nmea_buffer[rtcm_start:rtcm_start + total_length]
                            continue
                
                # No more complete messages
                break
            
            # Trim buffer if too large
            if len(self.nmea_buffer) > 4096:
                self.nmea_buffer = self.nmea_buffer[-2048:]
            
            return nmea_messages, rtcm_messages

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
        
        # Threading and synchronization
        self._state_lock = threading.RLock()
        self._position_lock = threading.Lock()
        
        # Queue-based architecture
        self.rtcm_write_queue = queue.Queue(maxsize=RTCM_QUEUE_SIZE)
        self.nmea_read_buffer = collections.deque(maxlen=NMEA_BUFFER_SIZE)
        
        # Performance monitoring
        self.performance_monitor = PerformanceMonitor()
        self.buffer_manager = SerialBufferManager()
        
        # Configuration
        try:
            from config.settings import rtk_config, uart_config
            self.ntrip_config = rtk_config
            self.uart_config = uart_config
            self._validate_configuration()
        except Exception as e:
            logger.error(f"Configuration error: {e}")
            raise RTKConfigurationError(f"Invalid configuration: {e}")
        
        # Threads
        self.nmea_thread: Optional[threading.Thread] = None
        self.gga_thread: Optional[threading.Thread] = None
        self.rtcm_writer_thread: Optional[threading.Thread] = None
        
        # Statistics
        self._stats = {
            'rtcm_bytes_received': 0,
            'gga_uploads_sent': 0,
            'nmea_errors': 0,
            'connection_failures': 0,
            'last_rtcm_time': 0,
            'last_gga_time': 0,
            'rtcm_messages_processed': 0,
            'rtcm_messages_queued': 0,
            'rtcm_queue_overflows': 0,
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
            
            # Include performance metrics
            performance_report = self.performance_monitor.get_performance_report()
            
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
                    'rtcm_writer': self.rtcm_writer_thread and self.rtcm_writer_thread.is_alive(),
                },
                'queue_status': {
                    'rtcm_queue_size': self.rtcm_write_queue.qsize(),
                    'nmea_buffer_size': len(self.nmea_read_buffer),
                },
                'performance': performance_report,
                'ntrip': ntrip_stats
            }
    
    def _rtcm_writer_loop(self):
        """Dedicated RTCM writer thread - handles all serial writes asynchronously"""
        logger.info("RTCM writer thread started")
        
        write_failures = 0
        max_write_failures = 5
        
        while self.running:
            try:
                # Get RTCM data from queue with timeout
                start_time = time.time()
                try:
                    rtcm_data = self.rtcm_write_queue.get(timeout=1.0)
                except queue.Empty:
                    continue
                
                # Validate we have serial connection
                if not self.gps_serial:
                    logger.warning("No GPS serial connection for RTCM write")
                    self.rtcm_write_queue.task_done()
                    continue
                
                # Write RTCM data to serial port
                try:
                    # Thread-safe serial write
                    with self._state_lock:
                        if self.gps_serial and self.gps_serial.is_open:
                            # Check for data before clearing - don't lose NMEA data
                            bytes_waiting = self.gps_serial.in_waiting
                            if bytes_waiting > 0:
                                logger.debug(f"⚠️  {bytes_waiting} bytes in buffer before RTCM write - preserving NMEA data")
                                # Don't clear buffer if data is available - it might be NMEA
                            
                            # Write RTCM data
                            bytes_written = self.gps_serial.write(rtcm_data)
                            self.gps_serial.flush()  # Ensure immediate write
                            
                            # Update statistics
                            self._stats['rtcm_messages_processed'] += 1
                            self._stats['rtcm_bytes_received'] += len(rtcm_data)
                            self._stats['last_rtcm_time'] = time.time()
                            
                            # Track performance
                            write_duration = time.time() - start_time
                            self.performance_monitor.track_operation('rtcm_write', write_duration)
                            self.performance_monitor.track_queue_depth(self.rtcm_write_queue.qsize())
                            
                            write_failures = 0  # Reset failure counter on success
                            
                            logger.info(f"✅ RTCM written: {bytes_written} bytes, queue: {self.rtcm_write_queue.qsize()}, total processed: {self._stats['rtcm_messages_processed']}")
                        
                        else:
                            logger.warning("GPS serial connection closed during RTCM write")
                
                except Exception as write_error:
                    write_failures += 1
                    logger.error(f"Serial write error ({write_failures}/{max_write_failures}): {write_error}")
                    
                    if write_failures >= max_write_failures:
                        logger.error("Too many serial write failures, stopping RTCM writer")
                        break
                
                # Mark task as done
                self.rtcm_write_queue.task_done()
                
            except Exception as e:
                logger.error(f"RTCM writer thread error: {e}")
                time.sleep(0.1)  # Brief pause on error
        
        logger.info("RTCM writer thread stopped")
        
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
            # Don't reset buffer - might destroy valid NMEA data
            # serial_connection.reset_input_buffer()
            
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
        Queue it for asynchronous writing to GPS receiver
        """
        try:
            if not rtcm_data:
                return
                
            # Quick validation using RTCMValidator
            data_type = RTCMValidator.detect_data_type(rtcm_data)
            
            if data_type == 'rtcm':
                # Queue RTCM data for asynchronous writing
                try:
                    start_time = time.time()
                    
                    # Try to add to queue (non-blocking)
                    self.rtcm_write_queue.put_nowait(rtcm_data)
                    
                    # Update statistics
                    self._stats['rtcm_messages_queued'] += 1
                    
                    # Track queue depth for performance monitoring
                    queue_depth = self.rtcm_write_queue.qsize()
                    self.performance_monitor.track_queue_depth(queue_depth)
                    
                    logger.info(f"📡 RTCM queued: {len(rtcm_data)} bytes, queue depth: {queue_depth}, total queued: {self._stats['rtcm_messages_queued']}")
                    
                except queue.Full:
                    # Queue is full - drop oldest message and add new one
                    try:
                        dropped_data = self.rtcm_write_queue.get_nowait()
                        self.rtcm_write_queue.put_nowait(rtcm_data)
                        
                        self._stats['rtcm_queue_overflows'] += 1
                        logger.warning(f"⚠️  RTCM queue overflow: dropped {len(dropped_data)} bytes, added {len(rtcm_data)} bytes")
                        
                    except queue.Empty:
                        # Shouldn't happen, but handle gracefully
                        self.rtcm_write_queue.put_nowait(rtcm_data)
                        logger.debug("RTCM queue was unexpectedly empty during overflow handling")
                
            else:
                logger.warning(f"⚠️  Rejected non-RTCM data from NTRIP: {data_type}")
                
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
        
        # Start RTCM writer thread (always needed if GPS connected)
        if self.gps_serial:
            self.rtcm_writer_thread = threading.Thread(
                target=self._rtcm_writer_loop, 
                daemon=True,
                name="RTCMWriter"
            )
            self.rtcm_writer_thread.start()
            threads_started.append("RTCM writer")
        
        # Start NMEA processing thread
        if self.gps_serial and self.nmea_reader:
            self.nmea_thread = threading.Thread(
                target=self._nmea_loop, 
                daemon=True,
                name="NMEAProcessor"
            )
            self.nmea_thread.start()
            threads_started.append("NMEA processing")
        
        # Start GGA upload thread (only if NTRIP connected)
        if self.ntrip_client and self.ntrip_client.is_connected():
            self.gga_thread = threading.Thread(
                target=self._gga_upload_loop, 
                daemon=True,
                name="GGAUploader"
            )
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
        corruption_count = 0
        last_corruption_log = 0
        loop_iterations = 0
        last_data_check = 0
        
        while self.running and self.nmea_reader:
            try:
                loop_iterations += 1
                
                # Debug: Log periodic status
                if loop_iterations % 100 == 0:  # Every 100 iterations
                    logger.info(f"🔄 NMEA loop status: iterations={loop_iterations}, in_waiting={self.gps_serial.in_waiting if self.gps_serial else 'NO_SERIAL'}")
                
                # Check for serial port availability and data
                if not (self.gps_serial and self.gps_serial.is_open):
                    logger.warning("❌ GPS serial connection lost")
                    consecutive_errors += 1
                    if consecutive_errors >= max_consecutive_errors:
                        logger.error("Lost GPS serial connection. Stopping NMEA loop.")
                        break
                    time.sleep(0.1)
                    continue
                
                # Check for data availability with buffer management
                bytes_waiting = self.gps_serial.in_waiting
                current_time = time.time()
                
                # Buffer overflow protection - clear if too full
                if bytes_waiting > 3000:  # Nearly full buffer
                    logger.warning(f"📊 GPS buffer near capacity: {bytes_waiting} bytes - optimizing...")
                    # Read and process multiple messages quickly to clear buffer
                    for _ in range(20):  # Process up to 20 messages quickly
                        if self.gps_serial.in_waiting < 100:
                            break
                        try:
                            raw_data, parsed_data = self.nmea_reader.read()
                            if raw_data:
                                self._process_nmea_message(raw_data, parsed_data)
                        except Exception:
                            break
                    logger.info(f"📊 Buffer optimized: {self.gps_serial.in_waiting} bytes remaining")
                
                if bytes_waiting > 0:
                    logger.info(f"📥 GPS data available: {bytes_waiting} bytes")
                    last_data_check = current_time
                else:
                    # Log if no data for too long
                    if current_time - last_data_check > 10.0:  # 10 seconds without data
                        logger.warning(f"⚠️  No GPS data for {current_time - last_data_check:.1f}s")
                        last_data_check = current_time
                    
                    time.sleep(0.1)
                    continue

                # Read and process data with corruption detection and synchronization
                try:
                    logger.debug(f"🔄 Reading NMEA data ({bytes_waiting} bytes available)")
                    
                    # Synchronized NMEA reading to prevent interference with RTCM writing
                    with self._state_lock:  # Synchronize with RTCM writing
                        raw_data, parsed_data = self.nmea_reader.read()
                    
                    if raw_data:
                        logger.info(f"📡 NMEA read successful: {len(raw_data)} bytes")
                    
                except Exception as read_error:
                    # Handle corruption at read level
                    corruption_count += 1
                    error_str = str(read_error).lower()
                    
                    if "checksum" in error_str or "format" in error_str or "crc" in error_str:
                        # Expected corruption - don't spam logs
                        current_time = time.time()
                        if current_time - last_corruption_log > 10.0:  # Log every 10 seconds max
                            logger.debug(f"GPS data corruption detected: {read_error} (count: {corruption_count})")
                            last_corruption_log = current_time
                    else:
                        # Unexpected error
                        logger.warning(f"GPS read error: {read_error}")
                        consecutive_errors += 1
                    
                    # Don't clear buffer - might destroy valid NMEA data
                    # if self.gps_serial and self.gps_serial.is_open:
                    #     try:
                    #         # Try to flush input buffer to clear corruption
                    #         self.gps_serial.reset_input_buffer()
                    #         time.sleep(0.1)  # Brief pause to let things settle
                    #     except:
                    #         pass
                    
                    continue
                
                if raw_data and parsed_data:
                    # Additional validation for corrupted data
                    try:
                        raw_str = raw_data.decode('ascii', errors='ignore').strip()
                        
                        # Check for obviously corrupted NMEA
                        if not raw_str.startswith('$') or len(raw_str) < 10:
                            corruption_count += 1
                            logger.debug(f"Corrupted NMEA format detected: {raw_str[:50]}")
                            continue
                        
                        # Check for RTCM contamination (binary data in NMEA stream)
                        if b'\xd3' in raw_data:  # RTCM preamble in NMEA data
                            corruption_count += 1
                            logger.debug("RTCM contamination detected in NMEA stream")
                            # Don't clear buffer - might destroy valid NMEA data
                            # self.gps_serial.reset_input_buffer()
                            time.sleep(0.01)
                            continue
                        
                        # Check for binary characters that shouldn't be in NMEA
                        if any(b < 32 or b > 126 for b in raw_data if b not in [10, 13]):  # Allow CR/LF
                            corruption_count += 1
                            logger.debug("Binary contamination in NMEA data")
                            continue
                        
                        # Check for repeated characters (sign of corruption)
                        if len(set(raw_str)) < len(raw_str) * 0.3:  # Less than 30% unique characters
                            corruption_count += 1
                            logger.debug(f"Suspicious NMEA pattern detected: {raw_str[:50]}")
                            continue
                        
                        # Process valid data
                        logger.info(f"🎯 About to process NMEA message: {len(raw_data)} bytes")
                        self._process_nmea_message(raw_data, parsed_data)
                        consecutive_errors = 0  # Reset on success
                        
                    except UnicodeDecodeError:
                        corruption_count += 1
                        logger.debug("Binary corruption in NMEA data")
                        continue
                        
                else:
                    # This can happen with incomplete messages
                    time.sleep(0.05)
            
            except serial.SerialException as se:
                error_msg = str(se)
                if "device reports readiness to read but returned no data" in error_msg:
                    # Common issue - don't spam logs
                    logger.debug(f"GPS serial timeout: {se}")
                else:
                    logger.error(f"GPS serial error in NMEA loop: {se}")
                    consecutive_errors += 1
                time.sleep(GPS_RECONNECT_INTERVAL)
                
            except Exception as e:
                # Handle checksum and other parsing errors from pynmeagps
                error_str = str(e).lower()
                if "checksum" in error_str or "format" in error_str or "crc" in error_str:
                    self._stats['nmea_errors'] += 1
                    corruption_count += 1
                    
                    # Log periodically to avoid spam
                    if self._stats['nmea_errors'] % 20 == 0:
                        logger.debug(f"NMEA format/checksum error: {e} (total: {self._stats['nmea_errors']})")
                else:
                    logger.warning(f"Unhandled NMEA loop error: {e}")
                    consecutive_errors += 1
                
                time.sleep(0.1)

            # Check for exit condition
            if consecutive_errors >= max_consecutive_errors:
                logger.error("Too many consecutive errors in NMEA loop. Stopping.")
                self.running = False # Signal other threads to stop
                break
                
        logger.info(f"NMEA processing loop ended (checksum errors: {self._stats['nmea_errors']}, corruption events: {corruption_count})")
    
    def _process_nmea_message(self, raw_data, parsed_data):
        """Process NMEA message and extract position data"""
        try:
            # Debug: Log all incoming NMEA messages
            if raw_data:
                raw_str = raw_data.decode('ascii', errors='ignore').strip()
                logger.info(f"📡 NMEA received: {raw_str}")
            
            # Look for GGA sentences (like Waveshare searches for GNGGA)
            if hasattr(parsed_data, 'msgID'):
                # Log all message types to understand what GPS sends
                if not hasattr(self, '_msg_type_counts'):
                    self._msg_type_counts = {}
                
                msg_id = parsed_data.msgID
                self._msg_type_counts[msg_id] = self._msg_type_counts.get(msg_id, 0) + 1
                
                # Log message type counts every 50 messages
                total_messages = sum(self._msg_type_counts.values())
                if total_messages % 50 == 0:
                    logger.info(f"� NMEA message statistics (last 50): {dict(self._msg_type_counts)}")
                
                if parsed_data.msgID in ['GGA']:
                    logger.info("🎯 Processing GGA message")
                    self._process_gga_message(parsed_data)
                elif parsed_data.msgID in ['GLL']:
                    logger.info("🎯 Processing GLL message (position backup)")
                    self._process_gll_message(parsed_data)
                    
                    # Check if we should look for GGA in the same data stream
                    self._check_for_missing_gga()
                elif parsed_data.msgID in ['GSA']:
                    # Extract HDOP and satellite info from GSA messages
                    self._process_gsa_message(parsed_data)
                    logger.debug(f"ℹ️  Processed GSA message for HDOP/satellite data")
                else:
                    logger.debug(f"ℹ️  Skipping non-position message: {parsed_data.msgID}")
            else:
                logger.info("⚠️  NMEA message has no msgID attribute")
                
        except Exception as e:
            logger.warning(f"Error processing NMEA: {e}")
            logger.debug(f"Raw data: {raw_data}")
            logger.debug(f"Parsed data: {parsed_data}")
    
    def _process_gga_message(self, gga_data):
        """Process GGA message and update position with RTK status detection"""
        try:
            logger.info(f"🎯 Processing GGA: {gga_data}")
            
            # Debug: sprawdź co faktycznie zawiera GGA
            logger.debug(f"🔍 GGA Debug - lat='{gga_data.lat}', lon='{gga_data.lon}', quality='{gga_data.quality}', numSV='{gga_data.numSV}'")
            logger.debug(f"🔍 GGA All attributes: {[attr for attr in dir(gga_data) if not attr.startswith('_')]}")
            
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
                    rtk_status = quality_map.get(int(gga_data.quality), f"Unknown ({gga_data.quality})")
                    position_data["rtk_status"] = rtk_status
                    
                    # Special logging for RTK achievements
                    if int(gga_data.quality) == 4:
                        logger.info(f"🎉 RTK FIXED ACHIEVED! Quality=4, HDOP={position_data['hdop']:.1f}")
                    elif int(gga_data.quality) == 5:
                        logger.info(f"🎯 RTK FLOAT ACTIVE! Quality=5, HDOP={position_data['hdop']:.1f}")
                    
                    logger.info(f"📊 GGA Quality Indicator: {gga_data.quality} = {rtk_status}")
                else:
                    position_data["rtk_status"] = "Unknown"
                    logger.warning("⚠️ GGA message missing quality field!")
                
                logger.info(f"📍 Position update (GGA): lat={position_data['lat']:.6f}, lon={position_data['lon']:.6f}, " +
                           f"alt={position_data['altitude']:.1f}m, sats={position_data['satellites']}, " +
                           f"hdop={position_data['hdop']:.1f}, status={position_data['rtk_status']}")
                
                # Update status if changed
                if position_data["rtk_status"] != self.rtk_status:
                    old_status = self.rtk_status
                    self.rtk_status = position_data["rtk_status"]
                    logger.info(f"🔄 RTK Status changed: {old_status} → {self.rtk_status}")
                    
                # Log signal quality warnings
                self._log_signal_quality_warnings(position_data)
                
                # Store current position
                with self._position_lock:
                    self.current_position = position_data
                
                # Call position callback
                if self.position_callback:
                    try:
                        self.position_callback(position_data)
                    except Exception as cb_error:
                        logger.warning(f"Position callback error: {cb_error}")
            else:
                logger.warning("⚠️  GGA message missing lat/lon data")
                logger.debug(f"GGA attributes: {dir(gga_data)}")
                    
        except Exception as e:
            logger.error(f"Error processing GGA: {e}")
            logger.debug(f"GGA data: {gga_data}")
    
    def _process_gll_message(self, gll_data):
        """Process GLL message and update position (backup for GGA)"""
        try:
            logger.info(f"🎯 Processing GLL: {gll_data}")
            
            if hasattr(gll_data, 'lat') and hasattr(gll_data, 'lon'):
                # Extract position data from GLL
                position_data = {
                    "lat": float(gll_data.lat) if gll_data.lat else 0.0,
                    "lon": float(gll_data.lon) if gll_data.lon else 0.0,
                    "altitude": 0.0,  # GLL doesn't contain altitude
                    "satellites": self._get_last_satellite_count(),  # Try to get from recent GSA/GSV
                    "hdop": self._get_last_hdop(),  # Try to get from recent GSA
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")
                }
                
                # GLL status: A = Active (valid), V = Void (invalid)
                if hasattr(gll_data, 'status') and gll_data.status == 'A':
                    # Try to determine better RTK status from HDOP and satellites
                    hdop = position_data.get("hdop", 0.0)
                    satellites = position_data.get("satellites", 0)
                    
                    if hdop > 0 and hdop < 1.0 and satellites >= 12:
                        position_data["rtk_status"] = "RTK Float"  # High precision suggests RTK
                    elif hdop > 0 and hdop < 2.0 and satellites >= 8:
                        position_data["rtk_status"] = "DGPS"  # Good precision
                    else:
                        position_data["rtk_status"] = "No Fix"
                        
                    # Log enhanced RTK detection
                    if hdop <= 0.5:
                        logger.info(f"🎯 EXCELLENT precision detected: HDOP={hdop:.2f}, Sats={satellites}")
                else:
                    position_data["rtk_status"] = "No Fix"
                
                logger.info(f"📍 Position update (GLL): lat={position_data['lat']:.6f}, lon={position_data['lon']:.6f}, " +
                           f"alt={position_data['altitude']:.1f}m, sats={position_data['satellites']}, " +
                           f"hdop={position_data['hdop']:.1f}, status={position_data['rtk_status']}")
                
                # Update status if changed
                if position_data["rtk_status"] != self.rtk_status:
                    old_status = self.rtk_status
                    self.rtk_status = position_data["rtk_status"]
                    logger.info(f"🔄 RTK Status changed: {old_status} → {self.rtk_status}")
                
                # Log signal quality warnings
                self._log_signal_quality_warnings(position_data)
                
                # Store current position
                with self._position_lock:
                    self.current_position = position_data
                
                # Call position callback
                if self.position_callback:
                    try:
                        self.position_callback(position_data)
                    except Exception as cb_error:
                        logger.warning(f"Position callback error: {cb_error}")
            else:
                logger.warning("⚠️  GLL message missing lat/lon data")
                logger.debug(f"GLL attributes: {dir(gll_data)}")
                    
        except Exception as e:
            logger.error(f"Error processing GLL: {e}")
            logger.debug(f"GLL data: {gll_data}")
    
    def _get_last_satellite_count(self):
        """Get satellite count from recent GSA messages"""
        if not hasattr(self, '_last_satellite_count'):
            self._last_satellite_count = 0
        return self._last_satellite_count
    
    def _get_last_hdop(self):
        """Get HDOP from recent GSA messages"""
        if not hasattr(self, '_last_hdop'):
            self._last_hdop = 0.0
        return self._last_hdop
    
    def _process_gsa_message(self, gsa_data):
        """Process GSA message to extract HDOP and satellite count"""
        try:
            # Extract HDOP from GSA
            if hasattr(gsa_data, 'HDOP') and gsa_data.HDOP:
                self._last_hdop = float(gsa_data.HDOP)
                logger.debug(f"📊 Updated HDOP from GSA: {self._last_hdop:.2f}")
            
            # Count active satellites from GSA
            satellite_count = 0
            if hasattr(gsa_data, 'svid_01') and gsa_data.svid_01:
                # GSA contains up to 12 satellite IDs
                for i in range(1, 13):
                    svid_attr = f'svid_{i:02d}'
                    if hasattr(gsa_data, svid_attr):
                        svid = getattr(gsa_data, svid_attr)
                        if svid and svid != '':
                            satellite_count += 1
                
                self._last_satellite_count = satellite_count
                logger.debug(f"📊 Updated satellite count from GSA: {satellite_count}")
            
        except Exception as e:
            logger.debug(f"Error processing GSA: {e}")
    
    def _check_for_missing_gga(self):
        """Check if GPS configuration is missing GGA messages and try to enable them"""
        if not hasattr(self, '_gga_check_time'):
            self._gga_check_time = time.time()
            self._gga_missing_count = 0
            self._gga_config_sent = False
            return
        
        current_time = time.time()
        
        # Check every 15 seconds if GGA is missing (faster than before)
        if current_time - self._gga_check_time > 15:
            self._gga_missing_count += 1
            self._gga_check_time = current_time
            
            # Try to enable GGA after just 30 seconds (2 checks) if not done already
            if self._gga_missing_count >= 2 and not self._gga_config_sent:
                logger.warning("🚨 GGA messages missing for 30+ seconds - attempting to enable GGA")
                logger.info("💡 Currently using GLL as position source, attempting to enable full GGA data")
                
                # Try to manually request GGA configuration
                self._try_enable_gga_messages()
                self._gga_config_sent = True
                
            elif self._gga_missing_count >= 6 and self._gga_config_sent:  # After 90 seconds total
                logger.info("📊 GPS appears to be configured without GGA - continuing with GLL + GSA data")
                logger.info(f"💼 Position source: GLL, Quality data: GSA (HDOP={getattr(self, '_last_hdop', 0.0):.1f}, Sats={getattr(self, '_last_satellite_count', 0)})")
                self._gga_missing_count = 0  # Reset to avoid spam
    
    def _try_enable_gga_messages(self):
        """Try to enable GGA messages via GPS configuration commands"""
        try:
            if self.gps_serial and self.gps_serial.is_open:
                logger.info("🔧 Attempting to enable GGA messages for RTK Fixed status detection...")
                logger.info("💡 GGA Quality Indicator field is essential for RTK Fixed (4) vs Float (5) detection")
                
                # LC29H PQTM commands (Quectel Proprietary Message)
                # These are the correct commands for LC29H GPS module!
                pqtm_commands = [
                    # Enable GGA and VTG
                    b"$PQTMGNSSMSG,1,1,0,0,0,1*29\r\n",  # GGA=1Hz, GLL,GSA,GSV,RMC,VTG=0Hz
                ]
          
                all_commands = pqtm_commands 

                for cmd in all_commands:
                    try:
                        logger.info(f"📤 Sending GPS config: {cmd.decode('ascii', errors='ignore').strip()}")
                        self.gps_serial.write(cmd)
                        self.gps_serial.flush()
                        time.sleep(0.3)  # Give LC29H time to process each command
                    except Exception as cmd_error:
                        logger.debug(f"GPS config command failed: {cmd_error}")
                        continue
                
                time.sleep(3.0)
                logger.info("🔧 GGA enable commands sent - monitoring for GGA messages with RTK Quality Indicator...")
                logger.info("🎯 Looking for GGA field 6: 4=RTK Fixed, 5=RTK Float, 2=DGPS, 1=GPS")
                
        except Exception as e:
            logger.debug(f"Error enabling GGA: {e}")
    
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
            # High HDOP warning with automated recovery
            if hdop > 5.0:
                logger.warning(f"Poor HDOP: {hdop:.1f} (>5.0) - RTK Fixed unlikely. Check antenna position!")
                self._handle_poor_hdop(hdop, position_data)
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
    
    def _handle_poor_hdop(self, hdop, position_data):
        """Handle poor HDOP conditions with automated recovery attempts"""
        satellites = position_data.get("satellites", 0)
        
        # Track poor HDOP events
        if not hasattr(self, '_poor_hdop_count'):
            self._poor_hdop_count = 0
            self._last_hdop_recovery = 0
        
        self._poor_hdop_count += 1
        current_time = time.time()
        
        # Try automated recovery every 60 seconds
        if current_time - self._last_hdop_recovery > 60:
            logger.warning(f"Poor HDOP: {hdop:.1f} (>5.0) - attempting automated recovery...")
            
            # Strategy 1: Don't clear GPS buffer - might destroy valid NMEA data
            # if self.gps_serial and self.gps_serial.is_open:
            #     try:
            #         bytes_in_buffer = self.gps_serial.in_waiting
            #         if bytes_in_buffer > 0:
            #             self.gps_serial.reset_input_buffer()
            #             logger.info(f"🔧 Cleared {bytes_in_buffer} bytes from GPS buffer")
            #     except Exception as e:
            #         logger.debug(f"Failed to clear GPS buffer: {e}")
            
            # Strategy 2: Reset RTCM parser buffer
            if hasattr(self, 'rtcm_parser') and self.rtcm_parser:
                try:
                    self.rtcm_parser.reset()
                    logger.info("🔧 Reset RTCM parser buffer")
                except:
                    pass
            
            # Strategy 3: Log antenna positioning advice
            if satellites < 8:
                logger.warning(f"💡 Poor HDOP + low satellites ({satellites}) suggests antenna obstruction")
                logger.warning("   📡 Move antenna to open sky with clear view of horizon")
            else:
                logger.warning(f"💡 Poor HDOP with good satellites ({satellites}) suggests interference")
                logger.warning("   📡 Check for metal objects, buildings, or electronic interference near antenna")
            
            self._last_hdop_recovery = current_time
        
        # Log persistent issues
        if self._poor_hdop_count % 50 == 0:  # Every 50 poor readings
            logger.error(f"❌ Persistent poor HDOP: {self._poor_hdop_count} consecutive readings > 5.0")
            logger.error("   🔧 Consider: 1) Relocating antenna 2) Checking connections 3) Verifying mount point")
    
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
        threads_to_join = [
            ("NMEA", self.nmea_thread),
            ("GGA", self.gga_thread),
            ("RTCM Writer", self.rtcm_writer_thread)
        ]
        
        for thread_name, thread in threads_to_join:
            if thread and thread.is_alive():
                logger.debug(f"Waiting for {thread_name} thread to stop...")
                thread.join(timeout=2)
                if thread.is_alive():
                    logger.warning(f"{thread_name} thread did not stop gracefully")
                else:
                    logger.debug(f"{thread_name} thread stopped")
        
        # Clear the RTCM queue
        try:
            while not self.rtcm_write_queue.empty():
                self.rtcm_write_queue.get_nowait()
                self.rtcm_write_queue.task_done()
        except queue.Empty:
            pass
        
        self._cleanup_connections()
        
        # Log final statistics
        self._log_final_statistics()
        
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
        """Get RTK system status with enhanced diagnostics and RTCM statistics"""
        status = {
            "rtk_status": self.rtk_status,
            "running": self.running,
            "ntrip_connected": self.ntrip_client and self.ntrip_client.is_connected(),
            "gps_connected": self.gps_serial is not None,
            "current_position": self.current_position
        }
        
        # Add NTRIP client statistics if available
        if self.ntrip_client:
            ntrip_stats = self.ntrip_client.get_statistics()
            status["ntrip_statistics"] = ntrip_stats
            
            # Add RTCM parser statistics for detailed diagnostics
            rtcm_stats = ntrip_stats.get('rtcm_parser', {})
            status["rtcm_messages_parsed"] = rtcm_stats.get('total_parsed', 0)
            status["rtcm_parse_errors"] = rtcm_stats.get('parse_errors', 0)
            status["rtcm_message_types"] = rtcm_stats.get('message_types', {})
        
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
    
    def _log_final_statistics(self):
        """Log comprehensive statistics when system stops"""
        logger.info("📊 RTK SYSTEM FINAL STATISTICS:")
        logger.info(f"   GPS NMEA errors: {self._stats.get('nmea_errors', 0)}")
        logger.info(f"   RTCM messages processed: {self._stats.get('rtcm_messages_processed', 0)}")
        logger.info(f"   RTCM messages queued: {self._stats.get('rtcm_messages_queued', 0)}")
        logger.info(f"   RTCM queue overflows: {self._stats.get('rtcm_queue_overflows', 0)}")
        logger.info(f"   RTCM bytes received: {self._stats.get('rtcm_bytes_received', 0)}")
        
        if hasattr(self, '_poor_hdop_count'):
            logger.info(f"   Poor HDOP events: {self._poor_hdop_count}")
        
        # Performance statistics
        performance_report = self.performance_monitor.get_performance_report()
        if performance_report:
            logger.info("📈 PERFORMANCE METRICS:")
            if 'avg_nmea_latency_ms' in performance_report:
                logger.info(f"   Avg NMEA latency: {performance_report['avg_nmea_latency_ms']:.2f}ms")
            if 'avg_rtcm_latency_ms' in performance_report:
                logger.info(f"   Avg RTCM latency: {performance_report['avg_rtcm_latency_ms']:.2f}ms")
            if 'max_queue_depth' in performance_report:
                logger.info(f"   Max queue depth: {performance_report['max_queue_depth']}")
            if 'corruption_rate' in performance_report:
                logger.info(f"   Corruption rate: {performance_report['corruption_rate']:.4f}")
        
        # NTRIP statistics
        if self.ntrip_client:
            try:
                ntrip_stats = self.ntrip_client.get_statistics()
                if ntrip_stats:
                    logger.info(f"   NTRIP bytes received: {ntrip_stats.get('bytes_received', 0)}")
                    logger.info(f"   NTRIP connection uptime: {ntrip_stats.get('uptime', 0):.1f}s")
            except:
                logger.info("   NTRIP statistics unavailable")
                
        # Current status
        if self.current_position:
            pos = self.current_position
            logger.info(f"   Final RTK status: {pos.get('rtk_status', 'Unknown')}")
            logger.info(f"   Final HDOP: {pos.get('hdop', 0):.1f}")
            logger.info(f"   Final satellites: {pos.get('satellites', 0)}")
        else:
            logger.info("   No position data received")
