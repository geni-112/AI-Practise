"""Delay API startup until the local Temporal development server accepts connections."""
import socket,time
for _ in range(90):
    try:
        with socket.create_connection(('127.0.0.1',7233),timeout=2):break
    except OSError:time.sleep(2)
else:raise SystemExit('Temporal is not available')
