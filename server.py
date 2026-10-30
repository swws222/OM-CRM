#!/usr/bin/env python3
"""Office Pantry MVP: Python 3.11+, SQLite, no third-party runtime dependencies."""
import base64
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import secrets
import sqlite3
import uuid
import re
from zoneinfo import ZoneInfo
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
import catalog
import taxonomy
import purchasing

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get('PANTRY_DATA_DIR', ROOT / '.runtime'))
OFFICES = ['Белград', 'Нови-Сад']
LEVELS = ['Нет', 'Очень мало', 'Мало', 'Средне', 'Много', 'Очень много']

def supplier_key(value): return ' '.join(value.replace(' (чек)','').split()).casefold()
def invoice_key(value): return ' '.join(value.split()).casefold()

def now(): return dt.datetime.now(dt.timezone.utc).isoformat()
def current_day(): return dt.datetime.now(ZoneInfo('Europe/Belgrade')).date().isoformat()
def num(v, name='Число', minimum=0, nullable=False):
    if nullable and (v is None or v == ''): return None
    try: n=float(v)
    except (TypeError,ValueError): raise ValueError(f'{name}: введите число')
    if not math.isfinite(n) or n < minimum or n > 1e9: raise ValueError(f'{name}: недопустимое значение')
    return n

def day(v):
    try: return dt.date.fromisoformat(v).isoformat()
    except (ValueError,TypeError): raise ValueError('Дата должна быть в формате YYYY-MM-DD')
def office(v):
    if v not in OFFICES: raise ValueError('Неизвестный офис')
    return v

def connect():
    DATA.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(DATA/'pantry.sqlite',timeout=20)
    c.row_factory=sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    return c

def log(c,action,kind,id,before=None,after=None):
    c.execute('INSERT INTO audit(at,action,kind,entity_id,before_json,after_json) VALUES(?,?,?,?,?,?)',(now(),action,kind,str(id),json.dumps(before,ensure_ascii=False),json.dumps(after,ensure_ascii=False)))

