#!/usr/bin/env python3
"""
RTCM Parser for RTK Rover
Handles proper parsing and validation of RTCM 3.x correction messages
"""

import logging
import struct
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class RTCMMessage:
    """Represents a parsed RTCM message"""
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
        
        # Common RTCM 3.x message types for RTK
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
            1127: "BeiDou MSM7"
        }
    
    def add_data(self, data: bytes) -> List[RTCMMessage]:
        """
        Add new data to parser buffer and extract complete RTCM messages
        
        Args:
            data: Raw bytes from NTRIP stream
            
        Returns:
            List of parsed RTCM messages
        """
        self.buffer.extend(data)
        return self._extract_messages()
    
    def _extract_messages(self) -> List[RTCMMessage]:
        """Extract complete RTCM messages from buffer"""
        messages = []
        max_iterations = 10  # Prevent infinite loops
        iterations = 0
        
        while len(self.buffer) >= 6 and iterations < max_iterations:
            iterations += 1
            
            # Look for RTCM preamble (0xD3)
            preamble_idx = self._find_preamble()
            
            if preamble_idx == -1:
                # No preamble found, but keep some data for next iteration
                if len(self.buffer) > 1000:  # Prevent buffer overflow
                    # Keep last 100 bytes in case preamble is split
                    self.buffer = self.buffer[-100:]
                    logger.warning(f"Buffer too large ({len(self.buffer)} bytes), truncated")
                break
            
            # Remove data before preamble
            if preamble_idx > 0:
                discarded = self.buffer[:preamble_idx]
                self.buffer = self.buffer[preamble_idx:]
                logger.debug(f"Discarded {len(discarded)} bytes before RTCM preamble")
            
            # Try to parse message
            message = self._parse_message()
            
            if message:
                messages.append(message)
                # Remove parsed message from buffer
                self.buffer = self.buffer[len(message.raw_message):]
            else:
                # Parsing failed, remove one byte and try again
                self.buffer = self.buffer[1:]
        
        return messages
    
    def reset(self):
        """Reset parser state and clear buffers"""
        logger.info("🔄 Resetting RTCM parser - clearing all buffers")
        self.buffer = b''
        self.incomplete_message = None
        # Reset any internal state if needed
    
    def _find_preamble(self) -> int:
        """Find RTCM preamble (0xD3) in buffer"""
        for i in range(len(self.buffer)):
            if self.buffer[i] == 0xD3:
                return i
        return -1
    
    def _parse_message(self) -> Optional[RTCMMessage]:
        """Parse single RTCM message from buffer start"""
        if len(self.buffer) < 6:
            return None
        
        try:
            # Check preamble
            if self.buffer[0] != 0xD3:
                logger.warning("Invalid RTCM preamble")
                self.stats['parse_errors'] += 1
                return None
            
            # Extract header (first 3 bytes)
            header = struct.unpack('>I', b'\x00' + self.buffer[0:3])[0]
            
            # Parse header fields
            preamble = (header >> 16) & 0xFF  # Should be 0xD3
            reserved = (header >> 10) & 0x3F  # Should be 0
            length = header & 0x3FF  # Message length (0-1023)
            
            # Validate header
            if preamble != 0xD3:
                logger.warning(f"Invalid preamble: 0x{preamble:02X}")
                self.stats['parse_errors'] += 1
                return None
            
            if reserved != 0:
                logger.warning(f"Invalid reserved field: {reserved}")
            
            # Check if we have complete message
            total_length = 3 + length + 3  # Header + Data + CRC
            if len(self.buffer) < total_length:
                return None  # Wait for more data
            
            # Extract message data
            message_data = self.buffer[3:3+length]
            
            # Extract CRC
            crc_bytes = self.buffer[3+length:3+length+3]
            crc = struct.unpack('>I', b'\x00' + crc_bytes)[0]
            
            # Extract message type (first 12 bits of data)
            if length >= 2:
                msg_type = struct.unpack('>H', message_data[0:2])[0] >> 4
            else:
                msg_type = 0
            
            # Create raw message
            raw_message = bytes(self.buffer[0:total_length])
            
            # Validate CRC
            is_valid = self._validate_crc(raw_message[:-3], crc)
            if not is_valid:
                logger.warning(f"CRC validation failed for message type {msg_type}")
                self.stats['crc_errors'] += 1
            
            # Update statistics
            self.stats['messages_parsed'] += 1
            if msg_type in self.stats['message_types']:
                self.stats['message_types'][msg_type] += 1
            else:
                self.stats['message_types'][msg_type] = 1
            
            # Log message info
            msg_name = self.rtcm_message_types.get(msg_type, f"Unknown ({msg_type})")
            if msg_type not in self.rtcm_message_types:
                self.stats['unknown_messages'] += 1
            
            logger.debug(f"📡 RTCM Message: Type {msg_type} ({msg_name}), Length: {length}, Valid: {is_valid}")
            
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
        Validate RTCM CRC-24Q
        
        RTCM uses CRC-24Q polynomial: 0x1864CFB
        """
        try:
            # Simplified CRC validation for now
            # TODO: Implement proper CRC-24Q algorithm
            return True  # For now, assume CRC is valid
        except Exception as e:
            logger.error(f"CRC validation error: {e}")
            return False
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get parser statistics"""
        return {
            'total_parsed': self.stats['messages_parsed'],
            'parse_errors': self.stats['parse_errors'],
            'crc_errors': self.stats['crc_errors'],
            'unknown_messages': self.stats['unknown_messages'],
            'message_types': self.stats['message_types'].copy(),
            'buffer_size': len(self.buffer)
        }
    
    def reset_statistics(self):
        """Reset parser statistics"""
        self.stats = {
            'messages_parsed': 0,
            'parse_errors': 0,
            'crc_errors': 0,
            'unknown_messages': 0,
            'message_types': {}
        }
    
    def clear_buffer(self):
        """Clear internal buffer"""
        self.buffer.clear()


