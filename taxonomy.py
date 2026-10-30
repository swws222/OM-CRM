"""Editable product categories: conservative name-based suggestions, never quantities."""
import re
import unicodedata

CATEGORIES=['Молочные','Яйца','Хлеб и выпечка','Мясо и рыба','Фрукты и овощи','Снеки','Сладости','Напитки','Кофе и чай','Бакалея','Соусы и намазки','Замороженные продукты','Бытовые товары','Прочее']
SUPPLIERS=['Maxi','Moja Pijaca','Denmark','Coca-Cola']

def plain(value):
    value=str(value or '').casefold().replace('đ','dj')
    return ''.join(c for c in unicodedata.normalize('NFKD',value) if not unicodedata.combining(c))

def canonical_supplier(value):
    value=str(value or '').strip()
    key=re.sub(r'[\s_.-]+','',plain(re.sub(r'\s*\(чек\)$','',value,flags=re.I)))
    return {'maxi':'Maxi','mojapijaca':'Moja Pijaca','denmark':'Denmark','денмарк':'Denmark','cocacola':'Coca-Cola'}.get(key,value)

def suggest_category(name):
    n=plain(name)
    # Whole product nouns precede ingredient/flavour terms. Unknown names stay Other.
    rules=[
      ('Бытовые товары',r'\b(deterdzent\w*|detergent\w*|sampon\w*|sapun\w*|toalet\w*|ubrusi|maramice|ciscenje|listerine|omeksivac|domestos|mleko za telo|крем для рук|чистящ\w*|мыло|салфет\w*)\b'),
      ('Замороженные продукты',r'\b(smrzn\w*|zamrzn\w*|sladoled\w*|frozen|ice cream|заморож\w*|мороженое)\b'),
      ('Напитки',r'\b(coca[ -]?cola|fanta|sprite|powerade|fuze tea|rosa|pepsi|red bull|voda|vode|sok|sokovi|nektar\w*|smuti\w*|smoothie|pivo|напиток газирован\w*|газирован\w* вода|сок|смузи)\b'),
      ('Соусы и намазки',r'\b(maslac od kikirikija|kikiriki puter|peanut butter)\b'),
      ('Молочные',r'\b(mleko|mlijeko|jogurt|yogurt|kiselo mleko|sir|sira|sirko|sirok\w*|sirki|sirevi|kackavalj|pavlaka|kajmak|kefir|maslac|grekos|jogood|balans|tilsit|alpro|proteinski puding|protein drink|protein sejk|молоко|йогурт\w*|кефир|сыр\w*|творог\w*|масло порционное|протеинов\w* пудинг)\b'),
      ('Яйца',r'\b(jaja|jaje|egg|eggs|јаја|яйц\w*)\b'),
      ('Хлеб и выпечка',r'\b(hleb\w*|hljeb\w*|peciv\w*|baget\w*|kifl\w*|kroasan\w*|tost|toast|lepinj\w*|pita|zemick\w*|хлеб\w*|булоч\w*|выпечк\w*|круассан\w*)\b'),
      ('Мясо и рыба',r'\b(meso|piletin\w*|pileci|svinj\w*|sunka|prsut\w*|kobasic\w*|losos\w*|tunjevin\w*|riba|sardin\w*|salam\w*|мяс\w*|рыб\w*|лосос\w*|тунец|нарезка)\b'),
      ('Соусы и намазки',r'\b(humus|hummus|ribella|pastet\w*|argeta|namaz\w*|majonez|senf|kecap|sos|dzem\w*|pekmez\w*|pindjur|ajvar|хумус|паштет\w*|соус\w*|майонез|джем\w*)\b'),
      ('Кофе и чай',r'\b(kafa|kafe|coffee|caj|tea|stassen|nescafe|кофе|чай)\b'),
      ('Сладости',r'\b(cokolad\w*|keks\w*|biskvit\w*|bombon\w*|napolit\w*|kolac\w*|puding|kinder|slatkis\w*|wafer\w*|cookie\w*|chocolate|шоколад\w*|печень\w*|конфет\w*|пудинг\w*)\b'),
      ('Фрукты и овощи',r'\b(banan\w*|paradajz\w*|krastav\w*|sargarep\w*|jabuk\w*|krusk\w*|pomorandz\w*|mandarin\w*|grozdje|limun\w*|kivi|borovnic\w*|malin\w*|jagod\w*|voce|povrce|salata|spanac|банан\w*|черри|морков\w*|огур\w*|яблок\w*|фрукт\w*|овощ\w*)\b'),
      ('Снеки',r'\b(cips\w*|chips\w*|smoki|stapic\w*|grisin\w*|kikiriki|badem\w*|orah\w*|orasi|lesnik\w*|pistac\w*|kokice|kreker\w*|sportness|benlian|чипс\w*|орех\w*|батончик\w*|крекер\w*)\b'),
      ('Бакалея',r'\b(pirinac|testenin\w*|spaget\w*|brasno|secer|so|ulje|palenta|ovsene|pahuljic\w*|granola|musli|konzerv\w*|pasulj|grasak|рис|макарон\w*|круп\w*|мука|сахар|хлопья|масло подсолнечное)\b'),
    ]
    for category,pattern in rules:
        if re.search(pattern,n):return category
    return 'Прочее'

def category_fields(name,category=None,source=None):
    category=str(category or '').strip()
    if source=='manual':return {'category':category or 'Прочее','category_source':'manual'}
    if category and category not in ('Прочее','Other','Ostalo','Uncategorized'):
        return {'category':category,'category_source':source or 'supplier'}
    return {'category':suggest_category(name),'category_source':'auto'}
