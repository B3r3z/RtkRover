import time

def build_dummy_gga() -> str:
    """
    Builds a standardized dummy GGA sentence for keep-alive or fallback.
    Uses a fixed location (e.g., center of Poland) and current time.
    """
    current_time = time.strftime('%H%M%S')
    # Using a consistent location for the dummy message
    dummy_gga = f"$GNGGA,{current_time},5213.0000,N,02100.0000,E,1,08,1.0,100.0,M,0.0,M,,*00\r\n"
    return dummy_gga
