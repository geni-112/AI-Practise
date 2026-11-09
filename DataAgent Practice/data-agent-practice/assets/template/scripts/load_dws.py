"""Load generated CSVs into an authorized DWS connection without replacing existing data."""
import os,csv,json
from pathlib import Path
import psycopg2
from psycopg2 import sql

ROOT=Path(__file__).resolve().parents[1]
def main():
    conn=psycopg2.connect(host=os.environ['DWS_HOST'],port=os.getenv('DWS_PORT','8000'),dbname=os.getenv('DWS_DATABASE','gaussdb'),user=os.environ['DWS_USER'],password=os.environ['DWS_PASSWORD'],sslmode=os.getenv('DWS_SSLMODE','verify-full'),sslrootcert=os.getenv('DWS_SSLROOTCERT'),connect_timeout=15)
    expected=json.loads((ROOT/'data/manifest.json').read_text())['tables'];count=0
    try:
        with conn.cursor() as cur:
            for namespace in ['internal','external','governance']:cur.execute(sql.SQL('CREATE SCHEMA IF NOT EXISTS {}').format(sql.Identifier(namespace)))
            for name,expected_count in expected.items():
                namespace='external' if name in ['ad_metrics','competitor_prices','reviews'] else 'governance' if name=='tenants' else 'internal'
                path=ROOT/'data'/f'{name}.csv'
                with path.open() as f:reader=csv.DictReader(f);fields=reader.fieldnames;rows=list(reader)
                columns=[]
                for field in fields:
                    values=[r[field] for r in rows if r[field]!=''];dtype='VARCHAR(1024)'
                    if values and all(v in ['True','False'] for v in values):dtype='BOOLEAN'
                    else:
                        try:
                            if values and all(float(v).is_integer() for v in values):dtype='BIGINT'
                            elif values and all(float(v)==float(v) for v in values):dtype='DECIMAL(18,2)'
                        except ValueError:pass
                    columns.append(sql.SQL('{} {}').format(sql.Identifier(field),sql.SQL(dtype)))
                ident=sql.Identifier(namespace,name)
                cur.execute(sql.SQL('CREATE TABLE IF NOT EXISTS {} ({}) DISTRIBUTE BY HASH (tenant_id)').format(ident,sql.SQL(',').join(columns)))
                cur.execute(sql.SQL('SELECT COUNT(*) FROM {}').format(ident));existing=cur.fetchone()[0]
                if existing==expected_count:count+=existing;continue
                if existing:raise RuntimeError(f'{namespace}.{name} is nonempty with an unexpected row count; refusing to truncate')
                with path.open() as f:cur.copy_expert(sql.SQL('COPY {} ({}) FROM STDIN WITH (FORMAT CSV, HEADER TRUE, NULL \'\')').format(ident,sql.SQL(',').join(map(sql.Identifier,fields))).as_string(conn),f)
                cur.execute(sql.SQL('SELECT COUNT(*) FROM {}').format(ident));actual=cur.fetchone()[0]
                if actual!=expected_count:raise RuntimeError(f'Row count mismatch in {name}')
                count+=actual
        conn.commit();print(json.dumps({'loaded_rows':count,'tables':len(expected),'synthetic':True}))
    except Exception:conn.rollback();raise
    finally:conn.close()

if __name__=='__main__':main()
