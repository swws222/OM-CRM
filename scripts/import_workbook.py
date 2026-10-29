"""One-time conversion of the supplied workbook. Cells are data, never instructions."""
import datetime as dt
import json
import sys
import xml.etree.ElementTree as E
import zipfile
from pathlib import Path
NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
def read(path):
    with zipfile.ZipFile(path) as z:
        strings = [''.join(x.itertext()) for x in E.fromstring(z.read('xl/sharedStrings.xml')).findall('s:si', NS)]
        sheets = {}
        for i in (3, 6, 7, 8, 12):
            rows = []
            for row in E.fromstring(z.read(f'xl/worksheets/sheet{i}.xml')).findall('.//s:row', NS):
                r = {}
                for c in row:
                    v = c.find('s:v', NS)
                    val = v.text if v is not None else ''
                    if c.get('t') == 's': val = strings[int(val)]
                    if val != '': r[''.join(filter(str.isalpha, c.get('r')))] = val
                rows.append(r)
            sheets[i] = rows
        return sheets

def date(v): return (dt.date(1899, 12, 30) + dt.timedelta(days=int(float(v)))).isoformat()
def category(name):
    n = name.lower()
    if any(x in n for x in ('банан', 'черри', 'морков', 'огур', 'хлеб')): return 'Фрукты и овощи'
    if any(x in n for x in ('rosa', 'coca', 'powerade', 'next ', 'банки', 'чай')): return 'Напитки'
    if any(x in n for x in ('argeta', 'хумус', 'лосось', 'шея', 'тунец')): return 'Перекусы'
    if any(x in n for x in ('listerine',)): return 'Прочее'
    if any(x in n for x in ('sportness', 'чипс', 'смузи')): return 'Снеки'
    return 'Молочные'

def convert(path):
    s = read(path); products = []
    for r in s[7][3:]:
        if not r.get('B'): continue
        weekly = float(r['P'])
        products.append(dict(id=len(products)+1, name=r['A'], supplier='Moja Pijaca' if any(x in r['A'] for x in ['Сырки', 'Бананы', 'Черри', 'Морковные', 'Огурцы']) else 'Maxi', category=category(r['A']), unit=r['B'], step=float(r['C']), rate=float(r['O']), rate_source='Оценка из Excel · нижняя граница', price=None, image='', url='', thresholds=[0, round(weekly*.25,2),round(weekly*.5,2),round(weekly,2),round(weekly*2.5,2),round(weekly*4,2)], notes=r.get('U',''), stock=float(r['L']), stock_min=float(r['J']), stock_max=float(r['K']), source_note='Оценка по фото, 19.10.2026. Не точная инвентаризация.'))
    for r in s[8]:
        drinks = 'L' in r and r.get('M') in ('бут.', 'шт.', 'банок')
        other = 'D' in r and r.get('E') == 'шт.'
        if not (drinks or other): continue
        stock = float(r['L'] if drinks else r['D'])
        products.append(dict(id=len(products)+1, name=r['A'], supplier='Coca-Cola' if drinks else 'Уточнить', category=category(r['A']), unit=r['M'] if drinks else r['E'], step=24 if '24' in r.get('N','') else 12 if drinks else 1, rate=None, rate_source='Нет истории потребления', price=None, image='', url='', thresholds=[0,1,3,6,12,24], notes=r.get('N',r.get('F',''))+' Пороги уровней — стартовый шаблон, настройте под товар.', stock=stock, stock_min=float(r['J'] if drinks else r['B']), stock_max=float(r['K'] if drinks else r['C']), source_note='Оценка по фото, 19.10.2026. Нет данных о расходе.'))
    price_names={'Бананы, кг':'Banane','Черри 250 г, шт.':'Paradajz čeri 250g','Морковные палочки 80 г, шт.':'Šargarepa štapići 80g','Огурцы, кг':'Krastavac'}
    prices={r.get('B'):r.get('L') for r in s[12]}
    for p in products:
        price=prices.get(price_names.get(p['name']))
        if price:
            p['price']=round(float(price),2)
            p['notes']+=' Историческая цена Moja Pijaca за сентябрь 2026, после скидки с НДС. Проверьте актуальность.'
    lookup = {p['name']:p['id'] for p in products}
    groups = {}; unmatched = []
    for r in s[6][1:]:
        if r.get('D') not in lookup: unmatched.append(r); continue
        key=(date(r['A']),r['B'],r['C'])
        g=groups.setdefault(key, dict(date=key[0],supplier=key[1],number=key[2],office='Белград',notes='История из Excel',lines=[]))
        g['lines'].append(dict(product_id=lookup[r['D']],qty=float(r['E']),price=None))
    attendance = [dict(date=date(r['A']),count=int(float(r['B'])),office='Белград',notes=r.get('C','')) for r in s[3][2:] if r.get('B') and r['A'].replace('.','').isdigit()]
    return dict(source='CRM_staff_prototype.xlsx', stock_date='2026-10-19', products=products, deliveries=list(groups.values()),attendance=attendance,unmatched=unmatched)
if __name__ == '__main__':
    data=convert(sys.argv[1]); Path(sys.argv[2]).write_text(json.dumps(data,ensure_ascii=False,indent=2))
    print({k:len(data[k]) for k in ('products','deliveries','attendance','unmatched')})
