import {chromium} from 'playwright';
import {spawn} from 'node:child_process';
import {mkdtemp,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import assert from 'node:assert/strict';
const dir=await mkdtemp(tmpdir()+'/pantry-bulk-');
const proc=spawn('python3',['server.py'],{env:{...process.env,PANTRY_DATA_DIR:dir,PORT:'8125'},stdio:'pipe'});
let browser;
try{
 for(let i=0;i<60;i++){try{if((await fetch('http://127.0.0.1:8125/api/state')).ok)break}catch{}await new Promise(r=>setTimeout(r,100))}
 browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
 const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:8125');await page.waitForSelector('.product');
 const base='http://127.0.0.1:8125';const initial=await (await page.request.get(base+'/api/state')).json();
 const image='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aSc8AAAAASUVORK5CYII=';
 const products=Array.from({length:725},(_,i)=>({name:'Maxi proizvod '+i,sku:'BULK-'+i,url:'https://www.maxi.rs/p/BULK-'+i,image,unit:'kom'}));
 const files=Array.from({length:74},(_,i)=>({name:`products-${String(i+1).padStart(3,'0')}.json`,mimeType:'application/json',buffer:Buffer.from(JSON.stringify({supplier:'Maxi',products:products.slice(Math.floor(i*725/74),Math.floor((i+1)*725/74))}))}));
 files.push({name:'report.json',mimeType:'application/json',buffer:Buffer.from('{}')});
 async function prepare(){await page.click('[data-nav="products"]');await page.click('#supplier-catalog');await page.click('#replace-catalog-files');await page.locator('#catalog-file').setInputFiles(files);await page.waitForSelector('#catalog-import-mode',{timeout:60000})}
 await prepare();assert.equal(await page.locator('[name="row"]').count(),725);assert.equal(await page.locator('#catalog-import-mode').inputValue(),'replace');
 assert.equal((await (await page.request.get(base+'/api/state')).json()).products.length,35);
 await page.getByRole('checkbox',{name:'Подтверждаю выбор товаров и источник данных'}).check();
 // A failed request must leave the old office catalogue intact and allow a retry.
 let failed=false;
 await page.route('**/api/catalog/import',async route=>{if(!failed){failed=true;await route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:'Temporary failure'})})}else await route.continue()});
 await page.getByRole('button',{name:'Подтвердить выбранные'}).click();await page.waitForFunction(()=>document.querySelector('#catalog-import-status')?.textContent.includes('Повторите'));
 assert.equal((await (await page.request.get(base+'/api/state')).json()).products.length,35);
 await page.getByRole('button',{name:'Подтвердить выбранные'}).click();await page.waitForSelector('dialog:not([open])',{state:'attached',timeout:60000});
 const state=await (await page.request.get(base+'/api/state')).json();const current=state.products.filter(p=>!p.archived);assert.equal(current.length,725);assert.equal(state.products.filter(p=>p.archived).length,35);
 assert.deepEqual(state.observations,initial.observations);assert.deepEqual(state.deliveries,initial.deliveries);
 assert.ok(current.every(p=>p.image.startsWith('/assets/catalog/')));
 assert.equal(await page.locator('#content tbody tr').count(),725);
 await page.click('#show-archived');assert.equal(await page.locator('#content tbody tr').count(),35);await page.click('#show-archived');
 await page.click('[data-nav="stock"]');await page.waitForSelector('.product img');assert.equal(await page.locator('.product').count(),725);
 await page.locator('.product img').first().scrollIntoViewIfNeeded();await page.waitForFunction(()=>{const image=document.querySelector('.product img');return image?.complete&&image.naturalWidth>0});
 // Editing a product with a locally stored photo must not fail URL form validation.
 await page.locator('[data-edit]').first().click();assert.equal(await page.locator('[name="image"]').inputValue(),'');assert.equal(await page.locator('#modal-form').evaluate(form=>form.checkValidity()),true);await page.locator('.close').click();
 assert.deepEqual(errors,[]);
 console.log('Bulk browser passed: 74 files + report, 725 products, retry, atomic replacement, archived history, visible local photos.');
}finally{if(browser)await browser.close();proc.kill();await rm(dir,{recursive:true,force:true})}
