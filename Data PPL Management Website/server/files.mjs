import fs from 'node:fs/promises';
import path from 'node:path';
import { Readable } from 'node:stream';
import { createReadStream } from 'node:fs';

export function fileStore(directory) {
  const root = path.resolve(directory);
  function target(key) {
    if (!/^resources\/[a-f0-9-]{36}$/.test(key)) throw new Error('Invalid file key');
    return path.join(root, key);
  }
  return {
    async put(key, bytes) {
      const file = target(key);
      await fs.mkdir(path.dirname(file), { recursive: true, mode: 0o700 });
      const handle = await fs.open(file, 'wx', 0o600);
      try { await handle.writeFile(bytes); await handle.sync(); } finally { await handle.close(); }
    },
    async get(key) {
      const file = target(key);
      try { await fs.access(file); return { body: Readable.toWeb(createReadStream(file)) }; }
      catch (error) { if (error.code === 'ENOENT') return null; throw error; }
    },
    async delete(key) { await fs.rm(target(key), { force: true }); }
  };
}