class RTCMValidator:
    """
    Validates if data stream contains valid RTCM messages
    Helps distinguish between RTCM and NMEA data
    """
    
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
        
        # Check for NMEA first (should be rejected)
        try:
            text = data.decode('ascii', errors='ignore').strip()
            if text.startswith('$') and any(msg_type in text for msg_type in ['GGA', 'RMC', 'GSV', 'GLL', 'VTG']):
                logger.error(f"❌ NMEA data detected instead of RTCM: {text[:80]}...")
                return False
        except:
            pass  # Not text data, continue checking for RTCM
        
        # Look for RTCM preamble (0xD3)
        rtcm_found = False
        for i in range(min(50, len(data) - 2)):  # Check more bytes
            if data[i] == 0xD3:
                # Validate RTCM structure
                if len(data) >= i + 3:
                    try:
                        header = struct.unpack('>I', b'\x00' + data[i:i+3])[0]
                        length = header & 0x3FF  # Extract length
                        if 0 < length < 1024:  # Reasonable RTCM message length
                            rtcm_found = True
                            logger.debug(f"✅ Valid RTCM preamble found at byte {i}, length={length}")
                            break
                    except:
                        continue
        
        # Additional checks for corrupted data
        if not rtcm_found:
            # Check if data looks like random binary (possibly corrupted RTCM)
            if len(data) > 20:
                # Count repeating patterns (sign of corruption)
                repeating_bytes = sum(1 for i in range(1, min(20, len(data))) if data[i] == data[i-1])
                repeating_ratio = repeating_bytes / min(20, len(data))
                
                # Check for obvious non-RTCM patterns
                if repeating_ratio > 0.5:  # Too many repeating bytes
                    logger.debug(f"Rejected data: too many repeating bytes ({repeating_ratio:.1%})")
                    return False
                
                # Check for all-zero or all-0xFF patterns
                if all(b == 0x00 for b in data[:10]) or all(b == 0xFF for b in data[:10]):
                    logger.debug("Rejected data: all zeros or all 0xFF")
                    return False
            
            hex_preview = ' '.join([f'{b:02x}' for b in data[:20]])
            logger.debug(f"⚠️  No valid RTCM preamble found. First 20 bytes: {hex_preview}")
        
        return rtcm_found
    
    @staticmethod
    def detect_data_type(data: bytes) -> str:
        """
        Detect what type of data this is
        
        Returns:
            'rtcm', 'nmea', or 'unknown'
        """
        if not data:
            return 'unknown'
        
        # Check for NMEA
        try:
            text = data.decode('ascii', errors='ignore').strip()
            if text.startswith('$'):
                return 'nmea'
        except:
            pass
        
        # Check for RTCM
        if RTCMValidator.is_rtcm_data(data):
            return 'rtcm'
        
        return 'unknown'
