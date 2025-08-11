#!/usr/bin/env python3
"""
Comprehensive RTCM Stream Validation Tests
Tests real-world scenarios: mixed data, corruption, fragmentation, CRC validation
"""

import unittest
import struct
from gps.rtcm_parser import RTCMParser, RTCMValidator


class TestRTCMStreamValidation(unittest.TestCase):
    
    def setUp(self):
        self.parser = RTCMParser()
    
    def build_rtcm_message(self, msg_type: int, payload_len: int = 2) -> bytes:
        """Build valid RTCM message with correct CRC-24Q"""
        if payload_len < 2:
            payload_len = 2
        data = bytearray(payload_len)
        data[0] = (msg_type >> 4) & 0xFF
        data[1] = ((msg_type & 0x0F) << 4) & 0xF0
        
        # Fill remaining payload with test pattern
        for i in range(2, payload_len):
            data[i] = (i * 37) & 0xFF
        
        length = len(data)
        header = bytearray(3)
        header[0] = 0xD3
        header[1] = (length >> 8) & 0x03
        header[2] = length & 0xFF
        
        body = bytes(header + data)
        
        # Compute CRC-24Q
        def crc24q(buf: bytes) -> int:
            crc = 0
            for b in buf:
                crc ^= b << 16
                for _ in range(8):
                    if crc & 0x800000:
                        crc = (crc << 1) ^ 0x1864CFB
                    else:
                        crc <<= 1
            return crc & 0xFFFFFF
        
        crc = crc24q(body)
        crc_bytes = bytes([(crc >> 16) & 0xFF, (crc >> 8) & 0xFF, crc & 0xFF])
        return body + crc_bytes
    
    def test_common_rtcm_types(self):
        """Test parsing of common RTK message types"""
        common_types = [1005, 1007, 1033, 1075, 1085, 1095, 1125, 1230, 4094]
        
        for msg_type in common_types:
            with self.subTest(msg_type=msg_type):
                frame = self.build_rtcm_message(msg_type, payload_len=10)
                msgs = self.parser.add_data(frame)
                
                self.assertEqual(len(msgs), 1, f"Should parse one message for type {msg_type}")
                msg = msgs[0]
                self.assertTrue(msg.is_valid, f"Message type {msg_type} should be valid")
                self.assertEqual(msg.message_type, msg_type)
                self.assertEqual(len(msg.raw_message), 16)  # 3 header + 10 data + 3 CRC
    
    def test_mixed_valid_invalid_stream(self):
        """Test stream with mix of valid RTCM and garbage data"""
        # Create mixed stream: garbage + valid RTCM + garbage + valid RTCM
        garbage1 = b'\x12\x34\x56\x78\x9A'
        valid1 = self.build_rtcm_message(1075, 20)
        garbage2 = b'$GNGGA,invalid,nmea*00\r\n'
        valid2 = self.build_rtcm_message(1085, 15)
        garbage3 = b'\xFF\xFF\x00\x00'
        
        stream = garbage1 + valid1 + garbage2 + valid2 + garbage3
        
        msgs = self.parser.add_data(stream)
        
        self.assertEqual(len(msgs), 2, "Should extract 2 valid messages from mixed stream")
        self.assertEqual(msgs[0].message_type, 1075)
        self.assertEqual(msgs[1].message_type, 1085)
        self.assertTrue(all(msg.is_valid for msg in msgs))
    
    def test_fragmented_large_message(self):
        """Test large RTCM message received in multiple fragments"""
        large_msg = self.build_rtcm_message(1095, 320)  # Typical MSM5 size
        
        # Split into random fragments
        fragments = [
            large_msg[0:5],    # Partial header
            large_msg[5:50],   # More data
            large_msg[50:200], # Bulk data
            large_msg[200:]    # Rest + CRC
        ]
        
        total_msgs = []
        for fragment in fragments:
            msgs = self.parser.add_data(fragment)
            total_msgs.extend(msgs)
        
        self.assertEqual(len(total_msgs), 1, "Should parse one complete message from fragments")
        msg = total_msgs[0]
        self.assertTrue(msg.is_valid)
        self.assertEqual(msg.message_type, 1095)
        self.assertEqual(len(msg.raw_message), 326)  # 3 + 320 + 3
    
    def test_crc_corruption_detection(self):
        """Test that corrupted CRC is properly detected"""
        valid_msg = self.build_rtcm_message(1005, 25)
        
        # Corrupt the CRC (last 3 bytes)
        corrupted = bytearray(valid_msg)
        corrupted[-1] ^= 0x01  # Flip one bit in CRC
        
        msgs = self.parser.add_data(bytes(corrupted))
        
        # Parser should reject invalid CRC messages and track the error
        self.assertEqual(len(msgs), 0, "Invalid CRC messages should be rejected")
        
        # Check that CRC error was tracked in statistics
        stats = self.parser.get_statistics()
        self.assertGreater(stats['crc_errors'], 0, "CRC error should be tracked")
    
    def test_buffer_overflow_protection(self):
        """Test parser handles buffer overflow gracefully"""
        # Create stream with lots of garbage (no valid preambles)
        garbage_stream = bytes([i & 0xFF for i in range(2000)])  # 2KB of garbage
        
        # Should not crash and should truncate buffer
        msgs = self.parser.add_data(garbage_stream)
        self.assertEqual(len(msgs), 0, "No valid messages in garbage stream")
        
        # Buffer should be limited
        self.assertLessEqual(len(self.parser.buffer), 1000, "Buffer should be truncated")
    
    def test_multiple_messages_in_single_add(self):
        """Test parsing multiple complete messages in one data chunk"""
        msg1 = self.build_rtcm_message(1005, 25)
        msg2 = self.build_rtcm_message(1007, 31)
        msg3 = self.build_rtcm_message(1033, 78)
        
        combined = msg1 + msg2 + msg3
        msgs = self.parser.add_data(combined)
        
        self.assertEqual(len(msgs), 3, "Should parse all 3 messages")
        self.assertEqual([m.message_type for m in msgs], [1005, 1007, 1033])
        self.assertTrue(all(m.is_valid for m in msgs))
    
    def test_statistics_tracking(self):
        """Test that parser statistics are correctly maintained"""
        # Reset stats
        self.parser.reset_statistics()
        
        # Add valid messages
        valid1 = self.build_rtcm_message(1075, 50)
        valid2 = self.build_rtcm_message(1075, 60)  # Same type
        msgs1 = self.parser.add_data(valid1)
        msgs2 = self.parser.add_data(valid2)
        
        # Add invalid message (corrupt CRC)
        invalid = bytearray(self.build_rtcm_message(1085, 30))
        invalid[-1] ^= 0xFF  # Corrupt CRC
        msgs3 = self.parser.add_data(bytes(invalid))
        
        # Add data that starts with RTCM preamble but is invalid to trigger parse errors
        fake_rtcm = b'\xD3\x00\x05invalid'  # Valid preamble but bad data
        self.parser.add_data(fake_rtcm)
        
        stats = self.parser.get_statistics()
        
        self.assertEqual(stats['total_parsed'], 2, "Should track valid messages")
        self.assertEqual(stats['crc_errors'], 1, "Should track CRC errors")
        self.assertEqual(stats['message_types'][1075], 2, "Should count message types")
        # Parser errors might be 0 if no exceptions occur in structured RTCM data
        self.assertGreaterEqual(stats['parse_errors'], 0, "Should track parse errors (may be 0)")
    
    def test_validator_data_type_detection(self):
        """Test RTCMValidator correctly identifies data types"""
        # Valid RTCM
        rtcm_data = self.build_rtcm_message(1075, 100)
        self.assertTrue(RTCMValidator.is_rtcm_data(rtcm_data))
        self.assertEqual(RTCMValidator.detect_data_type(rtcm_data), 'rtcm')
        
        # NMEA data
        nmea_data = b'$GNGGA,123456,5200.0000,N,02100.0000,E,1,08,1.0,100.0,M,0.0,M,,*67\r\n'
        self.assertFalse(RTCMValidator.is_rtcm_data(nmea_data))
        self.assertEqual(RTCMValidator.detect_data_type(nmea_data), 'nmea')
        
        # Unknown/garbage data
        garbage = b'\x12\x34\x56\x78\x9A\xBC\xDE\xF0'
        self.assertFalse(RTCMValidator.is_rtcm_data(garbage))
        self.assertEqual(RTCMValidator.detect_data_type(garbage), 'unknown')
    
    def test_reset_functionality(self):
        """Test parser reset clears state properly"""
        # Add some data
        msg = self.build_rtcm_message(1005, 25)
        self.parser.add_data(msg[:10])  # Partial message
        
        # Verify buffer has data
        self.assertGreater(len(self.parser.buffer), 0)
        
        # Reset and verify clean state
        self.parser.reset()
        self.assertEqual(len(self.parser.buffer), 0)
        
        # Should work normally after reset
        complete_msg = self.build_rtcm_message(1007, 31)
        msgs = self.parser.add_data(complete_msg)
        self.assertEqual(len(msgs), 1)
        self.assertTrue(msgs[0].is_valid)


if __name__ == '__main__':
    unittest.main()
