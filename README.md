# RTK Rover Project

Autonomiczny robot z pozycjonowaniem GPS-RTK, nawigacją i sterowaniem silnikami na Raspberry Pi.

## ✅ Status: PEŁNA INTEGRACJA ZAKOŃCZONA

System jest w pełni funkcjonalny - backend, API i frontend są zintegrowane i gotowe do testowania!

## 🚀 Features

- ✅ **GPS RTK** - Precyzyjne pozycjonowanie (dokładność 2-3 cm) przez ASG-EUPOS NTRIP
- ✅ **Autonomous Navigation** - Nawigacja do punktów waypoint z PID control
- ✅ **Motor Control** - Sterowanie silnikami L298N z napędem różnicowym
- ✅ **Web Interface** - Interfejs webowy z interaktywną mapą live
- ✅ **REST API** - Pełne API do kontroli nawigacji i silników
- ✅ **Safety Features** - Emergency stop (ESC key + button), timeout monitoring
- ✅ **Thread-Safe** - Singleton pattern z lazy initialization
- ✅ **Simulation Mode** - Automatyczne wykrywanie hardware (działa na PC i RPi)
- ✅ **Extensible** - Modularna architektura, łatwa rozbudowa

## 🔧 Hardware
- **GPS:** LC29H(DA) GPS/RTK HAT (UART connection)
- **Computer:** Raspberry Pi Zero 2 W / Raspberry Pi 4
- **Motors:** L298N Dual H-Bridge Motor Controller
- **Power:** 2x DC motors + 5V power supply for RPi
- **Connections:** 
  - L298N → RPi GPIO (ENA, IN1, IN2, ENB, IN3, IN4)
  - GPS → RPi UART (/dev/serial0)

## 📁 Struktura projektu

```
RtkRover/
├── app/                    # Flask web application (API + UI)
├── gps/                    # GPS-RTK modules
│   ├── adapters/          # LC29H GPS adapter
│   ├── core/              # Position interfaces
│   └── services/          # NTRIP client
├── navigation/             # ⭐ Navigation system
│   ├── core/              # Interfaces & data types
│   ├── algorithms/        # Geo calculations, PID, path planning
│   ├── navigator.py       # Main navigation logic
│   └── waypoint_manager.py # Waypoint queue management
├── motor_control/          # ⭐ Motor control system
│   ├── drivers/           # L298N hardware driver
│   ├── motor_controller.py # High-level motor control
│   └── motor_interface.py # Abstract interface
├── rover_manager.py        # ⭐ Main coordinator (GPS→Nav→Motors)
├── rover_manager_singleton.py # ⭐ Flask integration singleton
├── config/                 # Configuration files
├── static/                 # Frontend (CSS, JavaScript)
├── templates/              # HTML templates
├── tests/                  # Test scripts
└── docs/                   # Documentation
    ├── INTEGRATION_STATUS.md      # Pełny status integracji
    ├── FRONTEND_INTEGRATION.md    # Frontend API guide
    ├── INTEGRATION_PLAN.md        # Plan integracji
    ├── NAVIGATION_ARCHITECTURE.md # Architektura nawigacji
    └── FAQ.md                     # FAQ
├── motor_control/          # ⭐ Motor control system (NEW)
│   ├── drivers/           # Hardware drivers (L298N)
│   ├── motor_controller.py
│   └── motor_interface.py
├── rover_manager.py        # ⭐ Main rover coordinator (NEW)
├── rover_manager_singleton.py  # ⭐ Flask integration (NEW)
├── config/                 # Configuration files
├── templates/              # HTML templates
├── static/                 # CSS, JS
└── tests/                  # Unit tests
```

## 📖 Dokumentacja

