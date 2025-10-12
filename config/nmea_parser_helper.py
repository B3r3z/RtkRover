"""
NMEA Parser Extension - Helper for extracting heading and speed
Used to extend Position data with navigation information
"""
import logging
from typing import Optional, Tuple
from pynmeagps import NMEAMessage

logger = logging.getLogger(__name__)


class NMEANavigationParser:
    """
    Helper class for parsing heading and speed from NMEA messages
    Supports RMC (Recommended Minimum) and VTG (Track Made Good) messages
    """
    
    @staticmethod
    def parse_rmc_navigation(rmc: NMEAMessage) -> Tuple[Optional[float], Optional[float]]:
        """
        Parse speed and course from RMC message
        
        RMC format includes:
        - spd: Speed over ground (knots)
        - cog: Course over ground (degrees, 0-360)
        
        Args:
            rmc: Parsed RMC NMEA message
            
        Returns:
            Tuple of (speed_knots, heading_degrees) or (None, None)
        """
        speed = None
        heading = None
        
        try:
            # Parse speed (in knots)
            if hasattr(rmc, 'spd') and rmc.spd is not None and rmc.spd != '':
                try:
                    speed = float(rmc.spd)
                    # Validate speed (0-200 knots is reasonable for ground vehicles)
                    if not 0.0 <= speed <= 200.0:
                        logger.debug(f"RMC: Speed {speed} out of range, ignoring")
                        speed = None
                except (ValueError, TypeError):
                    logger.debug(f"RMC: Invalid speed format: {rmc.spd}")
            
            # Parse course over ground (heading)
            if hasattr(rmc, 'cog') and rmc.cog is not None and rmc.cog != '':
                try:
                    heading = float(rmc.cog)
                    # Validate heading (0-360 degrees)
                    if not 0.0 <= heading <= 360.0:
                        logger.debug(f"RMC: Heading {heading} out of range, ignoring")
                        heading = None
                except (ValueError, TypeError):
                    logger.debug(f"RMC: Invalid heading format: {rmc.cog}")
            
            return speed, heading
            
        except Exception as e:
            logger.debug(f"Error parsing RMC navigation data: {e}")
            return None, None
    
    @staticmethod
    def parse_vtg_navigation(vtg: NMEAMessage) -> Tuple[Optional[float], Optional[float]]:
        """
        Parse speed and course from VTG message
        
        VTG format includes:
        - cogt: Course over ground (true, degrees)
        - sogk: Speed over ground (knots)
        
        Args:
            vtg: Parsed VTG NMEA message
            
        Returns:
            Tuple of (speed_knots, heading_degrees) or (None, None)
        """
        speed = None
        heading = None
        
        try:
            # Parse speed (in knots)
            if hasattr(vtg, 'sogk') and vtg.sogk is not None and vtg.sogk != '':
                try:
                    speed = float(vtg.sogk)
                    if not 0.0 <= speed <= 200.0:
                        logger.debug(f"VTG: Speed {speed} out of range, ignoring")
                        speed = None
                except (ValueError, TypeError):
                    logger.debug(f"VTG: Invalid speed format: {vtg.sogk}")
            
            # Parse course over ground (true heading)
            if hasattr(vtg, 'cogt') and vtg.cogt is not None and vtg.cogt != '':
                try:
                    heading = float(vtg.cogt)
                    if not 0.0 <= heading <= 360.0:
                        logger.debug(f"VTG: Heading {heading} out of range, ignoring")
                        heading = None
                except (ValueError, TypeError):
                    logger.debug(f"VTG: Invalid heading format: {vtg.cogt}")
            
            return speed, heading
            
        except Exception as e:
            logger.debug(f"Error parsing VTG navigation data: {e}")
            return None, None
    
    @staticmethod
    def convert_knots_to_mps(knots: Optional[float]) -> Optional[float]:
        """
        Convert speed from knots to meters per second
        
        Args:
            knots: Speed in knots
            
        Returns:
            Speed in m/s or None
        """
        if knots is None:
            return None
        return knots * 0.514444  # 1 knot = 0.514444 m/s
    
    @staticmethod
    def is_moving(speed_knots: Optional[float], threshold: float = 0.1) -> bool:
        """
        Determine if vehicle is moving based on speed
        
        Args:
            speed_knots: Speed in knots
            threshold: Minimum speed to consider as moving (knots)
            
        Returns:
            True if speed exceeds threshold
        """
        if speed_knots is None:
            return False
        return speed_knots > threshold


# Example usage in GPS adapter:
"""
from config.nmea_parser_helper import NMEANavigationParser

# In your GPS adapter class:
def _parse_rmc(self, rmc: NMEAMessage) -> Optional[Position]:
    # Parse position from RMC (if available)
    # ...
    
    # Add navigation data
    speed, heading = NMEANavigationParser.parse_rmc_navigation(rmc)
    
    position = Position(
        lat=lat,
        lon=lon,
        altitude=altitude,
        satellites=satellites,
        hdop=hdop,
        rtk_status=rtk_status,
        timestamp=timestamp,
        speed=speed,        # NEW
        heading=heading     # NEW
    )
    return position
"""