def init():
    with connect() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS observations(id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES products(id), date TEXT NOT NULL, kind TEXT NOT NULL, qty REAL, level INTEGER, note TEXT, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS deliveries(id INTEGER PRIMARY KEY, office TEXT NOT NULL,supplier TEXT NOT NULL,number TEXT NOT NULL,date TEXT NOT NULL,data TEXT NOT NULL, UNIQUE(office,supplier,number));
        CREATE TABLE IF NOT EXISTS attendance(office TEXT NOT NULL,date TEXT NOT NULL,count INTEGER NOT NULL,notes TEXT,PRIMARY KEY(office,date));
        CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,at TEXT,action TEXT,kind TEXT,entity_id TEXT,before_json TEXT,after_json TEXT);
        CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT);
        CREATE TABLE IF NOT EXISTS supplier_catalog(id INTEGER PRIMARY KEY,supplier TEXT NOT NULL,external_key TEXT NOT NULL,data TEXT NOT NULL,url TEXT NOT NULL DEFAULT '',name_search TEXT NOT NULL DEFAULT '',UNIQUE(supplier,external_key));
        CREATE TABLE IF NOT EXISTS catalog_import_jobs(id TEXT PRIMARY KEY,data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS trial_proposals(id INTEGER PRIMARY KEY,product_id INTEGER NOT NULL REFERENCES products(id),office TEXT NOT NULL,status TEXT NOT NULL,note TEXT NOT NULL,created_at TEXT NOT NULL,decided_at TEXT,order_id INTEGER REFERENCES orders(id),decision_note TEXT);
        CREATE UNIQUE INDEX IF NOT EXISTS one_pending_trial ON trial_proposals(product_id) WHERE status='pending';
        ''')
        columns={r[1] for r in c.execute('PRAGMA table_info(supplier_catalog)')}
        if not {'url','name_search'}.issubset(columns):
            c.execute('BEGIN IMMEDIATE')
            for col in ('url','name_search'):
                if col not in columns:c.execute(f"ALTER TABLE supplier_catalog ADD COLUMN {col} TEXT NOT NULL DEFAULT ''")
            for row in c.execute('SELECT id,data FROM supplier_catalog').fetchall():
                item=json.loads(row['data']);c.execute('UPDATE supplier_catalog SET url=?,name_search=? WHERE id=?',(item.get('url',''),(item['name']+' '+item.get('sku','')).casefold(),row['id']))
        c.execute('CREATE INDEX IF NOT EXISTS supplier_catalog_url ON supplier_catalog(supplier,url)')
        if not c.execute("SELECT 1 FROM meta WHERE key='seeded'").fetchone():
            seed=json.loads((ROOT/'data/seed.json').read_text())
            for p in seed['products']:
                p={**p,'office':'Белград','active':True}
                c.execute('INSERT INTO products(id,data) VALUES(?,?)',(p['id'],json.dumps(p,ensure_ascii=False)))
                c.execute('INSERT INTO observations(product_id,date,kind,qty,note,created_at) VALUES(?,?,?,?,?,?)',(p['id'],seed['stock_date'],'estimate',p['stock'],p['source_note']+f" Диапазон: {p['stock_min']}–{p['stock_max']}.",now()))
            for d in seed['deliveries']:
                c.execute('INSERT INTO deliveries(office,supplier,number,date,data) VALUES(?,?,?,?,?)',(d['office'],supplier_key(d['supplier']),invoice_key(d['number']),d['date'],json.dumps(d,ensure_ascii=False)))
            for a in seed['attendance']:
                c.execute('INSERT INTO attendance VALUES(?,?,?,?)',(a['office'],a['date'],a['count'],a['notes']))
            c.execute("INSERT INTO meta VALUES('seeded','1')")
        names=json.loads((ROOT/'data/serbian_names.json').read_text())
        observed={r[0] for r in c.execute('SELECT DISTINCT product_id FROM observations')}
        received=set()
        for row in c.execute('SELECT data FROM deliveries'):
            received.update(l['product_id'] for l in json.loads(row[0])['lines'])
        for r in c.execute('SELECT id,data FROM products').fetchall():
            p=json.loads(r['data']);old=p.copy()
            if p['name'] in names and 'name_status' not in p:
                p['legacy_name']=p['name'];p['name']=names[p['name']];p['name_status']='provisional'
            if 'in_pantry' not in p:p['in_pantry']=not p.get('archived',False) and (r['id'] in observed or r['id'] in received)
            purchasing.normalize(p)
            if 'favorite' not in p:p['favorite']=False
            p['supplier']=taxonomy.canonical_supplier(p['supplier'])
            if p.get('category_source')!='manual' and (p.get('catalog_id') or p.get('name_status') in ('supplier_import','provisional')):
                p.update(taxonomy.category_fields(p['name'],p.get('category'),p.get('category_source')))
            if p!=old:
                c.execute('UPDATE products SET data=? WHERE id=?',(json.dumps(p,ensure_ascii=False),r['id']))
                log(c,'migrate','product',r['id'],old,p)
        for r in c.execute('SELECT id,data FROM deliveries').fetchall():
            d=json.loads(r['data'])
            c.execute('UPDATE deliveries SET supplier=?,number=? WHERE id=?',(supplier_key(d['supplier']),invoice_key(d['number']),r['id']))

def state(c):
    products=[dict(json.loads(r['data']),id=r['id']) for r in c.execute('SELECT * FROM products')]
    observations=[dict(r) for r in c.execute('SELECT * FROM observations ORDER BY date,id')]
    deliveries=[dict(json.loads(r['data']),id=r['id']) for r in c.execute('SELECT * FROM deliveries ORDER BY date DESC,id DESC')]
    for p in products:
        obs=[o for o in observations if o['product_id']==p['id']]
        latest=obs[-1] if obs else None
        qty=None
        if latest:
            qty=p['thresholds'][latest['level']] if latest['kind']=='level' else latest['qty']
            qty+=sum(line['qty'] for d in deliveries if d['office']==p['office'] and latest['date']<d['date'] for line in d['lines'] if line['product_id']==p['id'])
        p['observation']=latest; p['estimated_stock']=qty;p['photo_status']=photo_status(p.get('image',''))
    return dict(products=products,observations=observations,deliveries=deliveries,attendance=[dict(r) for r in c.execute('SELECT * FROM attendance ORDER BY date DESC')],orders=[dict(json.loads(r['data']),id=r['id'],created_at=r['created_at']) for r in c.execute('SELECT * FROM orders ORDER BY id DESC')],offices=OFFICES,levels=LEVELS,categories=taxonomy.CATEGORIES,suppliers=taxonomy.SUPPLIERS,proposals=[dict(r) for r in c.execute('SELECT * FROM trial_proposals ORDER BY id DESC')])

def calibration(s,pid):
    p=next(p for p in s['products'] if p['id']==pid)
    anchors=[o for o in s['observations'] if o['product_id']==pid and o['kind']=='exact']
    if len(anchors)<2: return dict(error='Нужны две точные инвентаризации в разные дни. Оценки по фото и кнопки не являются точными остатками.')
    a,b=anchors[-2:]
    if a['date']==b['date']: return dict(error='Инвентаризации должны быть в разные дни.')
    attendance={a['date']:a['count'] for a in s['attendance'] if a['office']==p['office']}
    dates=[]; current=dt.date.fromisoformat(a['date'])+dt.timedelta(days=1); end=dt.date.fromisoformat(b['date'])
    while current<=end:
        if current.weekday()<5: dates.append(current.isoformat())
        current+=dt.timedelta(days=1)
    missing=[d for d in dates if d not in attendance]
    visits=sum(v for k,v in attendance.items() if a['date']<k<=b['date'])
    received=sum(l['qty'] for d in s['deliveries'] if d['office']==p['office'] and a['date']<d['date']<=b['date'] for l in d['lines'] if l['product_id']==pid)
    used=a['qty']+received-b['qty']
    if missing: return dict(error=f'Не заполнена посещаемость за {len(missing)} будних дней',missing=missing)
    if visits<=0 or used<0: return dict(error='Нельзя рассчитать норму: нет посещений или расход отрицательный. Проверьте поступления и остатки.')
    return dict(rate=used/visits,used=used,received=received,visits=visits,start=a['date'],end=b['date'],note='Убыль включает списания. Все поставки периода должны быть внесены. Остатки фиксируются на конец дня.')

def save_product(c,b,id=None):
    old=None
    if id:
        r=c.execute('SELECT data FROM products WHERE id=?',(id,)).fetchone()
        if not r: raise ValueError('Товар не найден')
        old=json.loads(r[0])
    p={k:b.get(k) for k in ['name','supplier','category','unit','office','image','url','notes','rate_source']}
    for k in ('name','supplier','category','unit'):
        if not isinstance(p[k],str) or not p[k].strip(): raise ValueError(f'Заполните поле {k}')
        p[k]=p[k].strip()[:250]
    p['supplier']=taxonomy.canonical_supplier(p['supplier'])
    p['favorite']=bool((old or {}).get('favorite',b.get('favorite',False)))
    p['in_pantry']=bool(b.get('in_pantry',(old or {}).get('in_pantry',False)))
    p['purchase_policy']=b.get('purchase_policy',(old or {}).get('purchase_policy','regular' if p['in_pantry'] else 'catalog'))
    if p['purchase_policy'] not in purchasing.POLICIES:raise ValueError('Неизвестный статус закупки')
    p['trial_received']=bool((old or {}).get('trial_received',False))
    if old and p['purchase_policy']!=old.get('purchase_policy'):
        p['in_pantry']=old.get('in_pantry',False)
        purchasing.change_policy(p,p['purchase_policy'])
    else:purchasing.normalize(p)
    for key in ('policy_reason','policy_changed_at'):
        if key in (old or {}):p[key]=old[key]
    source=b.get('category_source',(old or {}).get('category_source'))
    if old and p['category']!=old.get('category'):source='manual'
    p.update(taxonomy.category_fields(p['name'],p['category'],source))
    p['legacy_name']=(old or {}).get('legacy_name','')
    p['catalog_id']=(old or {}).get('catalog_id')
    p['name_status']=(old or {}).get('name_status','manual')
    if old and p['name']!=old['name']:p['name_status']='manual'
    p['supplier_sku']=str(b.get('supplier_sku',(old or {}).get('supplier_sku','')) or '').strip()[:150]
    p['office']=office(p['office'])
    if old and old['office']!=p['office']: raise ValueError('Для другого офиса создайте отдельную карточку')
    for k in ('image','url'):
        p[k]=p[k] or ''
        if p[k] and not p[k].startswith(('https://','/assets/','data:image/png;base64,','data:image/jpeg;base64,','data:image/webp;base64,')): raise ValueError('Фото/ссылка: используйте HTTPS или загрузите изображение PNG/JPEG/WebP')
    p['rate']=num(b.get('rate'),'Норма',nullable=True); p['price']=num(b.get('price'),'Цена',nullable=True)
    p['max_stock']=num(b.get('max_stock'),'Максимальный запас',nullable=True)
    p['step']=num(b.get('step'),'Шаг',minimum=.001)
    p['archived']=bool(b.get('archived',(old or {}).get('archived',False)))
    p['active']=bool(b.get('active',True)) and not p['archived']
    p['image']=store_image(p['image'])
    if old and p['image']==old.get('image'):p['image_source']=old.get('image_source')
    t=b.get('thresholds',[])
    if len(t)!=6: raise ValueError('Нужно шесть значений уровней')
    p['thresholds']=[num(v,'Порог') for v in t]
    if p['thresholds'][0]!=0 or p['thresholds']!=sorted(p['thresholds']): raise ValueError('Уровни должны возрастать, «Нет» = 0')
    if old and p['rate']!=old.get('rate'):
        p['rate_source']=b.get('rate_source') if str(b.get('rate_source','')).startswith('Точные остатки ') else 'Ручная норма администратора'
    if id: c.execute('UPDATE products SET data=? WHERE id=?',(json.dumps(p,ensure_ascii=False),id))
    else: id=c.execute('INSERT INTO products(data) VALUES(?)',(json.dumps(p,ensure_ascii=False),)).lastrowid
    log(c,'update' if old else 'create','product',id,old,p)
    return id

def save_observation(c,b):
    pid=int(b['product_id']); day(b['date'])
    if b['date']>current_day(): raise ValueError('Остаток не может быть в будущем')
    if not c.execute('SELECT 1 FROM products WHERE id=?',(pid,)).fetchone(): raise ValueError('Товар не найден')
    kind=b.get('kind')
    if kind not in ('exact','estimate','level'): raise ValueError('Неизвестный тип остатка')
    qty=num(b.get('qty'),'Остаток') if kind!='level' else None
    level=b.get('level') if kind=='level' else None
    if kind=='level' and (type(level)!=int or level not in range(6)): raise ValueError('Неизвестный уровень')
    id=c.execute('INSERT INTO observations(product_id,date,kind,qty,level,note,created_at) VALUES(?,?,?,?,?,?,?)',(pid,b['date'],kind,qty,level,str(b.get('note',''))[:2000],now())).lastrowid
    enroll_received_product(c,pid)
    log(c,'create','observation',id,None,b)
    return id

def save_delivery(c,b,id=None):
    o=office(b['office']); date=day(b['date'])
    if date>current_day(): raise ValueError('Поступление не может быть в будущем')
    supplier=str(b.get('supplier','')).strip(); number=str(b.get('number','')).strip()
    if not supplier or not number: raise ValueError('Укажите поставщика и номер документа')
    lines=[]
    for l in b.get('lines',[]):
        pid=int(l['product_id']); row=c.execute('SELECT data FROM products WHERE id=?',(pid,)).fetchone()
        if not row or json.loads(row[0])['office']!=o: raise ValueError('Позиция не относится к этому офису')
        lines.append(dict(product_id=pid,qty=num(l['qty'],'Количество',minimum=.001),price=num(l.get('price'),'Цена',nullable=True)))
    if not lines: raise ValueError('Добавьте хотя бы одну позицию')
    attachment=b.get('attachment')
    if attachment:
        if len(attachment.get('base64',''))>20_000_000: raise ValueError('PDF слишком большой (до 15 МБ)')
        try: raw=base64.b64decode(attachment['base64'],validate=True)
        except Exception: raise ValueError('Некорректный файл')
        if not raw.startswith(b'%PDF-'): raise ValueError('Нужен PDF-файл')
        digest=hashlib.sha256(raw).hexdigest()
        for r in c.execute('SELECT id,data FROM deliveries'):
            if r['id']!=id and json.loads(r['data']).get('file_hash')==digest: raise ValueError('Этот PDF уже добавлен. Для объединённого документа отредактируйте существующую поставку.')
        files=DATA/'files'; files.mkdir(exist_ok=True); (files/(digest+'.pdf')).write_bytes(raw)
    oldrow=c.execute('SELECT data FROM deliveries WHERE id=?',(id,)).fetchone() if id else None
    if id and not oldrow: raise ValueError('Поставка не найдена')
    old=json.loads(oldrow[0]) if oldrow else None
    d=dict(office=o,date=date,supplier=supplier,number=number,lines=lines,notes=str(b.get('notes',''))[:2000])
    if attachment: d['file_hash']=digest
    elif old and old.get('file_hash'): d['file_hash']=old['file_hash']
    try:
        if id: c.execute('UPDATE deliveries SET office=?,supplier=?,number=?,date=?,data=? WHERE id=?',(o,supplier_key(supplier),invoice_key(number),date,json.dumps(d,ensure_ascii=False),id))
        else: id=c.execute('INSERT INTO deliveries(office,supplier,number,date,data) VALUES(?,?,?,?,?)',(o,supplier_key(supplier),invoice_key(number),date,json.dumps(d,ensure_ascii=False))).lastrowid
    except sqlite3.IntegrityError: raise ValueError('Документ этого поставщика с таким номером уже есть в офисе')
    previous_ids={line['product_id'] for line in old['lines']} if old else set()
    for line in lines:
        if line['product_id'] not in previous_ids:enroll_received_product(c,line['product_id'])
    log(c,'update' if old else 'create','delivery',id,old,d)
    return id

def enroll_received_product(c,pid):
    row=c.execute('SELECT data FROM products WHERE id=?',(pid,)).fetchone()
    if not row:return
    p=json.loads(row[0]);before=p.copy();purchasing.receive(p)
    if p!=before:
        purchasing.save(c,pid,p);log(c,'received','product',pid,before,p)

def product_flags(c,b):
    pid=int(b['product_id']);p=purchasing.product(c,pid)
    fields={k:b[k] for k in ('favorite','in_pantry') if k in b}
    if not fields or any(type(v)!=bool for v in fields.values()):raise ValueError('Флаги должны быть true или false')
    before=p.copy()
    if 'favorite' in fields:p['favorite']=fields['favorite']
    if 'in_pantry' in fields:purchasing.change_policy(p,'regular' if fields['in_pantry'] else 'catalog')
    purchasing.save(c,pid,p);log(c,'flags','product',pid,before,p)
    return {'product_id':pid,**{k:p[k] for k in fields},'purchase_policy':p['purchase_policy'],'trial_received':p['trial_received']}

def store_image(value):
    if not value or not value.startswith('data:'):return value
    match=re.fullmatch(r'data:(image/(?:png|jpeg|webp));base64,([A-Za-z0-9+/=]+)',value)
    if not match or len(value)>3_000_000:raise ValueError('Invalid embedded product photo')
    try:raw=base64.b64decode(match[2],validate=True)
    except ValueError:raise ValueError('Invalid embedded product photo')
    valid={'image/png':raw.startswith(b'\x89PNG\r\n\x1a\n'),'image/jpeg':raw.startswith(b'\xff\xd8\xff'),'image/webp':raw.startswith(b'RIFF') and raw[8:12]==b'WEBP'}
    if not valid[match[1]]:raise ValueError('Invalid embedded product photo')
    extension={'image/png':'png','image/jpeg':'jpg','image/webp':'webp'}[match[1]]
    name=hashlib.sha256(raw).hexdigest()+'.'+extension;folder=DATA/'catalog-images';folder.mkdir(exist_ok=True)
    if not (folder/name).exists():(folder/name).write_bytes(raw)
    return '/assets/catalog/'+name

def photo_status(value):
    if not value:return 'none'
    if value.startswith('/assets/catalog/'):
        name=value.rsplit('/',1)[-1]
        return 'local' if re.fullmatch(r'[a-f0-9]{64}\.(png|jpg|webp)',name) and (DATA/'catalog-images'/name).is_file() else 'missing'
    return 'inline' if value.startswith('data:') else 'external'

def photo_candidates(c,pid,query='',page=1):
    row=c.execute('SELECT data FROM products WHERE id=?',(pid,)).fetchone()
    if not row:raise ValueError('Товар не найден')
    target=json.loads(row['data']);supplier=taxonomy.canonical_supplier(target['supplier']);q=taxonomy.plain(query);choices=[];seen=set()
    for kind,table in (('product','products'),('supplier_catalog','supplier_catalog')):
        for r in c.execute(f'SELECT id,data FROM {table}'):
            p=json.loads(r['data'])
            if not p.get('image') or taxonomy.canonical_supplier(p['supplier'])!=supplier:continue
            if kind=='product' and (r['id']==pid or p['office']!=target['office'] or p.get('archived')):continue
            sku=p.get('supplier_sku',p.get('sku',''));key=(sku or p['name'],p['image'])
            if key in seen:continue
            if q and q not in taxonomy.plain(p['name']+' '+sku):continue
            seen.add(key);choices.append(dict(source_type=kind,id=r['id'],name=p['name'],sku=sku,image=p['image'],photo_status=photo_status(p['image'])))
    return dict(rows=choices[(page-1)*24:page*24],total=len(choices),page=page)

def choose_product_photo(c,b):
    pid=int(b['product_id']);kind=b.get('source_type');id=int(b['source_id'])
    table={'product':'products','supplier_catalog':'supplier_catalog'}.get(kind)
    if not table:raise ValueError('Неверный источник фотографии')
    target=c.execute('SELECT data FROM products WHERE id=?',(pid,)).fetchone();source=c.execute(f'SELECT data FROM {table} WHERE id=?',(id,)).fetchone()
    if not target or not source:raise ValueError('Товар не найден')
    p=json.loads(target['data']);item=json.loads(source['data'])
    if taxonomy.canonical_supplier(p['supplier'])!=taxonomy.canonical_supplier(item['supplier']):raise ValueError('Фотография относится к другому поставщику')
    if kind=='product' and item['office']!=p['office']:raise ValueError('Товар не относится к офису')
    if not item.get('image'):raise ValueError('У выбранного товара нет фото')
    if photo_status(item['image'])=='missing':raise ValueError('Файл фотографии не найден. Скопируйте папку .runtime/catalog-images из прежней версии.')
    before={'image':p.get('image',''),'image_source':p.get('image_source')};p['image']=store_image(item['image'])
    p['image_source']=dict(type=kind,id=id,name=item['name'],sku=item.get('supplier_sku',item.get('sku','')),selected_at=now(),illustrative=p.get('name_status')=='provisional')
    c.execute('UPDATE products SET data=? WHERE id=?',(json.dumps(p,ensure_ascii=False),pid));log(c,'photo','product',pid,before,{'image':p['image'],'image_source':p['image_source']})
    return {'product_id':pid,'image':p['image']}

def read_import_job(c,id):
    row=c.execute('SELECT data FROM catalog_import_jobs WHERE id=?',(str(id),)).fetchone()
    if not row:raise ValueError('Импорт не найден')
    return json.loads(row['data'])

def start_catalog_import(c,b):
    supplier=b.get('supplier');o=office(b.get('office'));mode=b.get('mode','supplier')
    if supplier not in catalog.SUPPLIERS:raise ValueError('Unknown supplier')
    if mode not in ('supplier','add','replace'):raise ValueError('Недопустимый режим импорта')
    id=uuid.uuid4().hex;job=dict(supplier=supplier,office=o,mode=mode,status='preparing',catalog_ids=[],created_at=now())
    c.execute('INSERT INTO catalog_import_jobs VALUES(?,?)',(id,json.dumps(job,ensure_ascii=False)))
    return {'job_id':id}

def finish_catalog_import(c,b):
    c.execute('BEGIN IMMEDIATE')
    job=read_import_job(c,b['job_id'])
    if job['status']=='finished':return job['result']
    ids=set(job['catalog_ids']);expected=int(b['expected_count'])
    if not ids or len(ids)!=expected:raise ValueError('Не все товары загружены. Каталог ещё не заменён.')
    if job['status']!='preparing':raise ValueError('Недопустимое состояние импорта')
    result=dict(count=len(ids),created=0,updated=0,archived=0)
    if job['mode']!='supplier':
        existing=[dict(json.loads(r['data']),id=r['id']) for r in c.execute('SELECT id,data FROM products')]
        linked={p.get('catalog_id'):p for p in existing if p['office']==job['office'] and p.get('catalog_id') in ids}
        for catalog_id in sorted(ids):
            row=c.execute('SELECT supplier,data FROM supplier_catalog WHERE id=?',(catalog_id,)).fetchone()
            if not row or row['supplier']!=job['supplier']:raise ValueError('Товар справочника не найден')
            item=json.loads(row['data']);old=linked.get(catalog_id)
            p=old.copy() if old else dict(office=job['office'],category=item['category'],unit=item['unit'],step=1,rate=None,rate_source='Нет истории потребления',price=item['price'],active=True,notes='',thresholds=[0,1,3,6,12,24],max_stock=None,legacy_name='',favorite=False,in_pantry=False,category_source=item.get('category_source','auto'))
            p.update(name=item['name'],supplier=item['supplier'],supplier_sku=item['sku'],url=item['url'],image=store_image(item.get('image') or p.get('image','')),catalog_id=catalog_id,name_status='supplier_import',archived=False,active=True)
            purchasing.normalize(p)
            p.pop('id',None)
            if old:
                id=old['id'];c.execute('UPDATE products SET data=? WHERE id=?',(json.dumps(p,ensure_ascii=False),id));result['updated']+=1
            else:
                id=c.execute('INSERT INTO products(data) VALUES(?)',(json.dumps(p,ensure_ascii=False),)).lastrowid;result['created']+=1
            log(c,'bulk-import','product',id,old,p)
        if job['mode']=='replace':
            for p in existing:
                if p['office']!=job['office'] or p.get('catalog_id') in ids or p.get('archived'):continue
                old=p.copy();id=p.pop('id');p.update(archived=True,active=False)
                c.execute('UPDATE products SET data=? WHERE id=?',(json.dumps(p,ensure_ascii=False),id));log(c,'archive','product',id,old,p);result['archived']+=1
    job.update(status='finished',result=result,finished_at=now());c.execute('UPDATE catalog_import_jobs SET data=? WHERE id=?',(json.dumps(job,ensure_ascii=False),b['job_id']))
    log(c,'finish','catalog_import',b['job_id'],None,result)
    return result

class Handler(BaseHTTPRequestHandler):
    def send(self,code,data,ctype='application/json; charset=utf-8',headers=None):
        raw=data if isinstance(data,bytes) else json.dumps(data,ensure_ascii=False).encode() if ctype.startswith('application/json') else data
        self.send_response(code)
        self.send_header('Content-Type',ctype); self.send_header('Content-Length',str(len(raw)))
        self.send_header('X-Content-Type-Options','nosniff'); self.send_header('X-Frame-Options','DENY')
        self.send_header('Cache-Control',(headers or {}).get('Cache-Control','no-store'))
        for k,v in (headers or {}).items():
            if k.lower()!='cache-control':self.send_header(k,v)
        self.end_headers(); self.wfile.write(raw)
    def authenticated(self):
        token=os.environ.get('PANTRY_PASSWORD')
        if not token: return True
        try:
            scheme,encoded=self.headers.get('Authorization','').split(' ',1)
            user,password=base64.b64decode(encoded).decode().split(':',1)
            if scheme=='Basic' and secrets.compare_digest(password,token): return True
        except Exception: pass
        self.send(401,{'error':'Требуется вход'},headers={'WWW-Authenticate':'Basic realm="Office Pantry", charset="UTF-8"'})
        return False
    def do_GET(self):
        if not self.authenticated(): return
        path=urlparse(self.path).path
        if path.startswith('/assets/catalog/'):
            name=path.rsplit('/',1)[-1]
            if not re.fullmatch(r'[a-f0-9]{64}\.(png|jpg|webp)',name):return self.send(404,{'error':'Файл не найден'})
            file=DATA/'catalog-images'/name
            if not file.is_file():return self.send(404,{'error':'Файл не найден'})
            mime={'.png':'image/png','.jpg':'image/jpeg','.webp':'image/webp'}[file.suffix]
            return self.send(200,file.read_bytes(),mime,{'Cache-Control':'private, max-age=31536000, immutable'})
        with connect() as c:
            if path=='/api/photo-candidates':
                query=parse_qs(urlparse(self.path).query)
                try:return self.send(200,photo_candidates(c,int(query.get('product_id',['0'])[0]),query.get('q',[''])[0],max(1,int(query.get('page',['1'])[0]))))
                except ValueError as e:return self.send(400,{'error':str(e)})
            if path=='/api/supplier-catalog':
                q=parse_qs(urlparse(self.path).query);supplier=q.get('supplier',['Maxi'])[0];search=q.get('q',[''])[0].casefold()[:200]
                try:page=max(1,int(q.get('page',['1'])[0]))
                except ValueError:return self.send(400,{'error':'Invalid page'})
                where='supplier=? AND instr(name_search,?)>0';args=(supplier,search)
                total=c.execute('SELECT count(*) FROM supplier_catalog WHERE '+where,args).fetchone()[0]
                rows=[]
                for r in c.execute('SELECT id,data FROM supplier_catalog WHERE '+where+' ORDER BY id LIMIT 40 OFFSET ?',(*args,(page-1)*40)):
                    item=dict(json.loads(r['data']),id=r['id']);item['has_image']=bool(item.get('image'))
                    if item.get('image','').startswith('data:'):item['image']=''
                    rows.append(item)
                return self.send(200,dict(rows=rows,total=total,page=page,suppliers=catalog.PAGES))
            if path=='/api/state': return self.send(200,state(c))
            if path=='/api/backup':
                backup={t:[dict(r) for r in c.execute(f'SELECT * FROM {t}')] for t in ('products','observations','deliveries','attendance','audit','meta','orders','supplier_catalog','catalog_import_jobs','trial_proposals')}
                files={f.name:base64.b64encode(f.read_bytes()).decode() for f in (DATA/'files').glob('*.pdf')}
                images={f.name:base64.b64encode(f.read_bytes()).decode() for f in (DATA/'catalog-images').glob('*') if f.is_file()}
                return self.send(200,dict(version=1,created_at=now(),tables=backup,files=files,images=images),headers={'Content-Disposition':'attachment; filename="pantry-backup.json"'})
            if path=='/api/audit': return self.send(200,[dict(r) for r in c.execute('SELECT * FROM audit ORDER BY id DESC LIMIT 300')])
            if path.startswith('/api/calibrate/'):
                try: return self.send(200,calibration(state(c),int(path.split('/')[-1])))
                except (ValueError,StopIteration): return self.send(404,{'error':'Товар не найден'})
            if path.startswith('/api/file/'):
                digest=path.split('/')[-1]
                if len(digest)!=64 or any(ch not in '0123456789abcdef' for ch in digest): return self.send(404,{'error':'Файл не найден'})
                f=DATA/'files'/(digest+'.pdf')
                if f.exists(): return self.send(200,f.read_bytes(),'application/pdf',{'Content-Disposition':'attachment; filename="invoice.pdf"'})
                return self.send(404,{'error':'Файл не найден'})
        rel='index.html' if path=='/' else path.lstrip('/')
        f=(ROOT/'static'/rel).resolve()
        if not f.is_relative_to((ROOT/'static').resolve()) or not f.is_file(): return self.send(404,{'error':'Страница не найдена'})
        types={'.html':'text/html; charset=utf-8','.css':'text/css','.js':'text/javascript','.svg':'image/svg+xml','.json':'application/json; charset=utf-8'}
        return self.send(200,f.read_bytes(),types.get(f.suffix,'application/octet-stream'))
    def do_POST(self):
        if not self.authenticated(): return
        # Require same-origin JSON; cross-origin form requests cannot mutate data.
        if self.headers.get('Sec-Fetch-Site')=='cross-site' or self.headers.get('Content-Type','').split(';')[0]!='application/json': return self.send(403,{'error':'Нужен same-origin JSON запрос'})
        origin=self.headers.get('Origin')
        if origin and urlparse(origin).netloc!=self.headers.get('Host'): return self.send(403,{'error':'Неверный Origin'})
        try:
            size=int(self.headers.get('Content-Length','0'))
            if size<=0 or size>23_000_000: raise ValueError('Слишком большой или пустой запрос')
            b=json.loads(self.rfile.read(size)); path=urlparse(self.path).path; result={}
            with connect() as c:
                if path=='/api/catalog/preview':result=catalog.preview(b['content'],b['format'],b['supplier'])
                elif path=='/api/catalog/import-start':result=start_catalog_import(c,b)
                elif path=='/api/catalog/import-finish':result=finish_catalog_import(c,b)
                elif path=='/api/catalog/import':
                    job=read_import_job(c,b['job_id']) if b.get('job_id') else None
                    if job and (job['supplier']!=b['supplier'] or job['status']!='preparing'):raise ValueError('Недопустимое состояние импорта')
                    ids=catalog.upsert(c,b['supplier'],b['rows'],now(),log,image_store=store_image)
                    if job:
                        job['catalog_ids']=list(dict.fromkeys(job['catalog_ids']+ids));c.execute('UPDATE catalog_import_jobs SET data=? WHERE id=?',(json.dumps(job,ensure_ascii=False),b['job_id']))
                    result={'count':len(ids)}
                elif path=='/api/catalog/select':
                    row=c.execute('SELECT data FROM supplier_catalog WHERE id=?',(int(b['catalog_id']),)).fetchone()
                    if not row:raise ValueError('Catalogue product not found')
                    item=json.loads(row['data']);o=office(b['office']);pid=b.get('product_id')
                    for r in c.execute('SELECT id,data FROM products'):
                        other=json.loads(r['data'])
                        if other.get('office')==o and other.get('catalog_id')==int(b['catalog_id']) and r['id']!=pid:raise ValueError('This catalogue product is already linked in this office')
                    if pid:
                        row=c.execute('SELECT data FROM products WHERE id=?',(int(pid),)).fetchone()
                        if not row:raise ValueError('Товар не найден')
                        p=json.loads(row['data'])
                        if p['office']!=o:raise ValueError('Товар не относится к офису')
                        if supplier_key(p['supplier'])!=supplier_key(item['supplier']):raise ValueError('The existing product belongs to a different supplier')
                    else:p=dict(office=o,category=item['category'],unit=item['unit'],step=1,rate=None,rate_source='Нет истории потребления',price=item['price'],active=True,notes='',thresholds=[0,1,3,6,12,24],favorite=False,in_pantry=False,category_source=item.get('category_source','auto'))
                    item['image']=store_image(item.get('image',''))
                    p.update(name=item['name'],supplier=item['supplier'],supplier_sku=item['sku'],url=item['url'],image=item['image'] or p.get('image',''))
                    id=save_product(c,p,int(pid) if pid else None)
                    saved=json.loads(c.execute('SELECT data FROM products WHERE id=?',(id,)).fetchone()[0]);saved.update(catalog_id=int(b['catalog_id']),name_status='supplier_import')
                    c.execute('UPDATE products SET data=? WHERE id=?',(json.dumps(saved,ensure_ascii=False),id));log(c,'link','product',id,None,{'catalog_id':int(b['catalog_id'])});result={'id':id}
                elif path=='/api/product-policy':result=purchasing.policy_action(c,b,now(),log)
                elif path=='/api/proposals':result=purchasing.propose(c,b,now(),log)
                elif path=='/api/proposals/decide':result=purchasing.decide(c,b,now(),log)
                elif path=='/api/product-photo':result=choose_product_photo(c,b)
                elif path=='/api/product-flags':result=product_flags(c,b)
                elif path=='/api/product': result={'id':save_product(c,b,b.get('id'))}
                elif path=='/api/observation': result={'id':save_observation(c,b)}
                elif path=='/api/delivery': result={'id':save_delivery(c,b,b.get('id'))}
                elif path=='/api/order':
                    office(b['office']); num(b['visits'],'Посещения'); num(b['buffer'],'Резерв')
                    if not b.get('lines'): raise ValueError('Нет позиций для заказа')
                    for line in b['lines']:
                        num(line['qty'],'Количество',minimum=.001)
                        row=c.execute('SELECT data FROM products WHERE id=?',(int(line['product_id']),)).fetchone()
                        if not row or json.loads(row[0])['office']!=b['office']: raise ValueError('Товар не относится к офису')
                    id=c.execute('INSERT INTO orders(created_at,data) VALUES(?,?)',(now(),json.dumps(b,ensure_ascii=False))).lastrowid
                    log(c,'create','order',id,None,b); result={'id':id}
                elif path=='/api/attendance':
                    records=b.get('records',[b])
                    if not records: raise ValueError('Нет строк')
                    for a in records:
                        o=office(a['office']); d=day(a['date']); n=num(a['count'],'Посещаемость')
                        if n!=int(n): raise ValueError('Посещаемость должна быть целым числом')
                        old=c.execute('SELECT * FROM attendance WHERE office=? AND date=?',(o,d)).fetchone()
                        c.execute('INSERT OR REPLACE INTO attendance VALUES(?,?,?,?)',(o,d,int(n),a.get('notes','')))
                        log(c,'upsert','attendance',o+':'+d,dict(old) if old else None,a)
                elif path=='/api/delete':
                    tables={'delivery':'deliveries','observation':'observations'}
                    if b.get('kind') not in tables: raise ValueError('Этот тип записи нельзя удалить')
                    table=tables[b['kind']]; row=c.execute(f'SELECT * FROM {table} WHERE id=?',(int(b['id']),)).fetchone()
                    if not row: raise ValueError('Запись не найдена')
                    c.execute(f'DELETE FROM {table} WHERE id=?',(int(b['id']),)); log(c,'delete',b['kind'],b['id'],dict(row))
                else: return self.send(404,{'error':'Метод не найден'})
            self.send(200,dict(ok=True,**result))
        except (ValueError,KeyError,TypeError,sqlite3.IntegrityError) as e: self.send(400,{'error':str(e)})
        except Exception:
            import traceback
            traceback.print_exc(); self.send(500,{'error':'Ошибка сервера. Проверьте журнал.'})

if __name__=='__main__':
    init()
    host=os.environ.get('HOST','127.0.0.1'); port=int(os.environ.get('PORT','8000'))
    if host not in ('127.0.0.1','localhost','::1') and not os.environ.get('PANTRY_PASSWORD'): raise SystemExit('Для доступа по сети задайте PANTRY_PASSWORD и используйте HTTPS через reverse proxy.')
    print(f'Office Pantry: {host}:{port}; database: {DATA}',flush=True)
    ThreadingHTTPServer((host,port),Handler).serve_forever()