- **[NAVIGATION_WAYPOINT_ALGORITHM.md](NAVIGATION_WAYPOINT_ALGORITHM.md)** - Algorytm nawigacji way-point (pseudokod, diagramy, przypadki użycia)
- **[INTEGRATION_PLAN.md](INTEGRATION_PLAN.md)** - Plan integracji RoverManager z RTKManager
- **[NAVIGATION_ARCHITECTURE.md](NAVIGATION_ARCHITECTURE.md)** - Architektura nawigacji i silników
- **[QUICK_START_INTEGRATION.py](QUICK_START_INTEGRATION.py)** - Szybki start integracji

## ⚙️ Konfiguracja

1. **Skopiuj plik konfiguracyjny:**
   ```bash
   cp .env.example .env
   ```

2. **Wypełnij dane w pliku `.env`:**
   
   **GPS RTK (ASG-EUPOS):**
   - Zarejestruj się na: https://www.asgeupos.pl/
   - Wpisz username i password
   
   **Silniki (L298N):**
   ```bash
   # GPIO Pins
   MOTOR_LEFT_IN1=17
   MOTOR_LEFT_IN2=22
   MOTOR_LEFT_EN=12
   MOTOR_RIGHT_IN1=23
   MOTOR_RIGHT_IN2=24
   MOTOR_RIGHT_EN=13
   
   # Motor settings
   MOTOR_USE_GPIO=true  # false dla testów bez sprzętu
   MOTOR_MAX_SPEED=0.8
   ```
   
   **Nawigacja:**
   ```bash
   NAV_MAX_SPEED=1.0
   NAV_WP_TOLERANCE=2.0  # metry
   ```

## 🚀 Szybki Start - Integracja

**Jeśli zaczynasz od zera:**

```bash
# 1. Klonuj repo
git clone <repo-url>
cd RtkRover

# 2. Zainstaluj zależności
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. Skonfiguruj
cp .env.example .env
# Edytuj .env

# 4. Uruchom testy integracji
python test_integration.py

# 5. Uruchom aplikację
python run.py
```

**Jeśli masz już działający system GPS:**

Przejdź przez **[INTEGRATION_CHECKLIST.md](INTEGRATION_CHECKLIST.md)** - kompletny przewodnik krok po kroku.

## 📚 Dokumentacja Szczegółowa

| Dokument | Opis |
|----------|------|
| **[NAVIGATION_WAYPOINT_ALGORITHM.md](NAVIGATION_WAYPOINT_ALGORITHM.md)** | 🗺️ Algorytm nawigacji way-point - pseudokod, diagramy przepływu, przypadki użycia |
| **[INTEGRATION_CHECKLIST.md](INTEGRATION_CHECKLIST.md)** | ✅ Lista kontrolna - krok po kroku integracja |
| **[INTEGRATION_PLAN.md](INTEGRATION_PLAN.md)** | 📋 Szczegółowy plan integracji z RTK |
| **[NAVIGATION_ARCHITECTURE.md](NAVIGATION_ARCHITECTURE.md)** | 🧭 Architektura nawigacji i silników |
| **[ARCHITECTURE_DIAGRAM.txt](ARCHITECTURE_DIAGRAM.txt)** | 📊 Diagram architektury systemu |
| **[FAQ.md](FAQ.md)** | ❓ Najczęściej zadawane pytania |
| **[QUICK_START_INTEGRATION.py](QUICK_START_INTEGRATION.py)** | ⚡ Szybki start - skrypt pomocniczy |

## 🧪 Testowanie

**Test komponentów (przed deploymentem):**
```bash
source venv/bin/activate
python test_components.py
```

**Test połączenia RTK (na Raspberry Pi z hardware):**
```bash
source venv/bin/activate
python -m gps.rtk_manager
```

## Uruchomienie

**Flask web interface:**
```bash
source venv/bin/activate
python run.py
```

Alternatywnie:
```bash
source venv/bin/activate
python -m flask --app app run --host=0.0.0.0 --port=5000
```

**Dostęp do interfejsu:**
- http://localhost:5000 (lokalnie)
- http://[IP_RASPBERRY]:5000 (zdalnie)
