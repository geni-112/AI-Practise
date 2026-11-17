import mysql from 'mysql2/promise';
import fs from 'node:fs/promises';
import { createHash } from 'node:crypto';

// Keep domain SQL parameterized; adapters share one connection per transaction.
export function database(client) {
  const convert = sql => {
    return sql.replace(/^INSERT OR IGNORE /i, 'INSERT IGNORE ')
      .replace('ON CONFLICT(email) DO UPDATE SET role_id=excluded.role_id,enabled=excluded.enabled', 'ON DUPLICATE KEY UPDATE role_id=VALUES(role_id),enabled=VALUES(enabled),version=version+1');
  };
  return {
    prepare(sql) {
      const query = convert(sql);
      const statement = params => ({
        bind: (...values) => statement(values),
        async first() { return (await client.query(query, params)).rows[0] ?? null; },
        async all() { return { results: (await client.query(query, params)).rows }; },
        async run() { const result = await client.query(query, params); return { meta: { changes: result.rowCount ?? result.affectedRows ?? 0 } }; }
      });
      return statement([]);
    },
    async batch(statements) { const results = []; for (const statement of statements) results.push(await statement.run()); return results; }
  };
}

export function adaptConnection(connection) {
  return {
    async query(sql, values = []) {
      const bound = [], hasNumbered = /\$\d+/.test(sql);
      sql = sql.replace(/\$(\d+)/g, (_, index) => { bound.push(values[Number(index)-1]); return '?'; });
      const params=hasNumbered?bound:values;
      const [rows] = /^(START|COMMIT|ROLLBACK|SET|CREATE|ALTER|DROP)\b/i.test(sql.trim()) && !params.length
        ? await connection.query(sql) : await connection.execute(sql,params);
      return { rows:Array.isArray(rows) ? rows : [], rowCount:rows.affectedRows ?? rows.length };
    },
    release: () => connection.release()
  };
}
export function createPool(config) {
  for (const key of ['DB_HOST','DB_USER','DB_PASSWORD','DB_NAME']) if (!config[key]) throw new Error(`${key} is required`);
  const raw = mysql.createPool({host:config.DB_HOST, port:Number(config.DB_PORT||3306), user:config.DB_USER, password:config.DB_PASSWORD,
    database:config.DB_NAME, connectionLimit:6, waitForConnections:true, queueLimit:30, charset:'utf8mb4', timezone:'Z',
    dateStrings:true, multipleStatements:false, connectTimeout:10000,
    ssl:config.DB_SSL_CA ? { ca:config.DB_SSL_CA, rejectUnauthorized:true } : undefined });
  return { connect:async()=>adaptConnection(await raw.getConnection()), end:()=>raw.end() };
}

export async function transaction(pool, fn, readOnly = false, commitErrors = false) {
  const client = await pool.connect();
  try {
    await client.query('SET TRANSACTION ISOLATION LEVEL READ COMMITTED');
    await client.query('START TRANSACTION');
    const result = await fn(client);
    if (!commitErrors && result instanceof Response && result.status >= 400) await client.query('ROLLBACK');
    else await client.query('COMMIT');
    return result;
  } catch (error) { await client.query('ROLLBACK'); throw error; }
  finally { client.release(); }
}

export async function migrate(pool) {
  const client = await pool.connect();
  try {
    const lock = (await client.query("SELECT GET_LOCK('navigator_migrate',30) AS acquired")).rows[0];
    if (Number(lock.acquired)!==1) throw new Error('Could not acquire migration lock');
    await client.query('CREATE TABLE IF NOT EXISTS schema_migrations (name VARCHAR(190) PRIMARY KEY, checksum CHAR(64) NOT NULL, applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP) ENGINE=InnoDB');
    const directory = new URL('../migrations/', import.meta.url);
    for (const name of (await fs.readdir(directory)).filter(x => x.endsWith('.sql')).sort()) {
      const sql = await fs.readFile(new URL(name, directory), 'utf8');
      const normalized=sql.replace(/\r\n/g,'\n');
      const hash=value=>createHash('sha256').update(value).digest('hex');
      const checksum=hash(normalized);
      const validChecksums=new Set([checksum,hash(normalized.replace(/\n/g,'\r\n'))]);
      const existing = (await client.query('SELECT checksum FROM schema_migrations WHERE name=$1', [name])).rows[0];
      if (existing && !validChecksums.has(existing.checksum)) throw new Error(`Applied migration changed: ${name}`);
      if (!existing) {
        // MySQL DDL commits implicitly; every statement is restart-safe.
        for (const statement of sql.split(';').map(s=>s.trim()).filter(Boolean)) await client.query(statement);
        await client.query('INSERT INTO schema_migrations(name,checksum) VALUES($1,$2)', [name, checksum]);
      }
    }
  } finally { await client.query("SELECT RELEASE_LOCK('navigator_migrate')"); client.release(); }
}
