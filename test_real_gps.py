#!/usr/bin/env python3
"""
Test RTK Manager z rzeczywistym sprzętem GPS
Uruchom ten test na Raspberry Pi z podłączonym LC29H(DA)
"""

import sys
import os
import logging
import time

# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gps.rtk_manager import RTKManager

def test_real_gps():
    """Test RTK Manager z rzeczywistym sprzętem"""
    
    print("🛰️ Test RTK Manager z rzeczywistym GPS")
    print("=" * 60)
    print("⚠️  Ten test wymaga:")
    print("   - Raspberry Pi z LC29H(DA) HAT")
    print("   - Połączenie internetowe")
    print("   - Antena GPS na zewnątrz")
    print("   - Aktywne konto ASG-EUPOS")
    print()
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    rtk = RTKManager()
    
    def position_callback(pos_data):
        lat = pos_data['lat']
        lon = pos_data['lon']
        status = pos_data['rtk_status']
        sats = pos_data.get('satellites', 0)
        hdop = pos_data.get('hdop', 0.0)
        
        print(f"📍 {lat:.6f}, {lon:.6f} | {status} | Sats: {sats} | HDOP: {hdop:.1f}")
    
    rtk.set_position_callback(position_callback)
    
    try:
        print("🔄 Inicjalizacja RTK Manager...")
        if rtk.initialize():
            print("✅ RTK Manager zainicjalizowany")
            
            print("🔄 Uruchomienie RTK system...")
            if rtk.start():
                print("✅ RTK system uruchomiony")
                
                # Check status
                status = rtk.get_status()
                print(f"📊 Status systemu:")
                print(f"   RTK Status: {status['rtk_status']}")
                print(f"   GPS połączony: {status['gps_connected']}")
                print(f"   NTRIP połączony: {status['ntrip_connected']}")
                print(f"   System działa: {status['running']}")
                print()
                
                if status['gps_connected']:
                    print("🎉 GPS połączony! Monitoring pozycji przez 60 sekund...")
                    print("📍 Format: LAT, LON | STATUS | Satelity | HDOP")
                    print("-" * 60)
                    
                    # Monitor for 60 seconds
                    start_time = time.time()
                    last_status = None
                    
                    while time.time() - start_time < 60:
                        current_status = rtk.get_status()
                        
                        # Show status changes
                        if current_status['rtk_status'] != last_status:
                            print(f"🔄 Status zmieniony na: {current_status['rtk_status']}")
                            last_status = current_status['rtk_status']
                        
                        time.sleep(1)
                        
                else:
                    print("⚠️  GPS nie został połączony - sprawdź:")
                    print("   1. Czy LC29H(DA) HAT jest podłączony")
                    print("   2. Czy UART jest włączony (/dev/ttyS0)")
                    print("   3. Czy antena GPS jest na zewnątrz")
                    print("   4. Uruchom: sudo dmesg | grep tty")
                    print("   5. Sprawdź: ls -la /dev/ttyS0")
                
                if status['ntrip_connected']:
                    print("🌐 NTRIP połączony - system RTK aktywny!")
                else:
                    print("⚠️  NTRIP nie został połączony - sprawdź:")
                    print("   1. Połączenie internetowe")
                    print("   2. Dane logowania ASG-EUPOS w .env")
                    print("   3. Czy konto ASG-EUPOS jest aktywne")
                    
            else:
                print("❌ Nie udało się uruchomić RTK system")
                
        else:
            print("❌ Nie udało się zainicjalizować RTK Manager")
            
    except KeyboardInterrupt:
        print("\n🛑 Test przerwany przez użytkownika")
        
    finally:
        print("\n🔄 Zatrzymywanie RTK system...")
        rtk.stop()
        print("✅ RTK system zatrzymany")

if __name__ == "__main__":
    test_real_gps()
