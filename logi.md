python3 -m flask run --host=0.0.0.0 --port=5000 --debug
 * Debug mode: on
2025-08-07 20:16:34,623 - gps.rtk_manager - INFO - RTK Manager initializing...
2025-08-07 20:16:34,623 - root - INFO - RTK Manager initialized successfully
2025-08-07 20:16:34,635 - gps.rtk_manager - INFO - Trying GPS connection at 9600 baud...
2025-08-07 20:16:34,706 - werkzeug - INFO - WARNING: This is a development server. Do not use it in a production deployment. Use a production WSGI server instead.
 * Running on all addresses (0.0.0.0)
 * Running on http://127.0.0.1:5000
 * Running on http://192.168.1.21:5000
2025-08-07 20:16:34,707 - werkzeug - INFO - Press CTRL+C to quit
2025-08-07 20:16:34,711 - werkzeug - INFO -  * Restarting with stat
2025-08-07 20:16:35,828 - gps.rtk_manager - INFO - RTK Manager initializing...
2025-08-07 20:16:35,829 - root - INFO - RTK Manager initialized successfully
2025-08-07 20:16:35,831 - gps.rtk_manager - INFO - Trying GPS connection at 9600 baud...
2025-08-07 20:16:35,902 - werkzeug - WARNING -  * Debugger is active!
2025-08-07 20:16:35,904 - werkzeug - INFO -  * Debugger PIN: 107-415-563
2025-08-07 20:16:37,278 - gps.rtk_manager - INFO - Trying GPS connection at 38400 baud...
2025-08-07 20:16:37,837 - gps.rtk_manager - INFO - Trying GPS connection at 38400 baud...
2025-08-07 20:16:39,279 - gps.rtk_manager - INFO - Trying GPS connection at 115200 baud...
2025-08-07 20:16:39,838 - gps.rtk_manager - INFO - Trying GPS connection at 115200 baud...
2025-08-07 20:16:41,281 - gps.rtk_manager - INFO - GPS communication successful at 115200 baud
2025-08-07 20:16:41,282 - gps.rtk_manager - INFO - Connected to GPS on /dev/ttyS0 at 115200 baud
2025-08-07 20:16:41,283 - gps.rtk_manager - INFO - Connecting to NTRIP caster system.asgeupos.pl:2101
2025-08-07 20:16:41,343 - gps.rtk_manager - INFO - NTRIP connection successful
2025-08-07 20:16:41,344 - gps.rtk_manager - INFO - Full RTK system started (GPS + NTRIP)
2025-08-07 20:16:41,345 - gps.rtk_manager - INFO - NMEA processing loop started
2025-08-07 20:16:41,347 - gps.rtk_manager - INFO - RTCM forwarding loop started
2025-08-07 20:16:41,351 - gps.rtk_manager - INFO - GGA upload loop started
2025-08-07 20:16:41,352 - gps.rtk_manager - INFO - NTRIP mode: Started threads: NMEA processing, RTCM forwarding, GGA uploading
2025-08-07 20:16:41,353 - gps.rtk_manager - INFO - All available threads started: NMEA processing, RTCM forwarding, GGA uploading
2025-08-07 20:16:41,354 - gps.rtk_manager - INFO - RTK system started successfully in mode: RTK Connected
2025-08-07 20:16:41,354 - root - INFO - RTK system started successfully
2025-08-07 20:16:41,457 - gps.rtk_manager - INFO - RTK Status: Single
2025-08-07 20:16:41,840 - gps.rtk_manager - WARNING - Failed to connect to GPS: No working baudrate found
2025-08-07 20:16:41,841 - gps.rtk_manager - INFO - Starting in DEMO mode - no physical GPS hardware
2025-08-07 20:16:41,841 - gps.rtk_manager - INFO - Starting GPS demo simulation
2025-08-07 20:16:41,842 - gps.rtk_manager - INFO - DEMO MODE: Skipping NTRIP connection
2025-08-07 20:16:41,843 - gps.rtk_manager - INFO - Full RTK system started (GPS + NTRIP)
2025-08-07 20:16:41,843 - gps.rtk_manager - INFO - DEMO MODE: Threads already started in simulation
2025-08-07 20:16:41,843 - gps.rtk_manager - INFO - RTK system started successfully in mode: RTK Connected
2025-08-07 20:16:41,843 - root - INFO - RTK system started successfully
2025-08-07 20:16:43,354 - gps.rtk_manager - ERROR - Error uploading GGA: [Errno 32] Broken pipe
2025-08-07 20:16:43,354 - gps.rtk_manager - WARNING - NTRIP connection lost - cleaning up socket
2025-08-07 20:16:43,355 - gps.rtk_manager - INFO - Stopping GGA uploads due to broken connection
2025-08-07 20:16:43,356 - gps.rtk_manager - INFO - GGA upload loop ended
2025-08-07 20:16:43,356 - gps.rtk_manager - ERROR - RTCM loop error: [Errno 9] Bad file descriptor
2025-08-07 20:16:43,357 - gps.rtk_manager - INFO - RTCM forwarding loop ended
