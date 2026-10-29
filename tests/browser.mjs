import {chromium} from 'playwright';
import {spawn} from 'node:child_process';
import {mkdtemp,rm,mkdir} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import assert from 'node:assert/strict';
const dir=await mkdtemp(tmpdir()+'/pantry-browser-');
const proc=spawn('python3',['server.py'],{env:{...process.env,PANTRY_DATA_DIR:dir,PORT:'8123'},stdio:'pipe'});
let browser;
try{
 for(let i=0;i<60;i++){try{if((await fetch('http://127.0.0.1:8123/api/state')).ok)break}catch{}await new Promise(r=>setTimeout(r,100))}
 browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
 const page=await browser.newPage({viewport:{width:1440,height:1000}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:8123');await page.waitForSelector('.product');assert.equal(await page.locator('.product').count(),35);
 await mkdir('.runtime/screenshots',{recursive:true});await page.screenshot({path:'.runtime/screenshots/desktop.png',fullPage:false});
 await page.locator('.product').first().getByRole('button',{name:'Нет',exact:true}).click();await page.waitForFunction(()=>document.querySelector('.product .level.selected')?.textContent==='Нет');
 await page.reload();await page.waitForSelector('.product .level.selected');assert.equal(await page.locator('.product .level.selected').first().textContent(),'Нет');
 await page.getByRole('button',{name:'План закупки',exact:false}).click();await page.waitForSelector('[data-qty="1"]');assert.ok(Number(await page.locator('[data-qty="1"]').inputValue())>0);
 await page.getByRole('button',{name:'Сохранить список',exact:true}).click();await page.waitForSelector('[data-saved-order]');
 await page.getByRole('button',{name:'Каталог',exact:false}).click();await page.getByRole('button',{name:'Добавить товар',exact:false}).click();
 await page.locator('[name="name"]').fill('Тестовый продукт');await page.locator('[name="rate"]').fill('0.1');await page.locator('#modal-form').getByRole('button',{name:'Сохранить',exact:true}).click();await page.waitForSelector('dialog:not([open])',{state:'attached'});
 await page.getByRole('button',{name:'Поступления',exact:false}).click();await page.getByRole('button',{name:'Добавить поставку',exact:false}).click();await page.locator('[name="number"]').fill('browser-test-1');await page.locator('[data-key="qty"]').fill('24');await page.getByRole('checkbox',{name:'Проверил позиции.',exact:false}).check();await page.getByRole('button',{name:'Подтвердить поступление'}).click();await page.waitForSelector('dialog:not([open])',{state:'attached'});assert.ok((await page.locator('tbody').textContent()).includes('browser-test-1'));
 await page.getByRole('button',{name:'Посещаемость',exact:false}).click();await page.getByRole('button',{name:'Добавить день',exact:false}).click();await page.locator('[name="count"]').fill('42');await page.locator('#modal-form').getByRole('button',{name:'Сохранить',exact:true}).click();await page.waitForSelector('dialog:not([open])',{state:'attached'});
 await page.locator('#office').selectOption('Нови-Сад');await page.getByRole('button',{name:'Остатки',exact:false}).click();assert.equal(await page.locator('.product').count(),0);
 await page.locator('#office').selectOption('Белград');await page.setViewportSize({width:390,height:844});await page.waitForSelector('.product');
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true);await page.screenshot({path:'.runtime/screenshots/mobile.png',fullPage:false});
 await page.goto('http://127.0.0.1:8123/?mode=staff');await page.waitForSelector('.product');assert.equal(await page.locator('[data-nav]').count(),1);assert.equal(await page.locator('[data-edit]').count(),0);assert.equal(await page.locator('#inventory').count(),0);
 assert.deepEqual(errors,[]);
 console.log('Browser checks passed: seeded catalogue, persistent stock, forecast, saved list, product creation, delivery, attendance, office isolation, mobile layout.');
}finally{if(browser)await browser.close();proc.kill();await rm(dir,{recursive:true,force:true})}
