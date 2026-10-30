import {waitForServer} from './browser-ready.mjs';
import {chromium} from 'playwright';
import {spawn} from 'node:child_process';
import {mkdtemp,rm,mkdir} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import assert from 'node:assert/strict';
const dir=await mkdtemp(tmpdir()+'/pantry-lists-');
const proc=spawn('python3',['server.py'],{env:{...process.env,PANTRY_DATA_DIR:dir,PORT:'8126'},stdio:'pipe'});
let browser;
try{
 await waitForServer('http://127.0.0.1:8126/api/state');
 browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
 const page=await browser.newPage({viewport:{width:1440,height:1000}});const errors=[];page.on('pageerror',e=>errors.push(e.message));const base='http://127.0.0.1:8126';
 const initial=await (await page.request.get(base+'/api/state')).json();const {id,...template}=initial.products[0];
 async function create(name,supplier,sku){const response=await page.request.post(base+'/api/product',{data:{...template,name,supplier,supplier_sku:sku,category:'Прочее',category_source:'auto',in_pantry:false,thresholds:[0,1,3,6,12,24]}});assert.ok(response.ok());return (await response.json()).id}
 const bread=await create('Hleb tost test 500g','denmark','BREAD-1');const milk=await create('Mleko test 1l','Maxi','MILK-1');await create('Banane test','mojapijaca','BANANA-1');
 await page.goto(base);await page.waitForSelector('.product');assert.equal(await page.locator('.product').count(),35);
 await page.click('[data-nav="products"]');await page.selectOption('#supplier-filter','Denmark');await page.selectOption('#category-filter','Хлеб и выпечка');assert.equal(await page.locator('#content tbody tr').count(),1);
 await page.locator(`[data-favorite="${bread}"]`).click();await page.waitForSelector(`[data-favorite="${bread}"][aria-pressed="true"]`);
 await page.reload();await page.waitForSelector('#supplier-filter');assert.equal(await page.locator('#supplier-filter').inputValue(),'Denmark');assert.equal(await page.locator(`[data-favorite="${bread}"]`).getAttribute('aria-pressed'),'true');
 await page.click('[data-nav="favorites"]');assert.equal(await page.locator('.product').count(),1);assert.equal(await page.locator('[data-level]').count(),0);
 await page.locator(`[data-pantry="${bread}"]`).click();await page.waitForSelector('[data-level]');
 await page.click('[data-nav="stock"]');assert.equal(await page.locator('.product').count(),1);await page.getByRole('button',{name:'Мало',exact:true}).click();await page.waitForSelector('.level.selected');
 await page.locator(`[data-favorite="${bread}"]`).click();await page.waitForSelector(`[data-favorite="${bread}"][aria-pressed="false"]`);
 await page.click('[data-nav="favorites"]');assert.equal(await page.locator('.product').count(),0);
 await page.click('[data-nav="products"]');await page.click('#reset-product-filters');await page.locator(`[data-favorite="${milk}"]`).click();await page.waitForSelector(`[data-favorite="${milk}"][aria-pressed="true"]`);
 await page.locator(`[data-edit="${milk}"]`).click();await page.selectOption('#edit-category','__new__');await page.fill('#custom-category','Breakfast picks');await page.locator('#modal-form').getByRole('button',{name:'Сохранить',exact:true}).click();await page.waitForSelector('dialog:not([open])',{state:'attached'});
 await page.selectOption('#category-filter','Breakfast picks');await page.check('#favorite-filter');assert.equal(await page.locator('#content tbody tr').count(),1);
 await page.click('[data-nav="favorites"]');assert.equal(await page.locator('.product').count(),1);assert.equal(await page.locator('[data-level]').count(),0);
 await mkdir('.runtime/screenshots',{recursive:true});await page.screenshot({path:'.runtime/screenshots/favorites.png'});
 await page.selectOption('#language','sr');await page.waitForFunction(()=>document.documentElement.lang==='sr-Latn');await page.waitForSelector('.product');assert.equal(await page.locator('#supplier-filter option[value="Denmark"]').count(),1);
 await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);await page.screenshot({path:'.runtime/screenshots/favorites-mobile-sr.png'});
 const final=await (await page.request.get(base+'/api/state')).json();const b=final.products.find(p=>p.id===bread),m=final.products.find(p=>p.id===milk);assert.ok(b.in_pantry);assert.equal(b.favorite,false);assert.equal(b.estimated_stock,3);assert.equal(m.in_pantry,false);assert.equal(m.favorite,true);assert.equal(m.category,'Breakfast picks');
 assert.deepEqual(errors,[]);
 console.log('Product-list browser passed: combined filters, Denmark, persistent favorites, independent pantry enrollment, counts, custom category, Serbian mobile view.');
}finally{if(browser)await browser.close();proc.kill();await rm(dir,{recursive:true,force:true})}
