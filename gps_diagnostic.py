#!/usr/bin/env python3
"""
GPS Diagnostic Tool for LC29H Module
Tests direct communication and NMEA output
"""

import serial
import time
import sys

def test_gps_direct(port="/dev/ttyACM0"):
    """Test direct GPS communication"""
    print(f"🔍 Testing GPS on {port}")
    
    baudrates = [115200, 38400, 9600]
    
    for baudrate in baudrates:
        print(f"\n📡 Testing at {baudrate} baud...")
        
        try:
            ser = serial.Serial(port, baudrate, timeout=1.0)
            print(f"✅ Serial port opened successfully")
            
            # Clear buffers
            ser.reset_input_buffer()
            ser.reset_output_buffer()
            
            # Wait and check for any data
            print("🔄 Checking for existing data...")
            time.sleep(2.0)
            
            if ser.in_waiting > 0:
                data = ser.read(ser.in_waiting)
                print(f"📊 Raw data received ({len(data)} bytes):")
                print(repr(data))
                
                # Try to decode
                try:
                    decoded = data.decode('ascii', errors='ignore')
                    lines = decoded.split('\n')
                    for line in lines:
                        if line.strip() and line.startswith('$'):
                            print(f"📍 NMEA: {line.strip()}")
                except:
                    print("❌ Could not decode as ASCII")
            else:
                print("⚠️  No data in buffer")
            
            # Send LC29H PAIR commands to force NMEA mode
            print("\n🔧 Sending LC29H PAIR commands...")
            
            lc29h_commands = [
                b"$PAIR000,1*3C\r\n",        # Set NMEA mode
                b"$PAIR010,1000*17\r\n",     # Set 1Hz output rate  
                b"$PAIR062,1,1*38\r\n",      # Enable GGA
                b"$PAIR062,2,1*3B\r\n",      # Enable GLL
                b"$PAIR062,5,1*3C\r\n",      # Enable RMC
                b"$PAIR001,0,0,1,1,1,1,0,0*3C\r\n",  # Configure NMEA output
            ]
            
            for cmd in lc29h_commands:
                print(f"📤 Sending: {cmd}")
                ser.write(cmd)
                time.sleep(0.3)
            
            # Wait for response
            print("\n⏳ Waiting for NMEA response (10 seconds)...")
            start_time = time.time()
            nmea_count = 0
            
            while time.time() - start_time < 10.0:
                if ser.in_waiting > 0:
                    try:
                        line = ser.readline().decode('ascii', errors='ignore').strip()
                        if line and line.startswith('$'):
                            nmea_count += 1
                            print(f"📍 NMEA[{nmea_count}]: {line}")
                            
                            if nmea_count >= 5:  # Got some NMEA data
                                print(f"✅ SUCCESS: GPS responding with NMEA at {baudrate} baud")
                                ser.close()
                                return True
                    except:
                        continue
                time.sleep(0.1)
            
            if nmea_count == 0:
                print(f"❌ No NMEA data received at {baudrate} baud")
            else:
                print(f"⚠️  Only {nmea_count} NMEA messages at {baudrate} baud")
            
            ser.close()
            
        except Exception as e:
            print(f"❌ Error at {baudrate} baud: {e}")
            continue
    
    print("\n❌ GPS communication failed at all baudrates")
    return False

def main():
    if len(sys.argv) > 1:
        port = sys.argv[1]
    else:
        port = "/dev/ttyACM0"
    
    print("🚀 GPS LC29H Diagnostic Tool")
    print("=" * 50)
    
    success = test_gps_direct(port)
    
    print("\n" + "=" * 50)
    if success:
        print("✅ GPS diagnostic completed successfully")
        print("💡 The GPS module is working and responding to PAIR commands")
    else:
        print("❌ GPS diagnostic failed")
        print("💡 Possible issues:")
        print("   - GPS module not connected")
        print("   - Wrong serial port")
        print("   - GPS in binary mode (not NMEA)")
        print("   - Hardware failure")
        print("   - Power supply issue")

if __name__ == "__main__":
    main()
