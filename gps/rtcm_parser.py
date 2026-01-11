import logging
import struct
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class RTCMMessage:
    message_type: int
    length: int
    data: bytes
    crc: int
    raw_message: bytes
    is_valid: bool

class RTCMParser:
    """
    RTCM 3.x Message Parser
    
    RTCM 3.x Message Structure:
    - Preamble: 0xD3 (8 bits)
    - Reserved: 6 bits (must be 0)
    - Message Length: 10 bits (0-1023 bytes)
    - Message Type: 12 bits
    - Message Data: Variable length
    - CRC: 24 bits
    """
    
    def __init__(self):
        self.buffer = bytearray()
        self.stats = {
            'messages_parsed': 0,
            'parse_errors': 0,
            'crc_errors': 0,
            'unknown_messages': 0,
            'message_types': {}
        }
        self.rtcm_message_types = {
            1001: "GPS L1 Code Observations",
            1002: "GPS L1 Phase Observations", 
            1003: "GPS L1 Code & Phase Observations",
            1004: "GPS L1 Code & Phase Observations (Extended)",
            1005: "RTK Base Station ARP Coordinates",
            1006: "RTK Base Station ARP Coordinates with Height",
            1007: "Antenna Descriptor",
            1008: "Antenna Descriptor & Serial Number",
            1009: "GLONASS L1 Code Observations",
            1010: "GLONASS L1 Phase Observations",
            1011: "GLONASS L1 Code & Phase Observations",
            1012: "GLONASS L1 Code & Phase Observations (Extended)",
            1019: "GPS Ephemeris",
            1020: "GLONASS Ephemeris",
            1033: "Receiver and Antenna Descriptors",
            1074: "GPS MSM4",
            1075: "GPS MSM5",
            1077: "GPS MSM7",
            1084: "GLONASS MSM4",
            1085: "GLONASS MSM5",
            1087: "GLONASS MSM7",
            1094: "Galileo MSM4",
            1095: "Galileo MSM5",
            1097: "Galileo MSM7",
            1124: "BeiDou MSM4",
            1125: "BeiDou MSM5",
            1127: "BeiDou MSM7",
            1230: "GLONASS Code-Phase Biases",
            4094: "Proprietary (4094)"
        }
    
    def add_data(self, data: bytes) -> List[RTCMMessage]:
        self.buffer.extend(data)
        return self._extract_messages()
    
    def _extract_messages(self) -> List[RTCMMessage]:
        messages = []
        max_iterations = 10
        iterations = 0
        
        while len(self.buffer) >= 1 and iterations < max_iterations:
            iterations += 1
            
            preamble_idx = self._find_preamble()
            
            if preamble_idx == -1:
                if len(self.buffer) > 1000:
                    self.buffer = self.buffer[-100:]
                    logger.warning(f"Buffer too large ({len(self.buffer)} bytes), truncated")
                break

            if preamble_idx > 0:
                discarded = self.buffer[:preamble_idx]
                self.buffer = self.buffer[preamble_idx:]
                logger.debug(f"Discarded {len(discarded)} bytes before RTCM preamble")

            if len(self.buffer) < 3:
                break
            try:
                header = struct.unpack('>I', b'\x00' + self.buffer[0:3])[0]
                length = header & 0x3FF
                total_length = 3 + length + 3
                if length <= 0 or length > 1023:
                    self.buffer = self.buffer[1:]
                    continue
                if len(self.buffer) < total_length:
                    break
            except Exception:
                break
            
            message = self._parse_message()
            
            if message:
                messages.append(message)
                self.buffer = self.buffer[len(message.raw_message):]
            else:
                self.buffer = self.buffer[1:]
        
        return messages
    
    def reset(self):
        logger.info("🔄 Resetting RTCM parser - clearing all buffers")
        self.buffer = bytearray()
        self.incomplete_message = None
        # Reset any internal state if needed
    
    def _find_preamble(self) -> int:
        for i in range(len(self.buffer)):
            if self.buffer[i] == 0xD3:
                return i
        return -1
    
    def _parse_message(self) -> Optional[RTCMMessage]:
        if len(self.buffer) < 6:
            return None
        
        try:
            if self.buffer[0] != 0xD3:
                # This happens during scanning, debug only
                logger.debug("Invalid RTCM preamble")
                self.stats['parse_errors'] += 1
                return None
            
            header = struct.unpack('>I', b'\x00' + self.buffer[0:3])[0]
            
            preamble = (header >> 16) & 0xFF  # Should be 0xD3
            reserved = (header >> 10) & 0x3F  # Should be 0
            length = header & 0x3FF  # Message length (0-1023)
            
            if preamble != 0xD3:
                logger.debug(f"Invalid preamble: 0x{preamble:02X}")
                self.stats['parse_errors'] += 1
                return None
            
            if reserved != 0:
                # False sync is common, don't spam warnings
                logger.debug(f"Invalid reserved field: {reserved}")
                return None
            
            total_length = 3 + length + 3  # Header + Data + CRC
            if len(self.buffer) < total_length:
                return None  # Wait for more data
            
            message_data = self.buffer[3:3+length]
            crc_bytes = self.buffer[3+length:3+length+3]
            crc = struct.unpack('>I', b'\x00' + crc_bytes)[0]
            
            if length >= 2:
                msg_type = struct.unpack('>H', message_data[0:2])[0] >> 4
            else:
                msg_type = 0
            
            raw_message = bytes(self.buffer[0:total_length])

            is_valid = self._validate_crc(raw_message[:-3], crc)
            if not is_valid:
                self.stats['crc_errors'] += 1
                # Only log debug for CRC errors to avoid spam during false syncs
                logger.debug(f"Invalid CRC for RTCM message type {msg_type} (len={length})")
                return None

            self.stats['messages_parsed'] += 1
            if msg_type in self.stats['message_types']:
                self.stats['message_types'][msg_type] += 1
            else:
                self.stats['message_types'][msg_type] = 1

            msg_name = self.rtcm_message_types.get(msg_type, f"Unknown ({msg_type})")
            if msg_type not in self.rtcm_message_types:
                self.stats['unknown_messages'] += 1

            return RTCMMessage(
                message_type=msg_type,
                length=length,
                data=message_data,
                crc=crc,
                raw_message=raw_message,
                is_valid=is_valid
            )

        except Exception as e:
            logger.error(f"Error parsing RTCM message: {e}")
            self.stats['parse_errors'] += 1
            return None

    def _validate_crc(self, data: bytes, received_crc: int) -> bool:
        """
        Validate CRC-24Q using table lookup
        """
        crc = 0
        for byte in data:
            crc = ((crc << 8) & 0xFFFFFF) ^ self.CRC24_TABLE[(crc >> 16) ^ byte]
        return crc == received_crc

    # Precomputed CRC-24Q table (Poly: 0x1864CFB)
    CRC24_TABLE = [
        0x000000, 0x864CFB, 0x8AD50D, 0x0C99F6, 0x93E6E1, 0x15AA1A, 0x1933EC, 0x9F7F17,
        0xA18139, 0x27CDC2, 0x2B5434, 0xAD18CF, 0x3267D8, 0xB42B23, 0xB8B2D5, 0x3EFE2E,
        0xC54E89, 0x430272, 0x4F9B84, 0xC9D77F, 0x56A868, 0xD0E493, 0xDC7D65, 0x5A319E,
        0x64CFB0, 0xE2834B, 0xEE1ABD, 0x685646, 0xF72951, 0x7165AA, 0x7DFC5C, 0xFBB0A7,
        0x0CD1E9, 0x8A9D12, 0x8604E4, 0x00481F, 0x9F3708, 0x197BF3, 0x15E205, 0x93AEFE,
        0xAD50D0, 0x2B1C2B, 0x2785DD, 0xA1C926, 0x3EB631, 0xB8FACA, 0xB4633C, 0x322FC7,
        0xC99F60, 0x4FD39B, 0x434A6D, 0xC50696, 0x5A7981, 0xDC357A, 0xD0AC8C, 0x56E077,
        0x681E59, 0xEE52A2, 0xE2CB54, 0x6487AF, 0xFBF8B8, 0x7DB443, 0x712DB5, 0xF7614E,
        0x19A3D2, 0x9FEF29, 0x9376DF, 0x153A24, 0x8A4533, 0x0C09C8, 0x00903E, 0x86DCC5,
        0xB822EB, 0x3E6E10, 0x32F7E6, 0xB4BB1D, 0x2BC40A, 0xAD88F1, 0xA11107, 0x275DFC,
        0xDCED5B, 0x5AA1A0, 0x563856, 0xD074AD, 0x4F0BBA, 0xC94741, 0xC5DEB7, 0x43924C,
        0x7D6C62, 0xFB2099, 0xF7B96F, 0x71F594, 0xEE8A83, 0x68C678, 0x645F8E, 0xE21375,
        0x15723B, 0x933EC0, 0x9FA736, 0x19EBCD, 0x8694DA, 0x00D821, 0x0C41D7, 0x8A0D2C,
        0xB4F302, 0x32BFF9, 0x3E260F, 0xB86AF4, 0x2715E3, 0xA15918, 0xADC0EE, 0x2B8C15,
        0xD03CB2, 0x567049, 0x5AE9BF, 0xDCA544, 0x43DA53, 0xC596A8, 0xC90F5E, 0x4F43A5,
        0x71BD8B, 0xF7F170, 0xFB6886, 0x7D247D, 0xE25B6A, 0x641791, 0x688E67, 0xEEC29C,
        0x3347A4, 0xB50B5F, 0xB992A9, 0x3FDE52, 0xA0A145, 0x26EDBE, 0x2A7448, 0xAC38B3,
        0x92C69D, 0x148A66, 0x181390, 0x9E5F6B, 0x01207C, 0x876C87, 0x8BF571, 0x0DB98A,
        0xF6092D, 0x7045D6, 0x7CDC20, 0xFA90DB, 0x65EFCC, 0xE3A337, 0xEF3AC1, 0x69763A,
        0x578814, 0xD1C4EF, 0xDD5D19, 0x5B11E2, 0xC46EF5, 0x42220E, 0x4EBBF8, 0xC8F703,
        0x3F964D, 0xB9DAB6, 0xB54340, 0x330FBB, 0xAC70AC, 0x2A3C57, 0x26A5A1, 0xA0E95A,
        0x9E1774, 0x185B8F, 0x14C279, 0x928E82, 0x0DF195, 0x8BBD6E, 0x872498, 0x016863,
        0xFAD8C4, 0x7C943F, 0x700DC9, 0xF64132, 0x693E25, 0xEF72DE, 0xE3EB28, 0x65A7D3,
        0x5B59FD, 0xDD1506, 0xD18CF0, 0x57C00B, 0xC8BF1C, 0x4EF3E7, 0x426A11, 0xC426EA,
        0x2AE476, 0xACA88D, 0xA0317B, 0x267D80, 0xB90297, 0x3F4E6C, 0x33D79A, 0xB59B61,
        0x8B654F, 0x0D29B4, 0x01B042, 0x87FCB9, 0x1883AE, 0x9ECF55, 0x9256A3, 0x141A58,
        0xEFAAFF, 0x69E604, 0x657FF2, 0xE33309, 0x7C4C1E, 0xFA00E5, 0xF69913, 0x70D5E8,
        0x4E2BC6, 0xC8673D, 0xC4FECB, 0x42B230, 0xDDCD27, 0x5B81DC, 0x57182A, 0xD154D1,
        0x26359F, 0xA07964, 0xACE092, 0x2AAC69, 0xB5D37E, 0x339F85, 0x3F0673, 0xB94A88,
        0x87B4A6, 0x01F85D, 0x0D61AB, 0x8B2D50, 0x145247, 0x921EBC, 0x9E874A, 0x18CBB1,
        0xE37B16, 0x6537ED, 0x69AE1B, 0xEFE2E0, 0x709DF7, 0xF6D10C, 0xFA48FA, 0x7C0401,
        0x42FA2F, 0xC4B6D4, 0xC82F22, 0x4E63D9, 0xD11CCE, 0x575035, 0x5BC9C3, 0xDD8538
    ]
    
    def get_statistics(self) -> Dict[str, Any]:
        return {
            'total_parsed': self.stats['messages_parsed'],
            'parse_errors': self.stats['parse_errors'],
            'crc_errors': self.stats['crc_errors'],
            'unknown_messages': self.stats['unknown_messages'],
            'message_types': self.stats['message_types'].copy(),
            'buffer_size': len(self.buffer)
        }
    
    def reset_statistics(self):
        self.stats = {
            'messages_parsed': 0,
            'parse_errors': 0,
            'crc_errors': 0,
            'unknown_messages': 0,
            'message_types': {}
        }
    
    def clear_buffer(self):
        self.buffer.clear()


