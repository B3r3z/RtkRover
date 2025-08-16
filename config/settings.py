import os
import logging
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

class ConfigurationError(Exception):
    """Raised when configuration is invalid or incomplete"""
    pass

def validate_rtk_config():
    """Validate RTK configuration and required environment variables"""
    errors = []
    warnings = []
    
    # Check required ASG-EUPOS credentials
    username = os.getenv("ASG_USERNAME", "").strip()
    password = os.getenv("ASG_PASSWORD", "").strip()
    
    if not username:
        warnings.append("ASG_USERNAME is not configured - NTRIP will be disabled, using GPS-only mode")
    if not password:
        warnings.append("ASG_PASSWORD is not configured - NTRIP will be disabled, using GPS-only mode")
    
    # Only validate other settings if we have credentials
    if username and password:
        # Validate ASG-EUPOS server settings
        caster = os.getenv("ASG_CASTER", "system.asgeupos.pl").strip()
        if not caster:
            errors.append("ASG_CASTER cannot be empty when credentials are provided")
        elif not caster.endswith(".asgeupos.pl"):
            warnings.append(f"ASG_CASTER '{caster}' doesn't appear to be an ASG-EUPOS server")
        
        # Validate port
        try:
            port = int(os.getenv("ASG_PORT", "2101"))
            if port < 1 or port > 65535:
                errors.append(f"ASG_PORT must be between 1-65535, got {port}")
        except ValueError:
            errors.append("ASG_PORT must be a valid integer")
        
        # Validate mountpoint
        mountpoint = os.getenv("ASG_MOUNTPOINT", "NEAR").strip()
        if not mountpoint:
            warnings.append("ASG_MOUNTPOINT is empty, using 'NEAR' as default")
    
    # Log results
    if errors:
        error_msg = "RTK configuration validation failed:\n" + "\n".join(f"  - {err}" for err in errors)
        logger.error(error_msg)
        raise ConfigurationError(error_msg)
    
    if warnings:
        warning_msg = "RTK configuration warnings:\n" + "\n".join(f"  - {warn}" for warn in warnings)
        logger.warning(warning_msg)
    
    # Return True if NTRIP can be used, False for GPS-only mode
    ntrip_available = bool(username and password)
    if ntrip_available:
        logger.info("RTK configuration validation passed - NTRIP mode available")
    else:
        logger.warning("RTK configuration incomplete - GPS-only mode will be used")
    
    return ntrip_available

# Validate configuration on import
try:
    ntrip_available = validate_rtk_config()
except ConfigurationError as e:
    logger.error(f"RTK configuration invalid: {e}")
    logger.info("System will start in GPS-only mode without NTRIP corrections")
    ntrip_available = False

# Configuration file for ASG-EUPOS RTK connection
# Only populate if credentials are available
username = os.getenv("ASG_USERNAME", "").strip()
password = os.getenv("ASG_PASSWORD", "").strip()

rtk_config = {
    "caster": os.getenv("ASG_CASTER", "system.asgeupos.pl"),
    "port": int(os.getenv("ASG_PORT", "2101")),
    "mountpoint": os.getenv("ASG_MOUNTPOINT", "NEAR"),  # Auto-select nearest station
    "username": username,
    "password": password,
    "enabled": bool(username and password)  # Flag to indicate if NTRIP is configured
}

# UART configuration for LC29H(DA)
uart_config = {
    "port": os.getenv("GPS_PORT", "/dev/ttyS0"),  # GPS UART port - configurable
    "baudrate": int(os.getenv("GPS_BAUDRATE", "115200")),
    "timeout": float(os.getenv("GPS_TIMEOUT", "3.0"))
}

# GPS tracking settings
gps_config = {
    "min_satellites": 1,
    "rtk_timeout": 30,  # seconds
    "track_interval": 1.0,  # seconds between position logs
}
