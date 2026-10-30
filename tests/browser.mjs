import {waitForServer} from './browser-ready.mjs';
import {chromium} from 'playwright';
import {spawn} from 'node:child_process';
import {mkdtemp,rm,mkdir,readFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import assert from 'node:assert/strict';
const dir=await mkdtemp(tmpdir()+'/pantry-browser-');
const proc=spawn('python3',['server.py'],{env:{...process.env,PANTRY_DATA_DIR:dir,PORT:'8123'},stdio:'pipe'});
let browser;
try{
 await waitForServer('http://127.0.0.1:8123/api/state');
 browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
 const page=await browser.newPage({viewport:{width:1440,height:1000}});const errors=[];page.on('pageerror',e=>{errors.push(e.message);console.error('Browser error:',e.message)});
 await page.goto('http://127.0.0.1:8123');await page.waitForSelector('.product');assert.equal(await page.locator('.product').count(),35);
 await mkdir('.runtime/screenshots',{recursive:true});await page.screenshot({path:'.runtime/screenshots/desktop.png',fullPage:false});
 await page.locator('.product').first().getByRole('button',{name:'Нет',exact:true}).click();await page.waitForFunction(()=>document.querySelector('.product .level.selected')?.textContent==='Нет');
 await page.reload();await page.waitForSelector('.product .level.selected');assert.equal(await page.locator('.product .level.selected').first().textContent(),'Нет');
 await page.getByRole('button',{name:'План закупки',exact:false}).click();await page.waitForSelector('[data-qty="1"]');assert.ok(Number(await page.locator('[data-qty="1"]').inputValue())>0);
 await page.getByRole('button',{name:'Сохранить список',exact:true}).click();await page.waitForSelector('[data-saved-order]');
 await page.getByRole('button',{name:'Каталог',exact:false}).click();await page.getByRole('button',{name:'Добавить товар',exact:false}).click();
 await page.locator('[name="name"]').fill('Test proizvod');await page.locator('[name="rate"]').fill('0.1');await page.locator('#modal-form').getByRole('button',{name:'Сохранить',exact:true}).click();await page.waitForSelector('dialog:not([open])',{state:'attached'});
 await page.getByRole('button',{name:'Поступления',exact:false}).click();await page.getByRole('button',{name:'Добавить поставку',exact:false}).click();await page.locator('[name="number"]').fill('browser-test-1');await page.locator('[data-key="qty"]').fill('24');await page.getByRole('checkbox',{name:'Проверил позиции.',exact:false}).check();await page.getByRole('button',{name:'Подтвердить поступление'}).click();await page.waitForSelector('dialog:not([open])',{state:'attached'});assert.ok((await page.locator('tbody').textContent()).includes('browser-test-1'));
 await page.getByRole('button',{name:'Посещаемость',exact:false}).click();await page.getByRole('button',{name:'Добавить день',exact:false}).click();await page.locator('[name="count"]').fill('42');await page.locator('#modal-form').getByRole('button',{name:'Сохранить',exact:true}).click();await page.waitForSelector('dialog:not([open])',{state:'attached'});
 await page.locator('#office').selectOption('Нови-Сад');await page.getByRole('button',{name:'Остатки',exact:false}).click();assert.equal(await page.locator('.product').count(),0);
 await page.locator('#office').selectOption('Белград');await page.setViewportSize({width:390,height:844});await page.waitForSelector('.product');
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true);await page.screenshot({path:'.runtime/screenshots/mobile.png',fullPage:false});
 await page.goto('http://127.0.0.1:8123/?mode=staff');await page.waitForSelector('.product');assert.equal(await page.locator('[data-nav]').count(),2);assert.equal(await page.locator('[data-edit]').count(),0);assert.equal(await page.locator('#inventory').count(),0);

 // Language choice persists, Serbian names do not change with UI language.
 for(const [lang,stockText] of [['sr','Zalihe'],['en','Stock'],['ru','Остатки']]){
  await page.selectOption('#language',lang);await page.waitForFunction(l=>document.documentElement.lang===(l==='sr'?'sr-Latn':l),lang);await page.waitForSelector('.product');
  assert.equal(await page.locator('#language').inputValue(),lang);
  assert.ok((await page.locator('.nav').textContent()).includes(stockText));
  assert.equal(await page.locator('.product-name').first().textContent(),'Argeta pašteta');
  if(lang!=='ru'){const text=await page.locator('#content').innerText();assert.equal(/[А-Яа-яЁё]/.test(text),false,text.match(/.{0,30}[А-Яа-яЁё].{0,50}/g)?.join('\n'));}
 }
 await page.goto('http://127.0.0.1:8123/');await page.waitForSelector('[data-nav="products"]');await page.click('[data-nav="products"]');
 await page.click('#supplier-catalog');await page.waitForSelector('#catalog-file',{state:'attached'});
 const imported={products:[{name:'Mleko original TEST 1 l',sku:'E2E-1',url:'https://www.maxi.rs/p/E2E-1',unit:'kom'}]};
 await page.locator('#catalog-file').setInputFiles({name:'products.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(imported))});
 await page.waitForSelector('[name="row"]');await page.getByRole('checkbox',{name:'Подтверждаю выбор товаров и источник данных'}).check();await page.getByRole('button',{name:'Подтвердить выбранные'}).click();await page.waitForSelector('dialog:not([open])',{state:'attached'});
 await page.click('#supplier-catalog');await page.waitForSelector('[data-select-catalog]');await page.locator('[data-select-catalog]').first().click();
 await page.selectOption('[name="product_id"]','1');await page.locator('#modal-form').getByRole('button',{name:'Сохранить',exact:true}).click();await page.waitForSelector('dialog:not([open])',{state:'attached'});
 const live=await (await page.request.get('http://127.0.0.1:8123/api/state')).json();assert.equal(live.products.find(p=>p.id===1).name,'Mleko original TEST 1 l');assert.ok(live.products.find(p=>p.id===1).rate>0);
 // All five screens remain usable in Serbian and English.
 for(const lang of ['sr','en']){
  await page.selectOption('#language',lang);await page.waitForFunction(l=>document.documentElement.lang===(l==='sr'?'sr-Latn':l),lang);await page.waitForSelector('[data-nav]');
  for(const id of ['stock','products','order','deliveries','attendance']){await page.click(`[data-nav="${id}"]`);await page.waitForSelector('h1');assert.ok((await page.locator('h1').textContent()).length>2)}
  await page.click('[data-nav="stock"]');assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  await page.screenshot({path:`.runtime/screenshots/mobile-${lang}.png`});
 }

 // Exporter fixture: no live store access is required, source names/SKUs are preserved.
 const exporter=await readFile('static/supplier-exporter.js','utf8');
 const fixture=await browser.newPage();fixture.on('dialog',d=>d.accept());
 await fixture.setContent('<script type="application/ld+json">'+JSON.stringify({'@type':'Product',name:'Izvorni naziv testa 250 g',sku:'FIXTURE-25',url:'https://www.maxi.rs/p/FIXTURE-25'})+'</script>');
 const downloading=fixture.waitForEvent('download');
 await fixture.evaluate(code=>new Function('location',code)({hostname:'www.maxi.rs',href:'https://www.maxi.rs/test-fixture'}),exporter);
 const exported=JSON.parse(await readFile(await (await downloading).path(),'utf8'));assert.equal(exported.products[0].name,'Izvorni naziv testa 250 g');assert.equal(exported.products[0].sku,'FIXTURE-25');await fixture.close();
 assert.deepEqual(errors,[]);
 console.log('Browser checks passed: seeded catalogue, persistent stock, forecast, saved list, product creation, delivery, attendance, office isolation, mobile layout.');
}finally{if(browser)await browser.close();proc.kill();await rm(dir,{recursive:true,force:true})}