class RTCMValidator:
    @staticmethod
    def is_rtcm_data(data: bytes) -> bool:
        """
        Quick check if data contains RTCM messages
        
        Args:
            data: Raw bytes to check
            
        Returns:
            True if data appears to be RTCM, False otherwise
        """
        if not data or len(data) < 3:
            return False
        
        try:
            text = data.decode('ascii', errors='ignore').strip()
            if text.startswith('$') and any(msg_type in text for msg_type in ['GGA', 'RMC', 'GSV', 'GLL', 'VTG']):
                logger.error(f"NMEA data detected instead of RTCM: {text[:80]}...")
                return False
        except:
            pass
        
        rtcm_found = False
        for i in range(min(50, len(data) - 2)):
            if data[i] == 0xD3:
                if len(data) >= i + 3:
                    try:
                        header = struct.unpack('>I', b'\x00' + data[i:i+3])[0]
                        length = header & 0x3FF
                        if 0 < length < 1024:
                            rtcm_found = True
                            break
                    except:
                        continue

        if not rtcm_found:
            if len(data) > 20:
                repeating_bytes = sum(1 for i in range(1, min(20, len(data))) if data[i] == data[i-1])
                repeating_ratio = repeating_bytes / min(20, len(data))

                if repeating_ratio > 0.5:
                    logger.debug(f"Rejected data: too many repeating bytes ({repeating_ratio:.1%})")
                    return False
                
                # Check for all-zero or all-0xFF patterns
                if all(b == 0x00 for b in data[:10]) or all(b == 0xFF for b in data[:10]):
                    logger.debug("Rejected data: all zeros or all 0xFF")
                    return False
        
        return rtcm_found
    
    @staticmethod
    def detect_data_type(data: bytes) -> str:
        if not data:
            return 'unknown'
        
        try:
            text = data.decode('ascii', errors='ignore').strip()
            if text.startswith('$'):
                return 'nmea'
        except:
            pass
        
        if RTCMValidator.is_rtcm_data(data):
            return 'rtcm'
        
        return 'unknown'
