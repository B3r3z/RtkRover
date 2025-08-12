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
        
        # Wait longer for GPS to get fix
        print("⏳ Waiting for GPS fix (120 seconds)...")
        print("💡 GPS needs clear sky view and time for cold start!")
        
        start_time = time.time()
        message_count = 0
        gga_count = 0
        gll_count = 0
        other_count = 0
        last_quality = None
        last_satellites = None
        
        while time.time() - start_time < 120.0:
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
                                lat = getattr(parsed_data, 'lat', 'N/A')
                                lon = getattr(parsed_data, 'lon', 'N/A') 
                                quality = getattr(parsed_data, 'quality', 'N/A')
                                numSV = getattr(parsed_data, 'numSV', 'N/A')
                                HDOP = getattr(parsed_data, 'HDOP', 'N/A')
                                
                                # Track changes in GPS status
                                if quality != last_quality or numSV != last_satellites:
                                    last_quality = quality
                                    last_satellites = numSV
                                    print(f"   📊 GPS Status Change:")
                                    print(f"      Quality: {quality} (0=Invalid, 1=GPS, 2=DGPS, 4=RTK Fixed, 5=RTK Float)")
                                    print(f"      Satellites: {numSV}, HDOP: {HDOP}")
                                    if lat != 'N/A' and lon != 'N/A':
                                        print(f"      Position: {lat}°N, {lon}°E")
                                
                                # Success condition: GPS fix with coordinates
                                if quality and int(quality) > 0 and lat != 'N/A' and lon != 'N/A':
                                    print(f"\n🎉 GPS FIX ACHIEVED!")
                                    print(f"   Quality: {quality}, Position: {lat}°N, {lon}°E")
                                    break
                                    
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
                            print(f"📄 ... (continuing to monitor)")
                    
                    # Show progress every 10 seconds
                    elapsed = time.time() - start_time
                    if int(elapsed) % 10 == 0 and elapsed > 1:
                        print(f"⏰ {int(elapsed)}s elapsed - Quality: {last_quality}, Satellites: {last_satellites}")
                            
                    # If we got GPS fix, that's success!
                    # Continue monitoring for actual GPS fix
                        
            except Exception as e:
                print(f"❌ Read error: {e}")
                continue
                
        print(f"\n📊 SUMMARY:")
        print(f"   Total messages: {message_count}")
        print(f"   GGA messages: {gga_count}")
        print(f"   GLL messages: {gll_count}")
        print(f"   Other messages: {other_count}")
        
        if gga_count > 0:
            if last_quality and int(last_quality) > 0:
                print(f"✅ SUCCESS: LC29H has GPS fix (Quality: {last_quality})!")
            else:
                print(f"⚠️  PARTIAL: LC29H sending NMEA but no GPS fix yet")
                print(f"💡 Try moving GPS to location with clear sky view")
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
