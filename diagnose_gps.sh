#!/bin/bash

echo "=== Diagnostyka GPS/UART na Raspberry Pi ==="

echo "1. Status usługi serial getty:"
sudo systemctl status serial-getty@ttyS0.service

echo -e "\n2. Konfiguracja UART w /boot/config.txt:"
grep -E "(uart|serial)" /boot/config.txt

echo -e "\n3. Sprawdzenie urządzeń UART:"
ls -la /dev/tty*

echo -e "\n4. Uprawnienia użytkownika do dialout:"
groups $USER | grep dialout

echo -e "\n5. Procesy używające ttyS0:"
sudo lsof /dev/ttyS0 2>/dev/null || echo "Brak procesów używających ttyS0"

echo -e "\n6. Test komunikacji z GPS (5 sekund):"
echo "Naciśnij Ctrl+C aby przerwać wcześniej..."
timeout 5 sudo cat /dev/ttyS0 2>/dev/null || echo "Brak danych z GPS"

echo -e "\n7. Sprawdzenie prędkości transmisji:"
sudo stty -F /dev/ttyS0

echo -e "\n=== Koniec diagnostyki ==="
