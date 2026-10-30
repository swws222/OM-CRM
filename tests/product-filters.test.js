import {test} from 'node:test';
import assert from 'node:assert/strict';
import {filterProducts,supplierName,suppliersFor} from '../static/product-filters.js';
const rows=[{id:1,name:'Mleko',supplier:'MAXI',category:'Молочные',favorite:true},{id:2,name:'Hleb',supplier:'mojapijaca',category:'Хлеб и выпечка',favorite:true},{id:3,name:'Mleko drugo',supplier:'Denmark',category:'Молочные',favorite:false,supplier_sku:'ABC-123'},{id:4,name:'Voda',supplier:'Maxi (чек)',category:'Напитки',favorite:false,observation:{kind:'level',level:1}}];
test('supplier aliases select the intended supplier and include Denmark',()=>{assert.equal(filterProducts(rows,{supplier:'maxi'}).length,2);assert.equal(filterProducts(rows,{supplier:'Moja Pijaca'})[0].id,2);assert.equal(supplierName('denmark'),'Denmark');assert.ok(suppliersFor(rows).includes('Denmark'))});
test('category, supplier, favorites, low stock and search combine',()=>{assert.deepEqual(filterProducts(rows,{category:'Молочные',favorites:true}).map(p=>p.id),[1]);assert.equal(filterProducts(rows,{supplier:'Denmark',search:'abc-123'})[0].id,3);assert.equal(filterProducts(rows,{low:true})[0].id,4)});
test('no filters means all input items, an empty match is explicit',()=>{assert.equal(filterProducts(rows).length,4);assert.equal(filterProducts(rows,{supplier:'Denmark',favorites:true}).length,0)});
