#!/usr/bin/env python3
"""
Test simple LC29H reading like Waveshare code
"""

import serial
import time
from pynmeagps import NMEAReader

def test_lc29h_simple():
    """Test LC29H reading exactly like Waveshare code"""
    print("🚀 Testing LC29H Simple Reading (Waveshare style)")
    print("=" * 60)
    
    try:
        # Open serial exactly like Waveshare
        print("📡 Opening /dev/ttyS0 at 115200 baud...")
        stream = serial.Serial('/dev/ttyS0', 115200, timeout=3)
        print("✅ Serial port opened successfully")
        
        # Create NMEAReader exactly like Waveshare  
        nmr = NMEAReader(stream)
        print("✅ NMEAReader created")
        
        # Wait a bit for GPS to initialize
        print("⏳ Waiting for GPS data (30 seconds)...")
        
        start_time = time.time()
        message_count = 0
        gga_count = 0
        gll_count = 0
        other_count = 0
        
        while time.time() - start_time < 30.0:
            try:
                # Read exactly like Waveshare
                (raw_data, parsed_data) = nmr.read()
                
                if raw_data:
                    message_count += 1
                    message_str = raw_data.decode('ascii', errors='ignore').strip()
                    
                    if b"GNGGA" in raw_data or b"GPGGA" in raw_data:
                        gga_count += 1
                        print(f"📍 GGA[{gga_count}]: {message_str}")
                        
                        if parsed_data:
                            try:
                                lat = getattr(parsed_data, 'lat', None)
                                lon = getattr(parsed_data, 'lon', None) 
                                quality = getattr(parsed_data, 'quality', None)
                                numSV = getattr(parsed_data, 'numSV', None)
                                HDOP = getattr(parsed_data, 'HDOP', None)
                                
                                print(f"   Position: {lat:.6f}°N, {lon:.6f}°E")
                                print(f"   Quality: {quality}, Satellites: {numSV}, HDOP: {HDOP}")
                            except Exception as e:
                                print(f"   Parse error: {e}")
                                
                    elif b"GNGLL" in raw_data or b"GPGLL" in raw_data:
                        gll_count += 1
                        print(f"📍 GLL[{gll_count}]: {message_str}")
                        
                    elif message_str.startswith('$'):
                        other_count += 1
                        if other_count <= 5:  # Show first 5 other messages
                            print(f"📄 OTHER[{other_count}]: {message_str}")
                        elif other_count == 6:
                            print(f"📄 ... ({other_count} other NMEA messages)")
                            
                    # If we got GGA with fix, that's success!
                    if gga_count >= 3:
                        print(f"\n✅ SUCCESS: Got {gga_count} GGA messages!")
                        break
                        
            except Exception as e:
                print(f"❌ Read error: {e}")
                continue
                
        print(f"\n📊 SUMMARY:")
        print(f"   Total messages: {message_count}")
        print(f"   GGA messages: {gga_count}")
        print(f"   GLL messages: {gll_count}")
        print(f"   Other messages: {other_count}")
        
        if gga_count > 0:
            print(f"✅ SUCCESS: LC29H is sending NMEA data!")
            return True
        else:
            print(f"❌ FAILED: No GGA messages received")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False
    finally:
        try:
            stream.close()
        except:
            pass

if __name__ == "__main__":
    test_lc29h_simple()
