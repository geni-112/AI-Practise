import { createApplication } from './index.mjs';
// Startup creates missing accounts only. Re-running never resets a password.
const app=await createApplication();
console.log('Account initialization complete. New accounts must change their initial password at first sign-in. Existing passwords are preserved.');
await app.pool.end();
