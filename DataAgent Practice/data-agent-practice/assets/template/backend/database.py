"""DWS connections verify TLS using explicitly configured trust roots."""
import os


def connect_dws(timeout=10):
    import psycopg2
    return psycopg2.connect(host=os.environ['DWS_HOST'],port=os.getenv('DWS_PORT','8000'),
        dbname=os.getenv('DWS_DATABASE','gaussdb'),user=os.environ['DWS_USER'],password=os.environ['DWS_PASSWORD'],
        sslmode=os.getenv('DWS_SSLMODE','verify-full'),sslrootcert=os.getenv('DWS_SSLROOTCERT'),connect_timeout=timeout)


def dws_available():
    try:
        connection=connect_dws(timeout=3)
        try:
            with connection.cursor() as cursor:cursor.execute('SELECT 1');return cursor.fetchone()[0]==1
        finally:connection.close()
    except Exception:return False
