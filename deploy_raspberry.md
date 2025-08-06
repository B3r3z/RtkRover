# Wdrożenie RTK Mower na Raspberry Pi

## Wymagania systemowe
- Raspberry Pi Zero 2W lub nowszy
- Raspbian OS (najlepiej Lite)
- LC29H(DA) GPS/RTK HAT
- Połączenie internetowe (WiFi lub Ethernet)

## 1. Przygotowanie systemu

```bash
# Aktualizacja systemu
sudo apt update && sudo apt upgrade -y

# Instalacja Python i narzędzi
sudo apt install python3 python3-pip python3-venv git -y

# Włączenie UART (dla komunikacji z GPS)
sudo raspi-config
# -> Interface Options -> Serial Port
# -> "Would you like a login shell accessible over serial?" -> No
# -> "Would you like the serial port hardware enabled?" -> Yes

# Restartuj Raspberry Pi
sudo reboot
```

## 2. Klonowanie projektu

```bash
# Sklonuj repozytorium
git clone https://github.com/B3r3z/RtkRover.git
cd RtkRover/rtk_mower

# Stwórz środowisko wirtualne
python3 -m venv .venv
source .venv/bin/activate

# Zainstaluj zależności
pip install -r requirements.txt
```

## 3. Konfiguracja GPS/RTK

```bash
# Sprawdź czy UART działa
ls -la /dev/ttyS0
# Powinno pokazać urządzenie

# Test komunikacji z GPS (opcjonalne)
sudo apt install minicom -y
minicom -b 115200 -o -D /dev/ttyS0
# Powinieneś zobaczyć NMEA sentences jak $GNGGA,$GNRMC itp.
# Ctrl+A, X aby wyjść
```

## 4. Konfiguracja środowiska

```bash
# Skopiuj przykładową konfigurację
cp .env.example .env

# Edytuj konfigurację dla Polski (ASG-EUPOS)
nano .env
```

Przykładowa konfiguracja `.env`:
```
# RTK Configuration for Poland (ASG-EUPOS)
RTK_CASTER=www.asgeupos.pl
RTK_PORT=2101
RTK_MOUNTPOINT=POZNAN_RTCM31  # Wybierz najbliższą stację
RTK_USERNAME=your_username
RTK_PASSWORD=your_password

# GPS Configuration
UART_PORT=/dev/ttyS0
UART_BAUDRATE=115200
UART_TIMEOUT=3

# Flask Configuration
FLASK_ENV=production
FLASK_HOST=0.0.0.0
FLASK_PORT=5000
```

## 5. Uruchomienie aplikacji

### Tryb deweloperski (z debugowaniem):
```bash
cd /home/pi/RtkRover/rtk_mower
source .venv/bin/activate
python3 -m flask run --host=0.0.0.0 --port=5000 --debug
```

### Tryb produkcyjny (bez debugowania):
```bash
cd /home/pi/RtkRover/rtk_mower
source .venv/bin/activate
python3 -m flask run --host=0.0.0.0 --port=5000
```

## 6. Dostęp do aplikacji

- Z sieci lokalnej: `http://IP_RASPBERRY_PI:5000`
- Sprawdź IP Raspberry Pi: `hostname -I`
- Przykład: `http://192.168.1.100:5000`

## 7. Automatyczne uruchamianie (systemd service)

Stwórz plik service:
```bash
sudo nano /etc/systemd/system/rtk-mower.service
```

Zawartość:
```ini
[Unit]
Description=RTK Mower Web Interface
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/RtkRover/rtk_mower
Environment=PATH=/home/pi/RtkRover/rtk_mower/.venv/bin
ExecStart=/home/pi/RtkRover/rtk_mower/.venv/bin/python3 -m flask run --host=0.0.0.0 --port=5000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Aktywacja service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable rtk-mower.service
sudo systemctl start rtk-mower.service

# Sprawdź status
sudo systemctl status rtk-mower.service

# Logi
sudo journalctl -u rtk-mower.service -f
```

## 8. Rozwiązywanie problemów

### Problem z uprawnieniami do UART:
```bash
# Dodaj użytkownika do grupy dialout
sudo usermod -a -G dialout pi
# Wyloguj się i zaloguj ponownie
```

### Problem z portem zajętym:
```bash
# Sprawdź co używa portu
sudo lsof -i :5000
# Zatrzymaj proces jeśli potrzeba
sudo pkill -f flask
```

### Sprawdź logi GPS:
```bash
# Monitoruj NMEA sentences
cat /dev/ttyS0
```

### Test połączenia z NTRIP:
```bash
# Test połączenia z castrem ASG-EUPOS
telnet www.asgeupos.pl 2101
```

## 9. Monitoring i logi

```bash
# Logi systemowe RTK Mower
sudo journalctl -u rtk-mower.service -f

# Logi Flask (jeśli uruchamiasz ręcznie)
tail -f /var/log/rtk-mower.log

# Monitor zasobów
htop

# Temperatura CPU
vcgencmd measure_temp
```

## 10. Aktualizacja aplikacji

```bash
cd /home/pi/RtkRover
git pull origin main
cd rtk_mower
source .venv/bin/activate
pip install -r requirements.txt --upgrade

# Restart service
sudo systemctl restart rtk-mower.service
```
