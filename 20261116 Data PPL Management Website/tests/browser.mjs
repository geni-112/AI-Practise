import { chromium } from '@playwright/test';
import { createApplication, httpServer } from '../server/index.mjs';
import { hashPassword } from '../server/auth.mjs';
import { transaction } from '../server/database.mjs';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { randomUUID } from 'node:crypto';

import {INITIAL_PASSWORD} from './test-credentials.mjs';
const env={INITIAL_ACCOUNT_PASSWORD:INITIAL_PASSWORD,DB_HOST:'127.0.0.1',DB_PORT:'13306',DB_USER:'navigator_test',DB_PASSWORD:'test-password-only',DB_NAME:'navigator_test',ADMIN_EMAIL:'owner@test.local',APP_ORIGIN:'http://127.0.0.1:3100',UPLOAD_DIR:fileURLToPath(new URL('../.data/test-uploads/',import.meta.url))};
const app=await createApplication({env});
await transaction(app.pool,async c=>{await c.query('DELETE FROM login_limits');await c.query('UPDATE accounts SET password_hash=$1 WHERE email=$2',[await hashPassword('Browser-test-password'),env.ADMIN_EMAIL]);await c.query('UPDATE account_password_state SET must_change_password=0 WHERE email=$1',[env.ADMIN_EMAIL]);});
const server=httpServer(app);await new Promise(resolve=>server.listen(3100,'127.0.0.1',resolve));
const browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage({viewport:{width:1440,height:1000},locale:'zh-CN'});
const errors=[];page.on('pageerror',e=>errors.push(e.message));
await fs.mkdir('artifacts',{recursive:true});
try{
 await page.goto(env.APP_ORIGIN+'/');await page.getByLabel('邮箱',{exact:true}).fill(env.ADMIN_EMAIL);await page.getByLabel('密码',{exact:true}).fill('Browser-test-password');await page.getByRole('button',{name:'登录'}).click();
 await page.getByRole('button',{name:'新建项目'}).waitFor();
 await page.getByRole('button',{name:'新建项目'}).click();await page.locator('input[name=name]').fill('浏览器验证 '+Date.now());await page.locator('input[name=repo]').fill('智利');await page.getByRole('button',{name:'保存',exact:true}).click();await page.locator('#modal').waitFor({state:'hidden'});
 await page.getByRole('button',{name:'项目运作',exact:false}).click();await page.getByPlaceholder('搜索项目、代表处或资料').fill('浏览器验证');await page.locator('tbody tr').first().click();await page.locator('input[name=next]').fill('与客户确认验证范围');await page.getByRole('button',{name:'保存',exact:true}).click();await page.locator('#modal').waitFor({state:'hidden'});
 await page.reload();await page.getByRole('button',{name:'项目运作',exact:false}).click();await page.getByPlaceholder('搜索项目、代表处或资料').fill('浏览器验证');assert.match(await page.locator('#results').innerText(),/与客户确认验证范围/);
 await page.getByRole('button',{name:'工作台总览',exact:false}).click();await page.screenshot({path:'artifacts/desktop.png',fullPage:true});
 await page.getByRole('button',{name:'报表中心',exact:false}).click();await page.locator('#reportBody .reporthead').waitFor();
 await page.getByRole('button',{name:'成员与角色',exact:false}).click();await page.locator('#members .listrow').first().waitFor();
 await page.setViewportSize({width:390,height:844});await page.getByRole('button',{name:'工作台总览',exact:false}).click();await page.screenshot({path:'artifacts/mobile.png',fullPage:true});
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth),false,'no page-level mobile overflow');
 await page.getByRole('button',{name:'退出',exact:true}).click();await page.getByRole('heading',{name:'登录工作空间'}).waitFor();await page.screenshot({path:'artifacts/login.png',fullPage:true});
 assert.deepEqual(errors,[]);console.log('PASS: real browser login, project creation/edit/reload persistence, reports, members, logout, mobile layout; zero uncaught page errors');
}finally{await browser.close();await new Promise(resolve=>server.close(resolve));await app.pool.end()}
