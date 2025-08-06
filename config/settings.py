import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configuration file for ASG-EUPOS RTK connection
rtk_config = {
    "caster": os.getenv("ASG_CASTER", "www.asgeupos.pl"),
    "port": int(os.getenv("ASG_PORT", "2101")),
    "mountpoint": os.getenv("ASG_MOUNTPOINT", "NEAR"),  # Auto-select nearest station
    "username": os.getenv("ASG_USERNAME", ""),
    "password": os.getenv("ASG_PASSWORD", ""),
}

# UART configuration for LC29H(DA)
uart_config = {
    "port": "/dev/ttyS0",  # Pi Zero 2W UART port
    "baudrate": 115200,
    "timeout": 1.0
}

# GPS tracking settings
gps_config = {
    "min_satellites": 4,
    "rtk_timeout": 30,  # seconds
    "track_interval": 1.0,  # seconds between position logs
}
