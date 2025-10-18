"""
NMEA Parser Extension - Helper for extracting heading and speed
Used to extend Position data with navigation information

All speed values are automatically converted from knots to m/s for consistency
with the navigation system.
"""
import logging
from typing import Optional, Tuple
from pynmeagps import NMEAMessage

logger = logging.getLogger(__name__)


class NMEANavigationParser:
    """
    Helper class for parsing heading and speed from NMEA messages
    Supports RMC (Recommended Minimum) and VTG (Track Made Good) messages
    
    Speed values are automatically converted from knots (GPS native) to m/s
    (SI unit used by navigation system).
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
            Tuple of (speed_mps, heading_degrees) or (None, None)
            Note: Speed is automatically converted from knots to m/s
        """
        speed_mps = None
        heading = None
        
        try:
            # Parse speed (in knots) and convert to m/s
            if hasattr(rmc, 'spd') and rmc.spd is not None and rmc.spd != '':
                try:
                    speed_knots = float(rmc.spd)
                    # Validate speed (0-200 knots is reasonable for ground vehicles)
                    if not 0.0 <= speed_knots <= 200.0:
                        logger.debug(f"RMC: Speed {speed_knots} kn out of range, ignoring")
                        speed_mps = None
                    else:
                        # Convert knots to m/s for consistency with navigation system
                        speed_mps = NMEANavigationParser.convert_knots_to_mps(speed_knots)
                        logger.debug(f"RMC: Parsed speed {speed_knots:.2f} kn → {speed_mps:.2f} m/s")
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
            
            return speed_mps, heading
            
        except Exception as e:
            logger.debug(f"Error parsing RMC navigation data: {e}")
            return None, None
    
    def parse_vtg_navigation(vtg: NMEAMessage) -> Tuple[Optional[float], Optional[float]]:
        """
        Parse speed and course from VTG message
        
        VTG format includes:
        - cogt: Course over ground (true, degrees)
        - sogk: Speed over ground (knots)
        
        Args:
            vtg: Parsed VTG NMEA message
            
        Returns:
            Tuple of (speed_mps, heading_degrees) or (None, None)
            Note: Speed is automatically converted from knots to m/s
        """
        speed_mps = None
        heading = None
        
        try:
            # Parse speed (in knots) and convert to m/s
            if hasattr(vtg, 'sogk') and vtg.sogk is not None and vtg.sogk != '':
                try:
                    speed_knots = float(vtg.sogk)
                    # Validate speed (0-200 knots is reasonable for ground vehicles)
                    if not 0.0 <= speed_knots <= 200.0:
                        logger.debug(f"VTG: Speed {speed_knots} kn out of range, ignoring")
                        speed_mps = None
                    else:
                        # Convert knots to m/s for consistency with navigation system
                        speed_mps = NMEANavigationParser.convert_knots_to_mps(speed_knots)
                        logger.debug(f"VTG: Parsed speed {speed_knots:.2f} kn → {speed_mps:.2f} m/s")
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
            
            return speed_mps, heading
            
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