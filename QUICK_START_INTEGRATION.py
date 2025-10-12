"""
Quick Start Guide - Integracja RoverManager z RTKManager
Wykonaj krok po kroku
"""

# ============================================
# KROK 1: Rozszerzenie Position dataclass
# ============================================
print("KROK 1: Dodawanie heading i speed do Position")
print("Plik: gps/core/interfaces.py")
print("""
Znajdź:
    @dataclass
    class Position:
        lat: float
        lon: float
        altitude: float
        satellites: int
        hdop: float
        rtk_status: RTKStatus
        timestamp: str

Zmień na:
    @dataclass
    class Position:
        lat: float
        lon: float
        altitude: float
        satellites: int
        hdop: float
        rtk_status: RTKStatus
        timestamp: str
        speed: Optional[float] = None      # prędkość w węzłach
        heading: Optional[float] = None    # kurs w stopniach (0-360)
""")

# ============================================
# KROK 2: GlobalRoverManager Singleton
# ============================================
print("\n" + "="*50)
print("KROK 2: Utworzenie GlobalRoverManager")
print("Nowy plik: rover_manager_singleton.py")
print("Status: Plik gotowy do utworzenia - sprawdź plan!")

# ============================================
# KROK 3: Testowanie integracji
# ============================================
print("\n" + "="*50)
print("KROK 3: Test integracji")
print("""
# Test skrypt
python << 'EOF'
from rover_manager_singleton import global_rover_manager
from gps.rtk_manager import RTKManager

# Symulacja inicjalizacji
rtk = RTKManager()
rtk.start()

# Inicjalizacja rover
rover = global_rover_manager.initialize(rtk)

if rover:
    print("✅ RoverManager zainicjalizowany")
    status = rover.get_rover_status()
    print(f"Status: {status}")
else:
    print("❌ Błąd inicjalizacji")

EOF
""")

# ============================================
# KROK 4: Integracja z Flask
# ============================================
print("\n" + "="*50)
print("KROK 4: Integracja z Flask")
print("Plik: app/__init__.py")
print("""
1. Dodaj import:
   from rover_manager_singleton import global_rover_manager

2. W funkcji _register_routes, dodaj przed definicjami route:
   
   @app.before_first_request
   def init_rover_manager():
       rtk_manager = app_manager.get_rtk_manager()
       if rtk_manager:
           global_rover_manager.initialize(rtk_manager)
           logger.info("Rover Manager initialized in Flask")

3. Dodaj endpoint test:
   
   @app.route('/api/navigation/test')
   def api_nav_test():
       rover = global_rover_manager.get_rover_manager()
       if rover:
           return jsonify({"status": "ok", "message": "Rover ready"})
       return jsonify({"status": "error", "message": "Rover not initialized"}), 503
""")

# ============================================
# KROK 5: Weryfikacja
# ============================================
print("\n" + "="*50)
print("KROK 5: Weryfikacja")
print("""
1. Uruchom aplikację:
   python run.py

2. Sprawdź endpoint:
   curl http://localhost:5000/api/navigation/test

3. Sprawdź logi:
   tail -f rtk_mower.log | grep -i rover

4. Sprawdź status:
   curl http://localhost:5000/api/navigation/status
""")

# ============================================
# Podsumowanie
# ============================================
print("\n" + "="*50)
print("PODSUMOWANIE")
print("="*50)
print("""
✓ Krok 1: Rozszerz Position (gps/core/interfaces.py)
✓ Krok 2: Utwórz rover_manager_singleton.py
✓ Krok 3: Test integracji
✓ Krok 4: Dodaj do Flask (app/__init__.py)
✓ Krok 5: Weryfikacja

Szczegóły w: INTEGRATION_PLAN.md
""")
