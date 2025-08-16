import serial
import time
import logging
from typing import Optional
from pynmeagps import NMEAReader, NMEAMessage
from ..core.interfaces import GPS, Position, RTKStatus

logger = logging.getLogger(__name__)

class LC29HGPS(GPS):
    BAUDRATES = [115200, 38400, 9600]
    PQTM_DISABLE_ALL = b"$PQTMGNSSMSG,0,0,0,0,0,0*2A\r\n"
    PQTM_ENABLE_GGA = b"$PQTMGNSSMSG,1,0,0,0,0,0*2B\r\n"
    PQTM_SAVE = b"$PQTMSAVEPAR*53\r\n"
    
    def __init__(self, port: str):
        self.port = port
        self.serial_conn: Optional[serial.Serial] = None
        self.nmea_reader: Optional[NMEAReader] = None
        self._last_gga_time = 0
        
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
                    logger.debug(f"📡 GPS communication OK - received NMEA data")
                    return True
            time.sleep(0.1)
        logger.debug("❌ No valid NMEA data received")
        return False
    
    def _configure_lc29h(self):
        if not self.serial_conn:
            return
            
        logger.info("🔧 Configuring LC29H with PQTM commands...")
        commands = [
            (self.PQTM_DISABLE_ALL, "Disabling all NMEA messages"),
            (self.PQTM_ENABLE_GGA, "Enabling GGA messages only"), 
            (self.PQTM_SAVE, "Saving configuration to flash")
        ]
        
        for cmd, description in commands:
            logger.debug(f"🔧 {description}: {cmd.decode('ascii').strip()}")
            self.serial_conn.write(cmd)
            self.serial_conn.flush()
            time.sleep(1.0)
        logger.info("✅ LC29H configured for GGA-only output")
    
    def read_position(self) -> Optional[Position]:
        if not self.nmea_reader or not self.serial_conn:
            return None
            
        try:
            raw_data, parsed_data = self.nmea_reader.read()
            if raw_data and parsed_data:
                # Log raw NMEA sentence
                raw_sentence = raw_data.decode('ascii', errors='ignore').strip()
                logger.debug(f"📡 Raw NMEA: {raw_sentence}")
                return self._parse_position(parsed_data)
        except Exception as e:
            logger.debug(f"Read error: {e}")
        return None
    
    def _parse_position(self, nmea_msg: NMEAMessage) -> Optional[Position]:
        if not hasattr(nmea_msg, 'msgID'):
            logger.debug("📡 Received NMEA message without msgID")
            return None
            
        msg_type = nmea_msg.msgID
        logger.debug(f"📡 Processing NMEA message: {msg_type}")
        
        if msg_type == 'GGA':
            self._last_gga_time = time.time()
            return self._parse_gga(nmea_msg)
        elif msg_type == 'GLL' and time.time() - self._last_gga_time > 5.0:
            logger.debug(f"📡 Using GLL fallback (no GGA for {time.time() - self._last_gga_time:.1f}s)")
            return self._parse_gll(nmea_msg)
        elif msg_type in ['GSA', 'GSV', 'RMC', 'VTG']:
            logger.debug(f"📡 Ignoring {msg_type} message (not used for positioning)")
        else:
            logger.debug(f"📡 Unknown NMEA message type: {msg_type}")
        return None
    
    def _parse_gga(self, gga: NMEAMessage) -> Optional[Position]:
        if not (hasattr(gga, 'lat') and hasattr(gga, 'lon')):
            logger.warning("📡 GGA message missing lat/lon data")
            return None
            
        # Extract all GGA fields for logging
        lat = float(gga.lat) if gga.lat else 0.0
        lon = float(gga.lon) if gga.lon else 0.0
        altitude = float(gga.alt) if hasattr(gga, 'alt') and gga.alt else 0.0
        satellites = int(gga.numSV) if hasattr(gga, 'numSV') and gga.numSV else 0
        hdop = float(gga.HDOP) if hasattr(gga, 'HDOP') and gga.HDOP else 0.0
        quality = int(gga.quality) if hasattr(gga, 'quality') else 0
        
        quality_map = {
            0: RTKStatus.NO_FIX,
            1: RTKStatus.SINGLE,
            2: RTKStatus.DGPS,
            4: RTKStatus.RTK_FIXED,
            5: RTKStatus.RTK_FLOAT
        }
        
        rtk_status = quality_map.get(quality, RTKStatus.NO_FIX)
        
        # Log detailed GGA information
        logger.info(f"📍 GGA: Lat={lat:.6f}, Lon={lon:.6f}, Alt={altitude:.1f}m, "
                   f"Sats={satellites}, HDOP={hdop:.1f}, Quality={quality}({rtk_status.value})")
        
        return Position(
            lat=lat,
            lon=lon,
            altitude=altitude,
            satellites=satellites,
            hdop=hdop,
            rtk_status=rtk_status,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ")
        )
    
    def _parse_gll(self, gll: NMEAMessage) -> Optional[Position]:
        if not (hasattr(gll, 'lat') and hasattr(gll, 'lon')):
            logger.warning("📡 GLL message missing lat/lon data")
            return None
        
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
                bytes_written = len(data)
                self.serial_conn.write(data)
                logger.debug(f"📡 RTCM: Sent {bytes_written} bytes to GPS")
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
