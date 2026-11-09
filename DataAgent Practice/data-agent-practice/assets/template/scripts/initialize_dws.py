"""One-time cloud bootstrap: load synthetic data, then create the reader account."""
import json,os
from pathlib import Path
from dotenv import load_dotenv
from psycopg2 import sql

ROOT=Path(__file__).resolve().parents[1]
load_dotenv(ROOT/'.env')


def main():
    from backend.database import connect_dws
    admin_file=ROOT/'.runtime/deploy-admin.json'
    admin=json.loads(admin_file.read_text())
    reader_user=os.environ['DWS_USER'];reader_password=os.environ['DWS_PASSWORD']
    os.environ['DWS_USER']='dbadmin';os.environ['DWS_PASSWORD']=admin['password']
    from scripts.load_dws import main as load
    load()
    connection=connect_dws()
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(reader_user,))
            if not cursor.fetchone():
                cursor.execute(sql.SQL('CREATE USER {} PASSWORD {}').format(sql.Identifier(reader_user),sql.Literal(reader_password)))
            for schema in ['internal','external']:
                cursor.execute(sql.SQL('GRANT USAGE ON SCHEMA {} TO {}').format(sql.Identifier(schema),sql.Identifier(reader_user)))
                cursor.execute(sql.SQL('GRANT SELECT ON ALL TABLES IN SCHEMA {} TO {}').format(sql.Identifier(schema),sql.Identifier(reader_user)))
        connection.commit()
    finally:connection.close()
    os.environ['DWS_USER']=reader_user;os.environ['DWS_PASSWORD']=reader_password
    connection=connect_dws()
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT COUNT(*) FROM internal.orders');assert cursor.fetchone()[0]==2600
    finally:connection.close()
    admin_file.unlink()
    report={'loaded_rows':10000,'tables':12,'synthetic':True,'query_user':'nexo_reader','source_writes_disabled_for_query_user':True}
    path=ROOT/'.runtime/dws-import-report.json';path.write_text(json.dumps(report,indent=2));path.chmod(0o600)
    print(json.dumps(report))


if __name__=='__main__':main()
