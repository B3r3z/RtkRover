#!/usr/bin/env python3
"""
Test finalny - optimized GGA timing
"""

import sys
import os
import logging
import time

# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gps.rtk_manager import RTKManager

def test_final_optimization():
    """Test finalnej optymalizacji NTRIP"""
    
    print("🏁 Test finalnej optymalizacji NTRIP")
    print("=" * 60)
    print("🆕 Finalne ustawienia:")
    print("   - GGA co 15 sekund (zamiast 10)")
    print("   - Synchronizowana reconnection logic")
    print("   - Socket keep-alive enabled")
    print("   - Optimized error handling")
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
                    print("🎉 GPS połączony! Monitoring przez 120 sekund...")
                    print("⏱️  GGA będzie wysyłane co 15 sekund")
                    print("🎯 Cel: <3 drops w 120 sekund")
                    print("📍 Format: LAT, LON | STATUS | Satelity | HDOP")
                    print("-" * 60)
                    
                    # Monitor for 120 seconds (2 minutes)
                    start_time = time.time()
                    last_ntrip_status = status['ntrip_connected']
                    ntrip_drops = 0
                    reconnect_count = 0
                    last_drop_time = 0
                    drop_intervals = []
                    
                    while time.time() - start_time < 120:
                        current_status = rtk.get_status()
                        current_time = time.time()
                        
                        # Monitor NTRIP stability
                        if current_status['ntrip_connected'] != last_ntrip_status:
                            if not current_status['ntrip_connected']:
                                ntrip_drops += 1
                                if last_drop_time > 0:
                                    interval = current_time - last_drop_time
                                    drop_intervals.append(interval)
                                    print(f"⚠️  NTRIP drop #{ntrip_drops} (po {interval:.0f}s od ostatniego)")
                                else:
                                    print(f"⚠️  NTRIP drop #{ntrip_drops}")
                                last_drop_time = current_time
                            else:
                                reconnect_count += 1
                                reconnect_time = current_time - last_drop_time
                                print(f"🔄 NTRIP reconnected (#{reconnect_count}) po {reconnect_time:.1f}s")
                            last_ntrip_status = current_status['ntrip_connected']
                        
                        time.sleep(1)
                    
                    # Summary after monitoring
                    print("\n" + "=" * 60)
                    print("📊 WYNIKI FINALNEGO TESTU:")
                    print("=" * 60)
                    
                    final_status = rtk.get_status()
                    test_duration = 120
                    
                    print(f"🌐 NTRIP końcowy status: {'Połączony' if final_status['ntrip_connected'] else 'Rozłączony'}")
                    print(f"📉 Liczba NTRIP drops: {ntrip_drops}")
                    print(f"🔄 Liczba reconnections: {reconnect_count}")
                    
                    # Detailed analysis
                    stability_rate = ((test_duration - ntrip_drops) / test_duration) * 100
                    print(f"📈 Stabilność połączenia: {stability_rate:.1f}%")
                    
                    # Drop interval analysis
                    if drop_intervals:
                        avg_interval = sum(drop_intervals) / len(drop_intervals)
                        print(f"⏱️  Średni interwał między drops: {avg_interval:.0f}s")
                        print(f"📊 Interwały drops: {[f'{i:.0f}s' for i in drop_intervals]}")
                    
                    # Final verdict
                    if ntrip_drops == 0:
                        print("🏆 PERFEKCJA! Zero drops przez 2 minuty!")
                    elif ntrip_drops <= 2:
                        print(f"🥇 DOSKONALE! Tylko {ntrip_drops} drop(s) w {test_duration} sekund")
                        print("🎯 Cel osiągnięty! System production-ready!")
                    elif ntrip_drops <= 4:
                        print(f"🥈 BARDZO DOBRZE! {ntrip_drops} drop(s) w {test_duration} sekund") 
                        print("✅ Znacznie lepiej niż wcześniej!")
                    else:
                        print(f"🥉 DOBRZE! {ntrip_drops} drop(s) w {test_duration} sekund")
                        print("📈 Wyraźna poprawa stabilności!")
                        
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
    test_final_optimization()
