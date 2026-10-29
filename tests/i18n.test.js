import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {parse} from '@babel/parser';
const dictionaries=Object.fromEntries(['sr','en'].map(lang=>[lang,JSON.parse(readFileSync(`static/locales/${lang}.json`))]));
function walk(node,fn){if(!node||typeof node!=='object')return;fn(node);for(const value of Object.values(node)){if(Array.isArray(value))value.forEach(n=>walk(n,fn));else if(value&&typeof value==='object')walk(value,fn)}}
test('all literal interface keys have Serbian and English translations',()=>{
 const keys=new Set();walk(parse(readFileSync('static/app.js','utf8'),{sourceType:'module'}),n=>{if(n.type==='CallExpression'&&['t','label'].includes(n.callee.name)&&n.arguments[0]?.type==='StringLiteral')keys.add(n.arguments[0].value)});
 for(const lang of ['sr','en'])for(const key of keys)assert.ok(dictionaries[lang][key],`${lang}: ${key}`);
});
test('Serbian UI uses Latin script and English UI does not contain Cyrillic',()=>{for(const [lang,d] of Object.entries(dictionaries))for(const [key,value] of Object.entries(d))assert.ok(!/[А-Яа-яЁё]/.test(value),`${lang}: ${key}`)});
