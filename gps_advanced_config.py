#!/usr/bin/env python3
"""
Advanced LC29H GPS Configuration Tool
Forces NMEA output through various PAIR command combinations
"""

import serial
import time
import sys

def configure_lc29h_nmea(port="/dev/ttyS0"):
    """Try multiple methods to force LC29H into NMEA mode"""
    print(f"🔧 Advanced LC29H Configuration on {port}")
    
    try:
        ser = serial.Serial(port, 115200, timeout=1.0)
        print(f"✅ Connected at 115200 baud")
        
        # Clear buffers
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        time.sleep(0.5)
        
        # Method 1: Factory reset + NMEA configuration
        print("\n🔄 Method 1: Factory reset + NMEA config")
        method1_commands = [
            b"$PAIR510*32\r\n",               # Factory reset
            b"$PAIR000,1*3C\r\n",             # Set NMEA mode
            b"$PAIR010,1000*17\r\n",          # Set 1Hz output rate
            b"$PAIR001,0,0,1,1,1,1,0,0*3C\r\n", # Enable GGA,GLL,GSA,GSV,RMC,VTG
        ]
        
        for cmd in method1_commands:
            print(f"📤 {cmd}")
            ser.write(cmd)
            time.sleep(1.0)  # Longer delay for factory reset
        
        # Check for NMEA
        if check_for_nmea(ser, "Method 1"):
            return True
        
        # Method 2: Individual message enable commands
        print("\n🔄 Method 2: Individual PAIR062 commands")
        method2_commands = [
            b"$PAIR000,1*3C\r\n",      # NMEA mode
            b"$PAIR062,1,1*38\r\n",    # Enable GGA
            b"$PAIR062,2,1*3B\r\n",    # Enable GLL
            b"$PAIR062,3,1*3A\r\n",    # Enable GSA
            b"$PAIR062,4,1*3D\r\n",    # Enable GSV
            b"$PAIR062,5,1*3C\r\n",    # Enable RMC
            b"$PAIR062,6,1*3F\r\n",    # Enable VTG
        ]
        
        for cmd in method2_commands:
            print(f"📤 {cmd}")
            ser.write(cmd)
            time.sleep(0.5)
        
        # Check for NMEA
        if check_for_nmea(ser, "Method 2"):
            return True
        
        # Method 3: Alternative PAIR commands
        print("\n🔄 Method 3: Alternative configuration")
        method3_commands = [
            b"$PAIR013,1,0*18\r\n",    # Set protocol to NMEA
            b"$PAIR063,1,1,1,1*17\r\n", # Enable NMEA output
            b"$PAIR020,1000,0*1F\r\n", # Set update rate
        ]
        
        for cmd in method3_commands:
            print(f"📤 {cmd}")
            ser.write(cmd)
            time.sleep(0.5)
        
        # Check for NMEA
        if check_for_nmea(ser, "Method 3"):
            return True
            
        # Method 4: Force cold start + NMEA
        print("\n🔄 Method 4: Cold start + NMEA")
        method4_commands = [
            b"$PAIR050,1*36\r\n",      # Cold start
            b"$PAIR000,1*3C\r\n",      # NMEA mode
            b"$PAIR001,0,0,1,1,1,1,0,0*3C\r\n", # Enable messages
        ]
        
        for cmd in method4_commands:
            print(f"📤 {cmd}")
            ser.write(cmd)
            time.sleep(2.0)  # Long delay for cold start
        
        # Check for NMEA
        if check_for_nmea(ser, "Method 4"):
            return True
        
        print("❌ All configuration methods failed")
        return False
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False
    finally:
        if 'ser' in locals():
            ser.close()

def check_for_nmea(ser, method_name, timeout=15):
    """Check for NMEA messages for specified timeout"""
    print(f"⏳ Checking for NMEA messages ({timeout}s)...")
    
    start_time = time.time()
    nmea_messages = []
    pair_messages = []
    
    while time.time() - start_time < timeout:
        if ser.in_waiting > 0:
            try:
                line = ser.readline().decode('ascii', errors='ignore').strip()
                if line:
                    if line.startswith('$G') and any(msg in line for msg in ['GGA', 'GLL', 'RMC', 'GSA', 'GSV', 'VTG']):
                        nmea_messages.append(line)
                        print(f"✅ NMEA: {line}")
                        
                        if len(nmea_messages) >= 3:
                            print(f"🎉 {method_name} SUCCESS! Got {len(nmea_messages)} NMEA messages")
                            return True
                    elif line.startswith('$PAIR'):
                        pair_messages.append(line)
                        print(f"📋 PAIR: {line}")
            except:
                continue
        time.sleep(0.1)
    
    print(f"⚠️  {method_name}: {len(nmea_messages)} NMEA, {len(pair_messages)} PAIR messages")
    return False

def continuous_monitor(port="/dev/ttyS0", duration=30):
    """Monitor GPS output continuously"""
    print(f"\n👁️  Continuous monitoring for {duration} seconds...")
    
    try:
        ser = serial.Serial(port, 115200, timeout=1.0)
        start_time = time.time()
        message_count = {'nmea': 0, 'pair': 0, 'other': 0}
        
        while time.time() - start_time < duration:
            if ser.in_waiting > 0:
                try:
                    line = ser.readline().decode('ascii', errors='ignore').strip()
                    if line:
                        if line.startswith('$G'):
                            message_count['nmea'] += 1
                            print(f"📍 NMEA[{message_count['nmea']}]: {line}")
                        elif line.startswith('$PAIR'):
                            message_count['pair'] += 1
                            print(f"📋 PAIR[{message_count['pair']}]: {line}")
                        elif line.startswith('$'):
                            message_count['other'] += 1
                            print(f"❓ OTHER[{message_count['other']}]: {line}")
                except:
                    continue
            time.sleep(0.1)
        
        print(f"\n📊 Monitor Results: NMEA={message_count['nmea']}, PAIR={message_count['pair']}, OTHER={message_count['other']}")
        ser.close()
        
    except Exception as e:
        print(f"❌ Monitor error: {e}")

def main():
    if len(sys.argv) > 1:
        port = sys.argv[1]
    else:
        port = "/dev/ttyS0"
    
    print("🚀 Advanced LC29H GPS Configuration Tool")
    print("=" * 60)
    
    # Try to configure NMEA
    success = configure_lc29h_nmea(port)
    
    if success:
        print("\n✅ NMEA configuration successful!")
        print("💡 You can now run the main RTK application")
    else:
        print("\n⚠️  NMEA configuration failed, starting continuous monitoring...")
        continuous_monitor(port, 30)
    
    print("\n" + "=" * 60)
    print("🏁 Configuration attempt completed")

if __name__ == "__main__":
    main()
