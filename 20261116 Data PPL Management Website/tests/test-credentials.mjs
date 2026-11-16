import {randomBytes} from 'node:crypto';
// Each integration test process owns its disposable initial credential.
export const INITIAL_PASSWORD = randomBytes(20).toString('hex');
