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
        for baudrate in self.BAUDRATES:
            if self._try_connect(baudrate):
                self._configure_lc29h()
                return True
        return False
    
    def _try_connect(self, baudrate: int) -> bool:
        try:
            test_serial = serial.Serial(port=self.port, baudrate=baudrate, timeout=2.0)
            if self._test_communication(test_serial):
                self.serial_conn = test_serial
                self.nmea_reader = NMEAReader(test_serial)
                logger.info(f"GPS connected at {baudrate} baud")
                return True
            test_serial.close()
        except Exception as e:
            logger.debug(f"Failed at {baudrate}: {e}")
        return False
    
    def _test_communication(self, conn: serial.Serial) -> bool:
        start_time = time.time()
        while time.time() - start_time < 3.0:
            if conn.in_waiting > 0:
                data = conn.read(conn.in_waiting)
                if b'$' in data and b'*' in data:
                    return True
            time.sleep(0.1)
        return False
    
    def _configure_lc29h(self):
        if not self.serial_conn:
            return
            
        commands = [self.PQTM_DISABLE_ALL, self.PQTM_ENABLE_GGA, self.PQTM_SAVE]
        for cmd in commands:
            self.serial_conn.write(cmd)
            self.serial_conn.flush()
            time.sleep(1.0)
        logger.info("LC29H configured for GGA-only output")
    
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
            
        if nmea_msg.msgID == 'GGA':
            self._last_gga_time = time.time()
            return self._parse_gga(nmea_msg)
        elif nmea_msg.msgID == 'GLL' and time.time() - self._last_gga_time > 5.0:
            return self._parse_gll(nmea_msg)
        return None
    
    def _parse_gga(self, gga: NMEAMessage) -> Optional[Position]:
        if not (hasattr(gga, 'lat') and hasattr(gga, 'lon')):
            return None
            
        quality_map = {
            0: RTKStatus.NO_FIX,
            1: RTKStatus.SINGLE,
            2: RTKStatus.DGPS,
            4: RTKStatus.RTK_FIXED,
            5: RTKStatus.RTK_FLOAT
        }
        
        return Position(
            lat=float(gga.lat) if gga.lat else 0.0,
            lon=float(gga.lon) if gga.lon else 0.0,
            altitude=float(gga.alt) if hasattr(gga, 'alt') and gga.alt else 0.0,
            satellites=int(gga.numSV) if hasattr(gga, 'numSV') and gga.numSV else 0,
            hdop=float(gga.HDOP) if hasattr(gga, 'HDOP') and gga.HDOP else 0.0,
            rtk_status=quality_map.get(int(gga.quality), RTKStatus.NO_FIX),
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ")
        )
    
    def _parse_gll(self, gll: NMEAMessage) -> Optional[Position]:
        if not (hasattr(gll, 'lat') and hasattr(gll, 'lon')):
            return None
            
        return Position(
            lat=float(gll.lat) if gll.lat else 0.0,
            lon=float(gll.lon) if gll.lon else 0.0,
            altitude=0.0,
            satellites=0,
            hdop=0.0,
            rtk_status=RTKStatus.SINGLE if hasattr(gll, 'status') and gll.status == 'A' else RTKStatus.NO_FIX,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ")
        )
    
    def write_rtcm(self, data: bytes) -> bool:
        if self.serial_conn:
            try:
                self.serial_conn.write(data)
                return True
            except Exception as e:
                logger.error(f"RTCM write failed: {e}")
        return False
    
    def close(self):
        if self.serial_conn:
            self.serial_conn.close()
            self.serial_conn = None
            self.nmea_reader = None
