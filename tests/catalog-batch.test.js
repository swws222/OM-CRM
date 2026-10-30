import {test} from 'node:test';
import assert from 'node:assert/strict';
import {importFiles,importBatches,mergeCatalogRows} from '../static/catalog-batch.js';
test('selects all 74 export files while excluding report and images',()=>{
 const files=Array.from({length:74},(_,i)=>({name:`products-${String(i+1).padStart(3,'0')}.json`}));
 const selected=importFiles([...files.reverse(),{name:'report.json'},{name:'photo.jpg'}]);assert.equal(selected.length,74);assert.equal(selected[0].name,'products-001.json');assert.equal(selected.at(-1).name,'products-074.json');
});
test('deduplicates supplier IDs and URLs across files',()=>{
 const a={external_key:'sku:1',url:'https://www.maxi.rs/p/1'};
 assert.equal(mergeCatalogRows([a,{...a},{external_key:'url:1',url:a.url},{external_key:'sku:2',url:'https://www.maxi.rs/p/2'}]).length,2);
});
test('splits photos into bounded UTF-8 requests without losing or duplicating rows',()=>{
 const rows=Array.from({length:725},(_,i)=>({name:'Čeri парадајз '+i,sku:String(i),image:'a'.repeat(200)}));
 const batches=importBatches(rows,'Maxi','job',2000);assert.ok(batches.length>1);assert.deepEqual(batches.flat(),rows);
 for(const part of batches)assert.ok(new TextEncoder().encode(JSON.stringify({supplier:'Maxi',job_id:'job',rows:part})).length<=2000);
});
test('refuses a single oversized photo instead of exceeding the server limit',()=>assert.throws(()=>importBatches([{image:'a'.repeat(2000)}],'Maxi','job',1000)));
