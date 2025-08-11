import unittest
from gps.rtcm_parser import RTCMParser


def build_rtcm_message(msg_type: int, payload_len: int = 2) -> bytes:
    # Build minimal RTCM frame: D3 | len | data(>=2) | CRC
    # Data begins with 12-bit message type in big-endian
    if payload_len < 2:
        payload_len = 2
    data = bytearray(payload_len)
    data[0] = (msg_type >> 4) & 0xFF
    data[1] = ((msg_type & 0x0F) << 4) & 0xF0

    length = len(data)
    header = bytearray(3)
    header[0] = 0xD3
    header[1] = (length >> 8) & 0x03  # reserved bits are 0
    header[2] = length & 0xFF

    body = bytes(header + data)

    # Compute CRC-24Q as in parser
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


class TestRTCMParserSmoke(unittest.TestCase):
    def test_parse_minimal_valid_frame(self):
        parser = RTCMParser()
        frame = build_rtcm_message(1005)
        msgs = parser.add_data(frame)
        self.assertEqual(len(msgs), 1)
        m = msgs[0]
        self.assertTrue(m.is_valid)
        self.assertEqual(m.message_type, 1005)
        self.assertEqual(m.length, 2)

    def test_fragmented_frame(self):
        parser = RTCMParser()
        frame = build_rtcm_message(1075, payload_len=10)
        # Feed in two parts to simulate fragmentation
        part1 = frame[:5]
        part2 = frame[5:]
        msgs1 = parser.add_data(part1)
        self.assertEqual(len(msgs1), 0)
        msgs2 = parser.add_data(part2)
        self.assertEqual(len(msgs2), 1)
        self.assertTrue(msgs2[0].is_valid)
        self.assertEqual(msgs2[0].message_type, 1075)


if __name__ == '__main__':
    unittest.main()
