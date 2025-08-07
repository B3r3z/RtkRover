#!/usr/bin/env python3
"""
Test poprawek synchronizacji reconnect
"""

import sys
import os
import logging
import time

# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gps.rtk_manager import RTKManager

def test_reconnect_synchronization():
    """Test poprawek synchronizacji reconnect"""
    
    print("🔧 Test poprawek synchronizacji NTRIP reconnect")
    print("=" * 60)
    print("🆕 Zmiany:")
    print("   - Mutex blokujący równoczesne reconnect próby")
    print("   - Opóźnienie przed reconnect (1s)")
    print("   - GGA co 10 sekund")
    print("   - Lepsza obsługa 'Broken pipe'")
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
                    print("🎉 GPS połączony! Monitoring przez 90 sekund...")
                    print("⏱️  GGA będzie wysyłane co 10 sekund")
                    print("🔒 Synchronizowana reconnection logic")
                    print("📍 Format: LAT, LON | STATUS | Satelity | HDOP")
                    print("-" * 60)
                    
                    # Monitor for 90 seconds (longer test)
                    start_time = time.time()
                    last_ntrip_status = status['ntrip_connected']
                    ntrip_drops = 0
                    reconnect_count = 0
                    consecutive_errors = 0
                    
                    while time.time() - start_time < 90:
                        current_status = rtk.get_status()
                        
                        # Monitor NTRIP stability
                        if current_status['ntrip_connected'] != last_ntrip_status:
                            if not current_status['ntrip_connected']:
                                ntrip_drops += 1
                                consecutive_errors += 1
                                print(f"⚠️  NTRIP drop #{ntrip_drops} (consecutive: {consecutive_errors})")
                            else:
                                reconnect_count += 1
                                consecutive_errors = 0  # Reset on successful reconnect
                                print(f"🔄 NTRIP reconnected (#{reconnect_count})")
                            last_ntrip_status = current_status['ntrip_connected']
                        
                        time.sleep(1)
                    
                    # Summary after monitoring
                    print("\n" + "=" * 60)
                    print("📊 WYNIKI TESTU:")
                    print("=" * 60)
                    
                    final_status = rtk.get_status()
                    print(f"🌐 NTRIP końcowy status: {'Połączony' if final_status['ntrip_connected'] else 'Rozłączony'}")
                    print(f"📉 Liczba NTRIP drops: {ntrip_drops}")
                    print(f"🔄 Liczba reconnections: {reconnect_count}")
                    
                    # Detailed analysis
                    test_duration = 90
                    stability_rate = ((test_duration - ntrip_drops) / test_duration) * 100
                    
                    print(f"📈 Stabilność połączenia: {stability_rate:.1f}%")
                    
                    if ntrip_drops == 0:
                        print("🎉 PERFEKCYJNIE! NTRIP stabilny przez cały test!")
                    elif ntrip_drops <= 2:
                        print(f"✅ ŚWIETNIE! Tylko {ntrip_drops} drop(s) w {test_duration} sekund")
                        print("🔒 Synchronizacja reconnect działa!")
                    elif ntrip_drops <= 5:
                        print(f"✅ DOBRZE! {ntrip_drops} drop(s) w {test_duration} sekund")
                        print("📈 Znacznie lepszy wynik niż wcześniej!")
                    else:
                        print(f"⚠️  NADAL PROBLEMY: {ntrip_drops} drop(s) w {test_duration} sekund")
                        
                    # Recovery analysis
                    if reconnect_count > 0:
                        recovery_rate = (reconnect_count / ntrip_drops) * 100 if ntrip_drops > 0 else 0
                        print(f"🚀 Recovery rate: {recovery_rate:.1f}% ({reconnect_count}/{ntrip_drops})")
                        
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
    test_reconnect_synchronization()
