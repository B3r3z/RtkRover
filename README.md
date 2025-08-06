# RTK Mower Project

Autonomiczny robot-kosiarka z pozycjonowaniem GPS-RTK na Raspberry Pi Zero 2W.

## Hardware
- LC29H(DA) GPS/RTK HAT
- Raspberry Pi Zero 2 W

## Struktura projektu

- `app/` - Flask aplikacja web
- `gps/` - Moduły GPS-RTK
- `config/` - Pliki konfiguracyjne
- `templates/` - HTML templates
- `static/` - CSS, JS, images
- `logs/` - Logi systemu
- `tests/` - Testy jednostkowe

## Instalacja na Raspberry Pi

```bash
git clone <repo-url>
cd rtk_mower
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Uruchomienie

```bash
source venv/bin/activate
python -m flask --app app run --host=0.0.0.0 --port=5000
```
