#!/usr/bin/env python3
"""
Krótki test poprawek NTRIP (10 sekund GGA interval)
"""

import sys
import os
import logging
import time

# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gps.rtk_manager import RTKManager

def test_ntrip_improvements():
    """Test poprawek NTRIP z dłuższym interwałem GGA"""
    
    print("🔧 Test poprawek NTRIP")
    print("=" * 50)
    print("🆕 Zmiany:")
    print("   - GGA co 10 sekund zamiast 1 sekundy")
    print("   - Socket keep-alive enabled")  
    print("   - Tylko rzeczywiste pozycje GPS")
    print("   - Lepszy User-Agent")
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
                print(f"   GPS połączony: {status['gps_connected']}")
                print(f"   NTRIP połączony: {status['ntrip_connected']}")
                print()
                
                if status['gps_connected']:
                    print("🎉 GPS połączony! Monitoring przez 60 sekund...")
                    print("⏱️  GGA będzie wysyłane co 10 sekund")
                    print("📍 Format: LAT, LON | STATUS | Satelity | HDOP")
                    print("-" * 60)
                    
                    # Monitor for 60 seconds
                    start_time = time.time()
                    last_ntrip_status = status['ntrip_connected']
                    ntrip_drops = 0
                    
                    while time.time() - start_time < 60:
                        current_status = rtk.get_status()
                        
                        # Monitor NTRIP stability
                        if current_status['ntrip_connected'] != last_ntrip_status:
                            if not current_status['ntrip_connected']:
                                ntrip_drops += 1
                                print(f"⚠️  NTRIP drop #{ntrip_drops}")
                            else:
                                print(f"🔄 NTRIP reconnected")
                            last_ntrip_status = current_status['ntrip_connected']
                        
                        time.sleep(1)
                    
                    # Summary after monitoring
                    print("\n" + "=" * 50)
                    print("📊 WYNIKI TESTU:")
                    print("=" * 50)
                    
                    final_status = rtk.get_status()
                    print(f"🌐 NTRIP końcowy status: {'Połączony' if final_status['ntrip_connected'] else 'Rozłączony'}")
                    print(f"📉 Liczba NTRIP drops: {ntrip_drops}")
                    
                    if ntrip_drops == 0:
                        print("🎉 Poprawki zadziałały! NTRIP stabilny przez 60 sekund!")
                    elif ntrip_drops < 5:
                        print(f"✅ Znacznie lepiej! Tylko {ntrip_drops} drop(s) w 60 sekund")
                    else:
                        print(f"⚠️  Nadal niestabilny: {ntrip_drops} drop(s) w 60 sekund")
                        
                else:
                    print("⚠️  GPS nie został połączony")
                    
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
    test_ntrip_improvements()
