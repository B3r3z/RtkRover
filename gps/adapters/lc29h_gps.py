import serial
import time
import logging
import struct
from typing import Optional
from pynmeagps import NMEAReader, NMEAMessage
from ..core.interfaces import GPS, Position, RTKStatus

logger = logging.getLogger(__name__)

class LC29HGPS(GPS):
    BAUDRATES = [115200, 38400, 9600]
    
    def __init__(self, port: str):
        self.port = port
        self.serial_conn: Optional[serial.Serial] = None
        self.nmea_reader: Optional[NMEAReader] = None
        self._last_gga_time = 0
        
        self._last_position_log = 0
        self._last_rtcm_log = 0
        self._position_log_interval = 10.0  
        self._rtcm_log_interval = 5.0      
        self._rtcm_message_count = 0
        self._last_rtk_status = None
        
    def connect(self) -> bool:
        logger.info(f"🔌 Connecting to LC29H GPS on {self.port}")
        for baudrate in self.BAUDRATES:
            logger.debug(f"🔌 Trying connection at {baudrate} baud...")
            if self._try_connect(baudrate):
                self._configure_lc29h()
                return True
        logger.error(f"❌ Failed to connect to GPS on {self.port}")
        return False
    
    def _try_connect(self, baudrate: int) -> bool:
        try:
            test_serial = serial.Serial(port=self.port, baudrate=baudrate, timeout=2.0)
            if self._test_communication(test_serial):
                self.serial_conn = test_serial
                self.nmea_reader = NMEAReader(test_serial)
                logger.info(f"✅ GPS connected at {baudrate} baud")
                return True
            test_serial.close()
        except Exception as e:
            logger.debug(f"Failed at {baudrate}: {e}")
        return False
    
    def _test_communication(self, conn: serial.Serial) -> bool:
        logger.debug("🔍 Testing GPS communication...")
        start_time = time.time()
        while time.time() - start_time < 3.0:
            if conn.in_waiting > 0:
                data = conn.read(conn.in_waiting)
                if b'$' in data and b'*' in data:
                  #  logger.debug(f"📡 GPS communication OK - received NMEA data")
                    return True
            time.sleep(0.1)
        logger.debug("❌ No valid NMEA data received")
        return False
    
    def _configure_lc29h(self):
        if not self.serial_conn:
            return
        logger.info("🔧 Configuring LC29H with PAIR062 commands (enable GGA only)...")

        # Clear buffer first
        if self.serial_conn.in_waiting:
            self.serial_conn.read(self.serial_conn.in_waiting)

        # Configuration commands sequence: (command_bytes, description)
        configuration_commands = [
            (b"$PAIR062,0,1*3E\r\n", "Enable GGA 1Hz"),
         #   (b"$PAIR062,1,0*3F\r\n", "Disable GLL"),
          #  (b"$PAIR062,2,0*3C\r\n", "Disable GSA"),
           # (b"$PAIR062,3,0*3D\r\n", "Disable GSV"),
            (b"$PAIR062,4,0*3A\r\n", "Disable RMC"),
            (b"$PAIR062,5,0*3B\r\n", "Disable VTG"),
        ]

        for cmd, desc in configuration_commands:
            self._send_nmea_command(cmd, desc)

        logger.info("✅ Configuration commands sent successfully.")

    def _send_nmea_command(self, cmd: bytes, desc: str, wait: float = 0.25):
        """Send a single NMEA configuration command with optional short wait.
        Args:
            cmd: Full command bytes including CRLF.
            desc: Human readable description for logs.
            wait: Seconds to wait after sending to allow device processing.
        """
        if not self.serial_conn:
            return False
        try:
            self.serial_conn.write(cmd)
            self.serial_conn.flush()
            time.sleep(wait)
            logger.debug(f"➡️ Sent {desc}: {cmd.decode(errors='ignore').strip()}")
            # Drain any immediate echo/ack
            if self.serial_conn.in_waiting:
                echo = self.serial_conn.read(self.serial_conn.in_waiting)
                if echo:
                    logger.debug(f"⬅️ Echo/Resp ({desc}): {echo.decode(errors='ignore').strip()}")
            return True
        except Exception as e:
            logger.warning(f"⚠️ Failed sending {desc}: {e}")
            return False
    
    def read_position(self) -> Optional[Position]:
        if not self.nmea_reader or not self.serial_conn:
            return None
            
        try:
            raw_data, parsed_data = self.nmea_reader.read()
            if raw_data and parsed_data:
                return self._parse_position(parsed_data)
        except Exception as e:
            logger.debug(f"Read error: {e}")
        return None
    
    def _parse_position(self, nmea_msg: NMEAMessage) -> Optional[Position]:
        if not hasattr(nmea_msg, 'msgID'):
            return None
            
        msg_type = nmea_msg.msgID
        
        # Only process important messages
        if msg_type == 'GGA':
            self._last_gga_time = time.time()
            return self._parse_gga(nmea_msg)
        elif msg_type == 'GLL':
            # Only use GLL as fallback if no recent GGA
            if time.time() - self._last_gga_time > 5.0:
                logger.debug(f"📡 Using GLL fallback (no GGA for {time.time() - self._last_gga_time:.1f}s)")
                return self._parse_gll(nmea_msg)
        elif msg_type in ['GSA', 'GSV', 'RMC', 'VTG']:
            # Common NMEA messages - silently ignore
            pass
        else:
            # Log unknown messages occasionally
            logger.debug(f"📡 Unknown NMEA message type: {msg_type}")
        return None
    
    def _parse_gga(self, gga: NMEAMessage) -> Optional[Position]:
        try:
            # Basic structure validation
            if not hasattr(gga, 'lat') or not hasattr(gga, 'lon'):
                logger.warning("📡 GGA message missing lat/lon attributes")
                return None
            
            # Check if position data is available (not None/empty)
            if gga.lat is None or gga.lon is None or gga.lat == '' or gga.lon == '':
                logger.debug("📡 GGA message has empty lat/lon data")
                return None
            
            # Parse and validate coordinates
            try:
                lat = float(gga.lat)
                lon = float(gga.lon)
                
            except (ValueError, TypeError) as e:
                logger.warning(f"📡 GGA: Invalid lat/lon format - lat={gga.lat}, lon={gga.lon}: {e}")
                return None
            
            # Validate coordinate ranges
            if not (-90.0 <= lat <= 90.0):
                logger.warning(f"📡 GGA: Invalid latitude {lat} (must be -90 to 90)")
                return None
            
            if not (-180.0 <= lon <= 180.0):
                logger.warning(f"📡 GGA: Invalid longitude {lon} (must be -180 to 180)")
                return None
            
            # Parse altitude with validation
            altitude = 0.0
            if hasattr(gga, 'alt') and gga.alt is not None and gga.alt != '':
                try:
                    altitude = float(gga.alt)
                    # Sanity check for altitude (-1000m to 10000m)
                    if not (-1000.0 <= altitude <= 10000.0):
                        logger.warning(f"📡 GGA: Suspicious altitude {altitude}m")
                except (ValueError, TypeError):
                    logger.warning(f"📡 GGA: Invalid altitude format: {gga.alt}")
            
            # Parse satellites count with validation
            satellites = 0
            if hasattr(gga, 'numSV') and gga.numSV is not None and gga.numSV != '':
                try:
                    satellites = int(gga.numSV)
                    # Validate satellite count (0-50 is reasonable range)
                    if not (0 <= satellites <= 50):
                        logger.warning(f"📡 GGA: Suspicious satellite count {satellites}")
                        satellites = max(0, min(50, satellites))  # Clamp to valid range
                except (ValueError, TypeError):
                    logger.warning(f"📡 GGA: Invalid satellite count format: {gga.numSV}")
            
            # Parse HDOP with validation
            hdop = 0.0
            if hasattr(gga, 'HDOP') and gga.HDOP is not None and gga.HDOP != '':
                try:
                    hdop = float(gga.HDOP)
                    # Validate HDOP (0-50 is reasonable range)
                    if not (0.0 <= hdop <= 50.0):
                        logger.warning(f"📡 GGA: Suspicious HDOP {hdop}")
                        hdop = max(0.0, min(50.0, hdop))  # Clamp to valid range
                except (ValueError, TypeError):
                    logger.warning(f"📡 GGA: Invalid HDOP format: {gga.HDOP}")
            
            # Parse quality indicator with validation
            quality = 0
            if hasattr(gga, 'quality') and gga.quality is not None and gga.quality != '':
                try:
                    quality = int(gga.quality)
                    # Validate quality range (0-9 according to NMEA spec)
                    if not (0 <= quality <= 9):
                        logger.warning(f"📡 GGA: Invalid quality indicator {quality}")
                        quality = 0
                except (ValueError, TypeError):
                    logger.warning(f"📡 GGA: Invalid quality format: {gga.quality}")
            
            # Map quality to RTK status
            quality_map = {
                0: RTKStatus.NO_FIX,        # No fix
                1: RTKStatus.SINGLE,        # GPS fix (SPS)
                2: RTKStatus.DGPS,          # DGPS fix
                3: RTKStatus.SINGLE,        # PPS fix (treat as single)
                4: RTKStatus.RTK_FIXED,     # RTK fixed
                5: RTKStatus.RTK_FLOAT,     # RTK float
            }
            
            rtk_status = quality_map.get(quality, RTKStatus.NO_FIX)
            
            # Get diffAge for logging if available
            diff_age = getattr(gga, 'diffAge', 'N/A')
            current_time = time.time()
            status_changed = self._last_rtk_status != rtk_status
            should_log_position = (current_time - self._last_position_log >= self._position_log_interval) or status_changed
            
            if should_log_position:
                if quality == 4:  # RTK Fixed - special success logging
                    logger.info(f"🎯 RTK FIXED! Lat={lat:.6f}, Lon={lon:.6f}, Alt={altitude:.1f}m, "
                               f"Sats={satellites}, HDOP={hdop:.1f}, DiffAge={diff_age}s")
                elif quality == 5:  # RTK Float
                    logger.info(f"🔶 RTK FLOAT: Lat={lat:.6f}, Lon={lon:.6f}, Alt={altitude:.1f}m, "
                               f"Sats={satellites}, HDOP={hdop:.1f}, DiffAge={diff_age}s")
                else:
                    logger.info(f"📍 GGA: Lat={lat:.6f}, Lon={lon:.6f}, Alt={altitude:.1f}m, "
                               f"Sats={satellites}, HDOP={hdop:.1f}, Quality={quality}({rtk_status.value})")
                
                self._last_position_log = current_time
                self._last_rtk_status = rtk_status
            if quality == 0:
                logger.debug("📡 GGA: No fix available")
            elif satellites < 4 and quality > 0:
                logger.warning(f"📡 GGA: Fix claimed with insufficient satellites ({satellites})")
            
            return Position(
                lat=lat,
                lon=lon,
                altitude=altitude,
                satellites=satellites,
                hdop=hdop,
                rtk_status=rtk_status,
                timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ")
            )
            
        except Exception as e:
            logger.error(f"📡 GGA parsing error: {e}", exc_info=True)
            return None
    
    def _parse_gll(self, gll: NMEAMessage) -> Optional[Position]:
        # Log ALL GLL attributes for detailed debugging
        gll_attrs = {}
        for attr in dir(gll):
            if not attr.startswith('_') and hasattr(gll, attr):
                try:
                    value = getattr(gll, attr)
                    if not callable(value):
                        gll_attrs[attr] = value
                except:
                    pass
        
        logger.info(f"🔍 GLL DETAILED: {gll_attrs}")
        
        if not (hasattr(gll, 'lat') and hasattr(gll, 'lon')):
            logger.warning("📡 GLL message missing lat/lon data")
            return None
        
        # Parse coordinates (pynmeagps already returns decimal degrees)
        lat = float(gll.lat) if gll.lat else 0.0
        lon = float(gll.lon) if gll.lon else 0.0
        status = gll.status if hasattr(gll, 'status') else 'V'
        rtk_status = RTKStatus.SINGLE if status == 'A' else RTKStatus.NO_FIX
        
        logger.info(f"📍 GLL: Lat={lat:.6f}, Lon={lon:.6f}, Status={status}({rtk_status.value}) [FALLBACK]")
            
        return Position(
            lat=lat,
            lon=lon,
            altitude=0.0,
            satellites=0,
            hdop=0.0,
            rtk_status=rtk_status,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ")
        )
    
    def write_rtcm(self, data: bytes) -> bool:
        if self.serial_conn:
            try:
                if len(data) > 0:
                    # Optimized RTCM parsing with throttled logging
                    self._rtcm_message_count += 1
                    current_time = time.time()
                    
                    if data[0] == 0xD3:
                        if len(data) >= 6:
                            try:
                                header = struct.unpack('>I', b'\x00' + data[0:3])[0]
                                length = header & 0x3FF
                                if len(data) >= 5:  # Header + at least 2 bytes for message type
                                    msg_type = struct.unpack('>H', data[3:5])[0] >> 4
                      
                            except Exception as e:
                                logger.debug(f"Could not extract RTCM message details: {e}")
                        
                        # Write data to GPS - this is the critical part
                        bytes_written = self.serial_conn.write(data)
                       # logger.info(f"📡 RTCM: Sending {len(data)} bytes to GPS: {data[:20].hex()}...")
                        return bytes_written == len(data)
                    else:
                        logger.warning(f"⚠️ RTCM: Invalid preamble 0x{data[0]:02X} (expected 0xD3)")
                
                self.serial_conn.write(data)
                return True
            except Exception as e:
                logger.error(f"❌ RTCM write failed: {e}")
        else:
            logger.warning("⚠️ Cannot write RTCM - GPS not connected")
        return False
    
    def close(self):
        if self.serial_conn:
            logger.info("🔌 Closing GPS connection")
            self.serial_conn.close()
            self.serial_conn = None
            self.nmea_reader = None
        else:
            logger.debug("GPS connection already closed")
    
    def is_connected(self) -> bool:
        return self.serial_conn is not None and not self.serial_conn.closed
