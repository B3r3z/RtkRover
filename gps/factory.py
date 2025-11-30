from gps.adapters.lc29h_gps import LC29HGPS
from gps.services.ntrip_service import NTRIPServiceAdapter
from typing import Dict, Any
from .interfaces import RTKSystemInterface

def create_rtk_system(uart_config: dict, ntrip_config: dict) -> RTKSystemInterface:
    gps = LC29HGPS(port=uart_config['port'])
    
    ntrip_service = None
    if ntrip_config.get('enabled', False):
        ntrip_service = NTRIPServiceAdapter(ntrip_config)
    
    return RTKSystem(gps, ntrip_service)

class RTKFactory:
    @staticmethod
    def create_system(uart_config: dict, ntrip_config: dict) -> RTKSystemInterface:
        return create_rtk_system(uart_config, ntrip_config)
