"""
NMEA Parser for LC29H(DA) GPS/RTK module
Parses GGA, RMC sentences and extracts position data
"""

import json
import os
from datetime import datetime
from dataclasses import dataclass
from typing import Optional, Dict, Any
import pynmea2
import logging

logger = logging.getLogger(__name__)

@dataclass
class GPSPosition:
    """GPS position data structure"""
    timestamp: str
    lat: float
    lon: float
    altitude: float
    fix_quality: int
    satellites: int
    hdop: float
    speed_knots: Optional[float] = None
    heading: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "timestamp": self.timestamp,
            "lat": self.lat,
            "lon": self.lon,
            "altitude": self.altitude,
            "fix_quality": self.fix_quality,
            "satellites": self.satellites,
            "hdop": self.hdop,
            "speed_knots": self.speed_knots,
            "heading": self.heading
        }
    
    @property
    def rtk_status(self) -> str:
        """Get RTK status string from fix quality"""
        quality_map = {
            0: "No Fix",
            1: "Single",
            2: "DGPS",
            4: "RTK Fixed", 
            5: "RTK Float"
        }
        return quality_map.get(self.fix_quality, f"Unknown ({self.fix_quality})")

class NMEAParser:
    """Parser for NMEA sentences from LC29H(DA)"""
    
    def __init__(self, log_directory="logs"):
        self.log_directory = log_directory
        self.current_position = None
        self.session_id = None
        self.track_data = {"session_id": "", "points": []}
        
        # Ensure log directory exists
        os.makedirs(self.log_directory, exist_ok=True)
        
        # Start new session
        self._start_new_session()
    
    def _start_new_session(self):
        """Start new tracking session"""
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.track_data = {
            "session_id": self.session_id,
            "points": []
        }
        logger.info(f"Started new GPS session: {self.session_id}")
    
    def parse_sentence(self, sentence: str) -> Optional[GPSPosition]:
        """Parse NMEA sentence and return GPS position if available"""
        try:
            # Parse NMEA sentence
            msg = pynmea2.parse(sentence)
            
            # Handle GGA sentences (position + quality)
            if isinstance(msg, pynmea2.GGA):
                return self._parse_gga(msg)
            
            # Handle RMC sentences (position + speed + heading)  
            elif isinstance(msg, pynmea2.RMC):
                return self._parse_rmc(msg)
            
            return None
            
        except pynmea2.ParseError as e:
            logger.debug(f"Failed to parse NMEA sentence: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error parsing NMEA: {e}")
            return None
    
    def _parse_gga(self, gga: pynmea2.GGA) -> Optional[GPSPosition]:
        """Parse GGA sentence"""
        if not gga.latitude or not gga.longitude:
            return None
        
        try:
            position = GPSPosition(
                timestamp=datetime.utcnow().isoformat() + "Z",
                lat=float(gga.latitude),
                lon=float(gga.longitude),
                altitude=float(gga.altitude) if gga.altitude else 0.0,
                fix_quality=int(gga.gps_qual) if gga.gps_qual else 0,
                satellites=int(gga.num_sats) if gga.num_sats else 0,
                hdop=float(gga.horizontal_dil) if gga.horizontal_dil else 0.0
            )
            
            self.current_position = position
            logger.debug(f"Parsed GGA: {position.rtk_status}, Sats: {position.satellites}")
            
            return position
            
        except (ValueError, TypeError) as e:
            logger.error(f"Error parsing GGA values: {e}")
            return None
    
    def _parse_rmc(self, rmc: pynmea2.RMC) -> Optional[GPSPosition]:
        """Parse RMC sentence and update current position with speed/heading"""
        if not rmc.latitude or not rmc.longitude:
            return None
            
        try:
            # Create position from RMC or update existing
            if self.current_position:
                # Update existing position with speed/heading
                self.current_position.speed_knots = float(rmc.spd_over_grnd) if rmc.spd_over_grnd else None
                self.current_position.heading = float(rmc.true_course) if rmc.true_course else None
                return self.current_position
            else:
                # Create new position from RMC
                position = GPSPosition(
                    timestamp=datetime.utcnow().isoformat() + "Z",
                    lat=float(rmc.latitude),
                    lon=float(rmc.longitude),
                    altitude=0.0,  # RMC doesn't have altitude
                    fix_quality=1 if rmc.status == 'A' else 0,  # A=Active, V=Void
                    satellites=0,   # RMC doesn't have satellite count
                    hdop=0.0,      # RMC doesn't have HDOP
                    speed_knots=float(rmc.spd_over_grnd) if rmc.spd_over_grnd else None,
                    heading=float(rmc.true_course) if rmc.true_course else None
                )
                
                self.current_position = position
                return position
                
        except (ValueError, TypeError) as e:
            logger.error(f"Error parsing RMC values: {e}")
            return None
    
    def log_position(self, position: GPSPosition) -> bool:
        """Log position to track file"""
        try:
            # Add to track data
            self.track_data["points"].append(position.to_dict())
            
            # Write to file
            track_filename = f"track_{datetime.now().strftime('%Y%m%d')}.json"
            track_filepath = os.path.join(self.log_directory, track_filename)
            
            with open(track_filepath, 'w') as f:
                json.dump(self.track_data, f, indent=2)
            
            logger.debug(f"Logged position to {track_filepath}")
            return True
            
        except Exception as e:
            logger.error(f"Error logging position: {e}")
            return False
    
    def get_current_position(self) -> Optional[GPSPosition]:
        """Get current GPS position"""
        return self.current_position
    
    def get_track_data(self) -> Dict[str, Any]:
        """Get current track data"""
        return self.track_data.copy()
    
    def get_rtk_status(self) -> str:
        """Get current RTK status"""
        if self.current_position:
            return self.current_position.rtk_status
        return "No Fix"

# Test function
def test_parser():
    """Test NMEA parser with sample data"""
    parser = NMEAParser(log_directory="test_logs")
    
    # Sample NMEA sentences
    sample_sentences = [
        "$GNGGA,143022.00,5224.3841,N,01655.5120,E,4,12,0.8,85.4,M,44.7,M,1.0,0000*5F",
        "$GNRMC,143022.00,A,5224.3841,N,01655.5120,E,0.05,125.29,060825,,,D*7E",
        "$GNGGA,143023.00,5224.3842,N,01655.5121,E,4,12,0.8,85.5,M,44.7,M,1.0,0000*5C",
    ]
    
    print("Testing NMEA Parser:")
    print("=" * 40)
    
    for sentence in sample_sentences:
        print(f"Input: {sentence}")
        
        position = parser.parse_sentence(sentence)
        if position:
            print(f"Parsed: {position.rtk_status} at {position.lat:.6f}, {position.lon:.6f}")
            parser.log_position(position)
        else:
            print("No position extracted")
        print()
    
    print(f"Current RTK Status: {parser.get_rtk_status()}")
    print(f"Total points logged: {len(parser.get_track_data()['points'])}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    test_parser()
