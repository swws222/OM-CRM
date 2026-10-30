import {filterProducts,suppliersFor,categoriesFor,supplierName} from './product-filters.js';
import {importFiles,mergeCatalogRows,importBatches} from './catalog-batch.js';
import {t, label, locale, getLanguage, setLanguage} from './i18n.js';
import { recommend } from './model.js';
const $ = s => document.querySelector(s),
  $$ = s => [...document.querySelectorAll(s)];
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;'
})[c]);
const fmt = n => n == null ? '—' : Number(n).toLocaleString(locale(), {
  maximumFractionDigits: 2
});
const date = d => d ? new Date(d + 'T12:00:00').toLocaleDateString(locale()) : '—';
const today = () => new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Europe/Belgrade',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit'
}).format(new Date());
const age = d => d ? Math.floor((new Date(today()) - new Date(d)) / 86400000) : Infinity;
const download = (name, content, type = 'text/plain') => {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([content], {
    type
  }));
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
};
const staffMode = new URLSearchParams(location.search).get('mode') === 'staff';
document.body.dataset.staff=String(staffMode);
let state,
  view = staffMode?'stock':(sessionStorage.getItem('pantry_view')||'stock'),
  selectedOffice = localStorage.getItem('office') || 'Белград',
  category = 'Все товары',
  search = '',
  onlyLow = false,
  visits = 240,
  buffer = .5,
  overrides = {},
  toastTimer;
const nav = [['stock', '▦', t("Остатки")],['favorites','♡',t('Избранное')], ['order', '▤', t("План закупки")], ['products', '◇', t("Каталог")], ['deliveries', '▱', t("Поступления")], ['attendance', '▥', t("Посещаемость")]];
const products = () => state.products.filter(p => p.office === selectedOffice);
const favoriteProducts=()=>products().filter(p=>p.favorite);
const active=()=>products().filter(p=>p.in_pantry);
let supplierFilter='',favoriteOnly=false;
try{const saved=JSON.parse(sessionStorage.getItem('pantry_filters')||'{}');supplierFilter=saved.supplier||'';category=saved.category||'Все товары';favoriteOnly=Boolean(saved.favorites)}catch{}
let catalogShowArchived=false;
function notify(message, error = false) {
  const el = $('#toast');
  el.textContent = t(message);
  el.className = error ? 'error' : '';
  el.style.display = 'block';
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.style.display = 'none', 4500);
}
async function api(path, body) {
  const r = await fetch('/api/' + path, body ? {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(body)
  } : {});
  let data;
  try {
    data = await r.json();
  } catch {
    throw Error(t("Сервер недоступен. Изменения не сохранены."));
  }
  if (!r.ok) throw Error(t(data.error) || t("Ошибка запроса"));
  return data;
}
async function load() {
  state = await api('state');
}
async function refresh() {
  await load();
  render();
}
function icon(p) {
  let n = (p.legacy_name||p.name).toLowerCase();
  for (const [words, i] of [[['банан'], '🍌'], [['черри'], '🍅'], [['морков'], '🥕'], [['огур'], '🥒'], [['хлеб'], '🍞'], [['лосось', 'тунец'], '🐟'], [['шея'], '🥓'], [['молоко', 'alpro'], '🥛'], [['сыр', 'tilsit'], '🧀'], [['чай'], '🍵'], [['coca', 'fanta', 'банки'], '🥤'], [['rosa'], '💧'], [['sportness', 'kinder'], '🍫'], [['чипс'], '🍘'], [['хумус', 'argeta'], '🥫'], [['смузи', 'next'], '🧃']]) if (words.some(w => n.includes(w))) return i;
  return p.category === 'Напитки' ? '🧴' : '🥣';
}
const illustration = p => `<span class="illustration" role="img" aria-label="${t("Иллюстрация:")} ${esc(p.name)}">${icon(p)}</span>`;
function photo(p) {
  return p.image ? `<img src="${esc(p.image)}" alt="${esc(p.name)}" loading="lazy" referrerpolicy="no-referrer">` : illustration(p);
}
function badge(p) {
  const o = p.observation;
  if (!o) return t("<span class=\"badge warn\">Не проверено</span>");
  if (age(o.date) > 7) return t("<span class=\"badge warn\">Нужно обновить</span>");
  if (o.kind === 'level') return `<span class="badge ${o.level < 2 ? 'red' : 'green'}">${esc(label(state.levels[o.level]))}</span>`;
  return `<span class="badge green">${o.kind === 'exact' ? t("Точный остаток") : t("Оценка")}</span>`;
}
function pagehead(eyebrow, title, sub, action = '') {
  return `<div class="pagehead"><div><div class="eyebrow">${eyebrow}</div><h1>${title}</h1><p class="subtitle">${sub}</p></div>${action}</div>`;
}
function render() {
  $('#app').innerHTML = `<div class="layout"><aside class="sidebar"><div class="brand"><span class="brandmark">♧</span><div>office pantry<small>${t("забота об офисе")}</small></div></div><div class="side-label">${t("РАБОЧЕЕ ПРОСТРАНСТВО")}</div><nav class="nav" aria-label="${t("Основная навигация")}">${nav.filter(n => !staffMode || ['stock','favorites'].includes(n[0])).map(([id, i, n]) => `<button data-nav="${id}" class="${view === id ? 'active' : ''}"><span class="nav-icon">${i}</span>${n}${id==='favorites'?`<span class="nav-count">${favoriteProducts().length}</span>`:''}</button>`).join('')}</nav><div class="side-foot"><span class="dot"></span> ${t("Всё в одной кладовой")}<br><span class="tiny">MVP · ${t("данные сохраняются на сервере")}</span><br><a class="text-link tiny" href="?mode=staff">${t("Интерфейс хозяюшки")}</a><br><button class="text-link tiny" id="backup" style="margin-top:12px">${t("Резервная копия")}</button></div></aside><main class="main"><header class="topbar"><span class="breadcrumb">${t("Рабочее пространство")} &nbsp; / &nbsp; ${nav.find(n => n[0] === view)[2]}</span><div class="top-right"><select id="office" aria-label="${t("Офис")}">${state.offices.map(o => `<option value="${esc(o)}" ${o === selectedOffice ? 'selected' : ''}>${esc(label(o))}</option>`).join('')}</select><select id="language" aria-label="Language / Jezik / Язык"><option value="ru">Русский</option><option value="sr">Srpski</option><option value="en">English</option></select><span class="avatar">OP</span></div></header><div class="content" id="content"></div></main></div>`;
  $('#language').value=getLanguage();
  $('#language').onchange=e=>setLanguage(e.target.value);
  $('#office').onchange = e => {
    selectedOffice = e.target.value;
    localStorage.setItem('office', selectedOffice);
    category = 'Все товары';supplierFilter='';favoriteOnly=false;rememberFilters();
    search = '';
    overrides = {};
    render();
  };
  $$('[data-nav]').forEach(b => b.onclick = () => {
    view = b.dataset.nav;
    sessionStorage.setItem('pantry_view',view);
    search = '';
    render();
  });
  $('#backup').onclick = () => window.location.assign('/api/backup');
  ({
    stock: stockView,
    favorites:favoritesView,
    products: productsView,
    order: orderView,
    deliveries: deliveriesView,
    attendance: attendanceView
  })[view]();
}
function stockView() {
  const ps = active(),
    checked = ps.filter(p => p.observation?.date === today()).length;
  $('#content').innerHTML = pagehead(t("КЛАДОВАЯ ОФИСА"), t("Всё на своих местах"), t("Отметьте, сколько осталось. О количестве для заказа позаботится система."), `<button class="btn" id="inventory">＋ ${t("Точный остаток")}</button>`) + `<div class="hero"><div><div class="eyebrow">${t("БЫСТРЫЙ ОБХОД")}</div><h2>${t("Хороший день начинается")}<br> ${t("с полной кухни.")}</h2><p>${t("Проверьте весь запас товара в офисе: склад и обе кухни. После сегодняшних поставок выбирайте уровень — он сохранится сразу.")}</p></div><div class="hero-art" aria-hidden="true">🧺</div><div class="progress-info"><strong>${checked}<span class="muted"> / ${ps.length}</span></strong><div class="tiny muted">${t("проверено сегодня")}</div><div class="progress"><i style="width:${ps.length ? checked / ps.length * 100 : 0}%"></i></div></div></div><div class="toolbar"><h3>${t("Что есть в кладовой")} <span class="muted tiny">${ps.length} ${t("позиций")}</span></h3><div class="actions"><label class="checkbox tiny"><input type="checkbox" id="low" ${onlyLow ? 'checked' : ''}>${t("Только мало / нет")}</label><div class="search"><input type="search" id="search" placeholder="⌕  ${t("Найти продукт…")}" value="${esc(search)}" aria-label="${t("Поиск товара")}"></div></div></div>${filtersMarkup(ps)}<div class="tabs" id="categories"></div><div class="grid" id="cards"></div><p class="footer-note">${t("Иллюстрации условные. Реальные фото можно загрузить в карточке товара. Уровни означают разное количество для каждого товара — их настраивает администратор.")}</p>`;
  if (staffMode) {
    $('#inventory').remove();
    $('.side-foot').innerHTML = t("<span class=\"dot\"></span>Режим обхода<br><span class=\"tiny\">Отмечайте остатки во всём офисе</span>");
  } else $('#inventory').onclick = () => observationModal();
  $('#search').oninput = e => {
    search = e.target.value;
    drawCards();
  };
  $('#low').onchange = e => {
    onlyLow = e.target.checked;
    drawCards();
  };
  bindFilters(stockView);drawCategoryTabs(ps,stockView);drawCards();
}
function rememberFilters(){sessionStorage.setItem('pantry_filters',JSON.stringify({supplier:supplierFilter,category,favorites:favoriteOnly}))}
function filtersMarkup(ps){
 const suppliers=suppliersFor(products(),state.suppliers||[]),categories=categoriesFor(products(),state.categories||[]);
 if(supplierFilter&&!suppliers.includes(supplierFilter))suppliers.push(supplierFilter);if(category!=='Все товары'&&!categories.includes(category))categories.push(category);
 return `<div class="product-filters"><label class="field"><span>${t('Поставщик')}</span><select id="supplier-filter"><option value="">${t('Все поставщики')}</option>${suppliers.map(v=>`<option value="${esc(v)}" ${supplierFilter===v?'selected':''}>${esc(label(v))}</option>`).join('')}</select></label><label class="field"><span>${t('Категория')}</span><select id="category-filter"><option value="Все товары">${t('Все категории')}</option>${categories.map(v=>`<option value="${esc(v)}" ${category===v?'selected':''}>${esc(label(v))}</option>`).join('')}</select></label><label class="checkbox"><input type="checkbox" id="favorite-filter" ${favoriteOnly||view==='favorites'?'checked':''} ${view==='favorites'?'disabled':''}>♡ ${t('Только избранное')}</label><button type="button" class="btn small" id="reset-product-filters">${t('Сбросить фильтры')}</button><span class="tiny muted" id="filter-count"></span></div>`;
}
function bindFilters(redraw){
 $('#supplier-filter').onchange=e=>{supplierFilter=e.target.value;rememberFilters();redraw()};
 $('#category-filter').onchange=e=>{category=e.target.value;rememberFilters();redraw()};
 $('#favorite-filter').onchange=e=>{favoriteOnly=e.target.checked;rememberFilters();redraw()};
 $('#reset-product-filters').onclick=()=>{supplierFilter='';category='Все товары';favoriteOnly=false;search='';onlyLow=false;rememberFilters();redraw()};
}
function selectedProducts(ps,extra={}){return filterProducts(ps,{supplier:supplierFilter,category,search,favorites:favoriteOnly||view==='favorites',...extra})}
function drawCategoryTabs(ps,redraw){
 const subset=filterProducts(ps,{supplier:supplierFilter,favorites:favoriteOnly||view==='favorites'});
 const cats=['Все товары',...new Set(subset.map(p=>p.category))];if(!cats.includes(category))cats.push(category);
 $('#categories').innerHTML=cats.map(c=>`<button class="chip ${category===c?'active':''}" data-cat="${esc(c)}">${esc(label(c))} <span>${c==='Все товары'?subset.length:subset.filter(p=>p.category===c).length}</span></button>`).join('');
 $$('[data-cat]').forEach(b=>b.onclick=()=>{category=b.dataset.cat;rememberFilters();redraw()});
}
function favoritesView(){
 const ps=favoriteProducts();
 $('#content').innerHTML=pagehead(t('ВАШ ВЫБОР'),t('Избранное'),t('Любимые товары для быстрого поиска. Сердечко не добавляет товар в кладовую.'))+`<div class="toolbar"><span class="muted">${ps.length} ${t('позиций')}</span><input id="search" type="search" placeholder="${t('Найти продукт…')}" value="${esc(search)}" aria-label="${t('Поиск товара')}"></div>${filtersMarkup(ps)}<div class="tabs" id="categories"></div><div class="grid" id="cards"></div>`;
 $('#search').oninput=e=>{search=e.target.value;drawCards()};bindFilters(favoritesView);drawCategoryTabs(ps,favoritesView);drawCards();
}
function favoriteButton(p,table=false){return `<button type="button" class="favorite-button ${table?'in-table':''} ${p.favorite?'selected':''}" data-favorite="${p.id}" aria-pressed="${Boolean(p.favorite)}" aria-label="${t(p.favorite?'Убрать из избранного':'Добавить в избранное')} ${esc(p.name)}" title="${t(p.favorite?'Убрать из избранного':'Добавить в избранное')}"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8Z"/></svg></button>`}
function pantryButton(p){return `<button type="button" class="btn small pantry-button" data-pantry="${p.id}">${t(p.in_pantry?'Убрать из кладовой':'Добавить в кладовую')}</button>`}
function redrawProducts(){if(view==='products')productsView();else if(view==='favorites')favoritesView();else stockView()}
function bindProductFlags(){
 $$('[data-favorite],[data-pantry]').forEach(button=>button.onclick=async()=>{
  const field=button.dataset.favorite?'favorite':'in_pantry',id=Number(button.dataset.favorite||button.dataset.pantry),p=state.products.find(p=>p.id===id);button.disabled=true;
  try{const result=await api('product-flags',{product_id:id,[field]:!p[field]});p[field]=result[field];redrawProducts();if(field==='favorite')notify(t(p.favorite?'Добавлено в избранное':'Удалено из избранного'));else notify(t(p.in_pantry?'Товар добавлен в кладовую':'Товар убран из обхода. История сохранена.'))}
  catch(e){button.disabled=false;notify(e.message,true)}
 });
 const count=$('[data-nav="favorites"] .nav-count');if(count)count.textContent=favoriteProducts().length;
}
function drawCards() {
  const base=view==='favorites'?favoriteProducts():active();
  const ps=selectedProducts(base,{low:view==='stock'&&onlyLow});$('#filter-count').textContent=`${t('Показано')}: ${ps.length} / ${base.length}`;
  $('#cards').innerHTML = ps.length ? ps.map(p => `<article class="product"><div class="product-img" style="background:${{
    'Напитки': '#eef0e9',
    'Молочные': '#eff0ec',
    'Фрукты и овощи': '#f1efe2',
    'Перекусы': '#efebe6',
    'Снеки': '#eee9e1'
  }[p.category] || '#f1f2ec'}">${badge(p)}${favoriteButton(p)}<button class="edit-icon" data-edit="${p.id}" aria-label="${t("Редактировать")} ${esc(p.name)}">↗</button>${photo(p)}</div><div class="product-body"><div class="product-meta">${esc(label(p.supplier))} · ${esc(label(p.unit))}</div><h3 class="product-name">${esc(p.name)}</h3><div class="category-caption">${esc(label(p.category))}${p.archived?` · ${t('Архив каталога')}`:''}</div>${p.in_pantry?`<div class="level-label"><span>${t("СКОЛЬКО ОСТАЛОСЬ?")}</span><span>${p.observation ? date(p.observation.date).slice(0, 5) : '—'}</span></div><div class="levels">${state.levels.map((l, i) => `<button class="level ${p.observation?.kind === 'level' && p.observation.level === i ? 'selected' : ''}" data-level="${p.id}:${i}" aria-pressed="${p.observation?.kind === 'level' && p.observation.level === i}" title="${t("Оценка для расчёта:")} ${fmt(p.thresholds[i])} ${esc(label(p.unit))}">${esc(label(l))}</button>`).join('')}</div><div class="stock-foot">${p.observation?.kind === 'exact' ? t("Точная инвентаризация") : p.observation?.kind === 'estimate' ? t("Приблизительная оценка") : p.observation ? t("Отметка уровня") : t("Остаток не указан")} · ${p.rate == null ? t("Норма пока не задана") : t("Весь офис")}</div>`:`<p class="stock-foot">${t(p.archived||!p.active?'Недоступен для заказа':'Есть в ассортименте, ещё не в кладовой')}</p>`}${!staffMode?pantryButton(p):''}</div></article>`).join('') : t("<div class=\"empty full\"><h2>Здесь пока пусто</h2><p>Добавьте товары в каталоге или измените фильтр.</p></div>");
  if(!ps.length)$('#cards').innerHTML=`<div class="empty full"><h2>${t(view==='favorites'&&favoriteProducts().length===0?'В избранном пока нет товаров':view==='stock'&&base.length===0?'В кладовой пока нет товаров':'По выбранным фильтрам ничего не найдено')}</h2><p>${t(view==='favorites'?'Нажмите сердечко у товара в каталоге или кладовой.':'Добавьте нужные товары из каталога в кладовую или сбросьте фильтры.')}</p></div>`;
  bindProductFlags();
  if (staffMode) $$('[data-edit]').forEach(b => b.remove());else bindEdit();
  $$('[data-level]').forEach(b => b.onclick = async () => {
    const [id, level] = b.dataset.level.split(':').map(Number);
    b.closest('.levels').querySelectorAll('button').forEach(x => x.disabled = true);
    try {
      await api('observation', {
        product_id: id,
        date: today(),
        kind: 'level',
        level
      });
      await load();
      redrawProducts();
      notify(t("Остаток сохранён"));
    } catch (e) {
      notify(e.message, true);
      drawCards();
    }
  });
  $$('img').forEach(img => img.onerror = () => {
    img.replaceWith(Object.assign(document.createElement('span'), {
      className: 'illustration',
      textContent: '🛍️'
    }));
  });
}
function bindEdit() {
  $$('[data-edit]').forEach(b => b.onclick = () => productModal(Number(b.dataset.edit)));
}
function modal(title, body, onSubmit) {
  const d = $('#modal');
  d.innerHTML = `<div class="modal-head"><h2>${title}</h2><button class="close" aria-label="${t("Закрыть")}">×</button></div><form id="modal-form" class="modal-body">${body}</form>`;
  d.querySelector('.close').onclick = () => d.close();
  d.onclose=()=>{if(!d.open)d.replaceChildren()};
  d.showModal();
  if (onSubmit) $('#modal-form').onsubmit = async e => {
    e.preventDefault();
    const btn = e.submitter;
    if (btn) btn.disabled = true;
    try {
      await onSubmit(new FormData(e.target));
      d.close();
      await refresh();
    } catch (err) {
      notify(err.message, true);
    } finally {
      if (btn) btn.disabled = false;
    }
  };
}
function field(label, name, value = '', type = 'text', extra = '') {
  return `<label class="field"><span>${label}</span><input type="${type}" name="${name}" value="${esc(value ?? '')}" ${extra}></label>`;
}
const foot = (text = t("Сохранить")) => `<div class="modal-foot"><button type="button" class="btn" data-cancel>${t("Отмена")}</button><button class="btn primary">${text}</button></div>`;
function cancel() {
  $('[data-cancel]').onclick = () => $('#modal').close();
}
const options = (ps, id) => ps.map(p => `<option value="${p.id}" ${p.id === id ? 'selected' : ''}>${esc(p.name)} (${esc(label(p.unit))})</option>`).join('');
function productModal(id) {
  const p = state.products.find(p => p.id === id) || {
    name: '',
    supplier: 'Maxi',
    unit: 'шт.',
    category: 'Снеки',
    office: selectedOffice,
    step: 1,
    rate: null,
    thresholds: [0, 1, 3, 6, 12, 24],
    active: true
  };
  modal(id ? t("Карточка товара") : t("Новый товар"), `<div class="form-grid">${field(t("Название как у поставщика"), 'name', p.name, 'text', 'required')}${field(t("Артикул поставщика"),'supplier_sku',p.supplier_sku)}${field(t("Поставщик"), 'supplier', p.supplier, 'text', 'required list="supplier-options"')}<datalist id="supplier-options">${suppliersFor(products(),state.suppliers||[]).map(v=>`<option value="${esc(v)}">`).join('')}</datalist><label class="field"><span>${t('Категория')}</span><select name="category" id="edit-category">${categoriesFor(products(),state.categories||[]).map(c=>`<option value="${esc(c)}" ${p.category===c?'selected':''}>${esc(label(c))}</option>`).join('')}<option value="__new__">${t('Своя категория…')}</option></select>${p.category_source==='auto'?`<small>${t('Категория подобрана автоматически. Можно изменить.')}</small>`:''}</label><label class="field" id="new-category-field" hidden><span>${t('Название новой категории')}</span><input name="custom_category" id="custom-category" maxlength="150"></label>${field(t("Единица учёта (шт., кг, л)"), 'unit', p.unit, 'text', 'required')}${field(t("Шаг заказа в единицах учёта"), 'step', p.step, 'number', 'min="0.001" step="any" required')}${field(t("Цена за единицу, RSD (неизвестна — пусто)"), 'price', p.price, 'number', 'min="0" step="any"')}${field(t("Норма на человеко-день (неизвестна — пусто)"), 'rate', p.rate, 'number', 'min="0" step="any"')}${field(t("Лимит целевого запаса (необязательно)"), 'max_stock', p.max_stock, 'number', 'min="0" step="any"')}${p.name_status==='provisional'?`<div class="full notice">${t('Название поставщика ещё не сверено. Можно связать товар с оригинальной карточкой через справочник.')}</div>`:''}<div class="full notice info">${t("Норма — расход в единицах товара на одно посещение офиса за день.")} ${esc(label(p.rate_source) || t("Настраивается вручную"))}. ${t("Для скоропортящегося задайте лимит запаса. Сроки партий пока не учитываются.")}</div><div class="full"><h3>${t("Что означает каждый уровень")}</h3><p class="tiny muted" style="margin:5px 0 12px">${t("Представительное количество для расчёта, не границы интервалов. «Нет» всегда 0. Настройки сразу влияют на последнюю отметку уровня.")}</p><div class="thresholds">${state.levels.map((l, i) => field(esc(label(l)), 't' + i, p.thresholds[i], 'number', `step="any" min="0" required ${i === 0 ? 'readonly' : ''}`)).join('')}</div></div>${field(t("Ссылка на товар в магазине"), 'url', p.url, 'url', 'placeholder="https://…"')}${field(t("Ссылка на фото"), 'image', (p.image?.startsWith('data:')||p.image?.startsWith('/assets/')) ? '' : p.image, 'url', 'placeholder="https://…"')}<label class="field full"><span>${t("Или загрузите реальное фото (до 2 МБ)")}</span><input type="file" name="photo" accept="image/png,image/jpeg,image/webp"></label><label class="field full"><span>${t("Примечание")}</span><textarea name="notes">${esc(p.notes)}</textarea></label>${p.archived?`<label class="checkbox full"><input type="checkbox" name="restore">${t('Восстановить из архива')}</label>`:''}<label class="checkbox full"><input type="checkbox" name="active" ${p.active ? 'checked' : ''}>${t('Доступен для заказа')}</label><label class="checkbox full"><input type="checkbox" name="in_pantry" ${p.in_pantry?'checked':''}>${t('Учитывать в кладовой')}</label></div>${foot()}`, async f => {
    let image = f.get('image');
    const file = f.get('photo');
    if (file?.size) {
      if (file.size > 2e6) throw Error(t("Фото должно быть меньше 2 МБ"));
      if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) throw Error(t("Нужен PNG, JPEG или WebP"));
      image = await dataURL(file);
    } else if (!image && (p.image?.startsWith('data:')||p.image?.startsWith('/assets/'))) image = p.image;
    await api('product', {
      ...p,
      ...Object.fromEntries(f),
      id,
      category:f.get('category')==='__new__'?String(f.get('custom_category')).trim():f.get('category'),
      category_source:'manual',
      in_pantry:f.has('in_pantry'),
      active: f.has('active'),
      archived: Boolean(p.archived)&&!f.has('restore'),
      image,
      thresholds: state.levels.map((_, i) => Number(f.get('t' + i)))
    });
    notify(t("Карточка сохранена"));
  });
  cancel();$('#edit-category').onchange=e=>{const custom=e.target.value==='__new__';$('#new-category-field').hidden=!custom;$('#custom-category').required=custom};
}
function dataURL(file) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(r.result);
    r.onerror = () => reject(Error(t("Не удалось прочитать файл")));
    r.readAsDataURL(file);
  });
}
function observationModal(pid) {
  const current=products().filter(p=>!p.archived);if (!current.length) return notify(t("Сначала добавьте товар"), true);
  modal(t("Инвентаризация"), `<div class="notice info">${t("Указывайте суммарный остаток во всём офисе на конец выбранного дня, после всех поступлений. Только точные инвентаризации используются для калибровки.")}</div><div class="form-grid"><label class="field full"><span>${t("Товар")}</span><select name="product_id">${options(current, pid)}</select></label>${field(t("Дата"), 'date', today(), 'date', 'required max="' + today() + '"')}<label class="field"><span>${t("Тип")}</span><select name="kind"><option value="exact">${t("Точное количество")}</option><option value="estimate">${t("Приблизительная оценка")}</option></select></label>${field(t("Количество в единицах товара"), 'qty', '', 'number', 'min="0" step="any" required')}<label class="field"><span>${t("Комментарий")}</span><input name="note" placeholder="${t("Склад + кухни")}"></label></div>${foot()}`, async f => {
    await api('observation', Object.fromEntries(f));
    notify(t("Остаток сохранён"));
  });
  cancel();
}
function productsView() {
  const base=products().filter(p=>Boolean(p.archived)===catalogShowArchived);const ps=selectedProducts(base);
  $('#content').innerHTML = pagehead(t("НАСТРОЙКИ КЛАДОВОЙ"), t('Каталог для заказа'),t('Ассортимент поставщиков. Добавляйте нужные товары в кладовую и избранное.'), `<button class="btn primary" id="add-product">＋ ${t("Добавить товар")}</button>`) + `<div class="toolbar"><input type="search" id="catalog-search" placeholder="⌕  ${t("Поиск по каталогу")}" value="${esc(search)}"><button class="btn" id="exact">${t("Точная инвентаризация")}</button><label class="checkbox tiny"><input type="checkbox" id="show-archived" ${catalogShowArchived?'checked':''}>${t('Архив')}</label></div>${filtersMarkup(base)}<div class="table-wrap"><table><thead><tr><th>${t("Товар")}</th><th>${t("Поставщик")}</th><th>${t("Норма / чел.-день")}</th><th>${t("Остаток")}*</th><th>${t("Настройки")}</th></tr></thead><tbody>${ps.map(p => `<tr><td class="name"><div class="catalog-name">${favoriteButton(p,true)}<strong>${esc(p.name)}</strong></div>${p.name_status==='provisional'?`<span class="badge warn">${t('Название не сверено')}</span>`:''}<small>${esc(p.supplier_sku||'')} · ${esc(label(p.category))} · ${esc(label(p.unit))} ${p.active ? '' : t('· недоступен для заказа')}</small></td><td>${esc(label(p.supplier))}</td><td>${fmt(p.rate)}<div class="tiny muted">${p.rate == null ? t("Нужно настроить") : esc(label(p.rate_source))}</div></td><td>${fmt(p.estimated_stock)}<div class="tiny muted">${date(p.observation?.date)}</div></td><td><div class="actions"><button class="btn small" data-edit="${p.id}">${t("Изменить")}</button><button class="btn small" data-calibrate="${p.id}">${t("Калибровка")}</button>${pantryButton(p)}</div></td></tr>`).join('')}</tbody></table></div><p class="footer-note">* ${t("Последний остаток + поступления после даты проверки. Расход после проверки не вычитается: обновляйте отметки перед расчётом заказа.")}</p>`;
  bindFilters(productsView);$('#filter-count').textContent=`${t('Показано')}: ${ps.length} / ${base.length}`;bindProductFlags();
  $('#show-archived').onchange=e=>{catalogShowArchived=e.target.checked;productsView()};
  $('#add-product').onclick = () => productModal();
  $('#exact').onclick = () => observationModal();
  const btn=document.createElement('button');btn.className='btn';btn.id='supplier-catalog';btn.textContent=t('Справочники поставщиков');btn.onclick=()=>supplierCatalogue();$('.toolbar').append(btn);
  $('#catalog-search').oninput = e => {
    const pos = e.target.selectionStart;
    search = e.target.value;
    productsView();
    $('#catalog-search').focus();
    $('#catalog-search').setSelectionRange(pos, pos);
  };
  bindEdit();
  $$('[data-calibrate]').forEach(b => b.onclick = () => calibrationModal(Number(b.dataset.calibrate)));
}
async function calibrationModal(pid) {
  try {
    const result = await api('calibrate/' + pid);
    const p = state.products.find(p => p.id === pid);
    modal(t("Уточнить норму расхода"), `<h3>${esc(p.name)}</h3><div class="notice ${result.error ? '' : 'info'}" style="margin-top:15px">${esc(t(result.error || result.note))}</div>${result.error ? '' : `<div class="kpi-row"><div><span class="muted tiny">${t("Убыль за период")}</span><h2>${fmt(result.used)} ${esc(label(p.unit))}</h2></div><div><span class="muted tiny">${t("Человеко-дни")}</span><h2>${fmt(result.visits)}</h2></div><div><span class="muted tiny">${t("Новая норма")}</span><h2>${fmt(result.rate)}</h2></div></div><p class="help-text" style="margin-top:15px">${date(result.start)} — ${date(result.end)}. ${t("Начальный остаток + поступления (")}${fmt(result.received)}) − ${t("конечный остаток. Первый день исключён, последний включён. Подтвердите полноту поставок и отсутствие неучтённых перемещений.")}</p><label class="checkbox" style="margin-top:15px"><input type="checkbox" required>${t("Проверил данные периода")}</label>${foot(t("Применить норму"))}`}`, result.error ? null : async () => {
      await api('product', {
        ...p,
        rate: result.rate,
        rate_source: `Точные остатки ${result.start}–${result.end}`
      });
      notify(t("Норма обновлена"));
    });
    if (!result.error) cancel();
  } catch (e) {
    notify(e.message, true);
  }
}
function rowsForOrder() {
  return active().filter(p=>p.active&&!p.archived).map(p => {
    const r = recommend(p, visits, buffer);
    return {
      p,
      ...r,
      orderQty: overrides[p.id] ?? r.qty
    };
  });
}
function orderView() {
  const rows = rowsForOrder(),
    buy = rows.filter(r => r.orderQty > 0),
    unknown = rows.filter(r => r.qty == null),
    stale = rows.filter(r => !r.p.observation || age(r.p.observation.date) > 7);
  const cost = buy.reduce((s, r) => s + (r.p.price ?? 0) * r.orderQty, 0),
    unknownPrices = buy.filter(r => r.p.price == null).length;
  $('#content').innerHTML = pagehead(t("ПЛАНИРОВАНИЕ"), t("Закупка без догадок"), t("Посещаемость → прогноз расхода → список по поставщикам."), `<button class="btn primary" id="save-order">${t("Сохранить список")}</button>`) + `<div class="panel"><div class="form-grid">${field(t("Прогноз человеко-дней на период"), 'visits', visits, 'number', 'id="visits" min="0" step="1" required')}${field(t("Страховой запас, %"), 'buffer', buffer * 100, 'number', 'id="buffer" min="0" max="200" step="1" required')}<div class="full help-text">${t("Человеко-дни — сумма посещений за планируемый период. Например: 48 человек × 5 дней")} = 240. ${t("Изменение прогноза сбрасывает ручные количества. Период поставки выбирайте с учётом свежести продуктов.")}</div></div></div><div class="stats"><div class="stat"><label>${t("К заказу")}</label><strong>${buy.length}</strong><small>${t("товарных позиций")}</small></div><div class="stat"><label>${t("По известным ценам")}</label><strong>${fmt(cost)} <span class="tiny">RSD</span></strong><small>${unknownPrices ? t("Нет цены у ") + unknownPrices + t(" поз.") : t("Оценка, не сумма счёта")}</small></div><div class="stat"><label>${t("Нужна настройка")}</label><strong>${unknown.length}</strong><small>${t("нет нормы или остатка")}</small></div></div>${stale.length ? `<div class="notice">${t("У")} ${stale.length} ${t("товаров остатки старше 7 дней или отсутствуют. Расход после проверки не вычитается. Обновите отметки перед закупкой.")}</div>` : ''}<div class="toolbar"><h3>${t("Рекомендованный список")}</h3><div class="actions"><button class="btn" id="export-order">↓ ${t("Скачать CSV")}</button><button class="btn" id="copy-order">${t("Копировать список")}</button></div></div><div class="table-wrap"><table><thead><tr><th>${t("Товар")}</th><th>${t("Остаток")}</th><th>${t("Расход")}</th><th>${t("Цель с резервом")}</th><th>${t("Заказать")}</th><th></th></tr></thead><tbody>${rows.map(r => `<tr><td class="name"><strong>${esc(r.p.name)}</strong><small>${esc(label(r.p.supplier))} · ${t("шаг")} ${fmt(r.p.step)} ${esc(label(r.p.unit))}</small>${r.warning ? `<small style="color:#a17a31">${esc(t(r.warning))}</small>` : ''}${r.p.rate_source?.includes('Excel') ? t("<small>Приблизительная норма из Excel</small>") : ''}</td><td>${fmt(r.stock)}</td><td>${fmt(r.need)}</td><td>${fmt(r.target)}</td><td><input class="number" type="number" min="0" step="any" data-qty="${r.p.id}" value="${r.orderQty ?? ''}" placeholder="—" aria-label="${t("Заказать")} ${esc(r.p.name)}"> ${esc(label(r.p.unit))}</td><td><button class="text-link" data-edit="${r.p.id}">${t("Настроить")}</button></td></tr>`).join('')}</tbody></table></div><details class="panel"><summary>${t("Как считается заказ")}</summary><p class="help-text">${t("Расход")} = ${t("норма × человеко-дни. Цель")} = ${t("расход × (1 + резерв), с ограничением лимита запаса, если он задан. Заказ")} = max(0, ${t("цель − оценка остатка), округлённый вверх до шага упаковки. Уровень остатка заменяется количеством из настроек товара. При неизвестной норме или остатке автоматическая рекомендация отсутствует; количество можно ввести вручную. Лимит не гарантирует срок годности — проверяйте партии отдельно.")}</p></details><div class="section-head"><h2>${t("Сохранённые списки")}</h2></div><div class="table-wrap"><table><thead><tr><th>${t("Создан")}</th><th>${t("Посещения")}</th><th>${t("Позиций")}</th><th>${t("Список")}</th></tr></thead><tbody>${state.orders.filter(o => o.office === selectedOffice).map(o => `<tr><td>${date(o.created_at.slice(0, 10))}</td><td>${fmt(o.visits)}</td><td>${o.lines.length}</td><td><button class="text-link" data-saved-order="${o.id}">${t("Открыть")}</button></td></tr>`).join('') || t("<tr><td colspan=\"4\" class=\"muted\">Пока нет сохранённых списков. Список не меняет остатки — поставку вносят после получения.</td></tr>")}</tbody></table></div>`;
  ['visits', 'buffer'].forEach(id => $('#' + id).onchange = e => {
    if (!e.target.checkValidity()) return e.target.reportValidity();
    if (id === 'visits') visits = Number(e.target.value);else buffer = Number(e.target.value) / 100;
    overrides = {};
    orderView();
  });
  $$('[data-qty]').forEach(el => el.onchange = e => {
    if (!e.target.checkValidity()) return e.target.reportValidity();
    if (e.target.value === '') delete overrides[e.target.dataset.qty];else overrides[e.target.dataset.qty] = Number(e.target.value);
    orderView();
  });
  bindEdit();
  $('#export-order').onclick = () => exportOrder(rowsForOrder().filter(r => r.orderQty > 0));
  $('#copy-order').onclick = () => copyOrder(rowsForOrder().filter(r => r.orderQty > 0));
  $('#save-order').onclick = async () => {
    const lines = rowsForOrder().filter(r => r.orderQty > 0).map(r => ({
      product_id: r.p.id,
      name: r.p.name,
      supplier: r.p.supplier,
      unit: r.p.unit,
      qty: r.orderQty,
      price: r.p.price,
      url: r.p.url
    }));
    try {
      await api('order', {
        office: selectedOffice,
        visits,
        buffer,
        lines
      });
      await refresh();
      notify(t("Список сохранён. Остатки не изменены."));
    } catch (e) {
      notify(e.message, true);
    }
  };
  $$('[data-saved-order]').forEach(b => b.onclick = () => {
    const o = state.orders.find(o => o.id === Number(b.dataset.savedOrder));
    modal(t("Список закупки"), `<p class="muted">${esc(o.office)} · ${fmt(o.visits)} ${t("человеко-дней")}</p><div class="table-wrap" style="margin-top:15px"><table>${o.lines.map(l => `<tr><td class="name">${esc(l.name)}<small>${esc(l.supplier)}</small></td><td>${fmt(l.qty)} ${esc(label(l.unit))}</td></tr>`).join('')}</table></div><button class="btn" id="saved-csv" type="button">${t("Скачать CSV")}</button>`);
    $('#saved-csv').onclick = () => exportOrder(o.lines.map(l => ({
      p: l,
      orderQty: l.qty
    })), o.office);
  });
}
function exportOrder(rows, o = selectedOffice) {
  const cell = x => '"' + String(x ?? '').replaceAll('"', '""').replace(/^[=+@-]/, "'$&") + '"';
  const content = [[t("Офис"), t("Поставщик"), t("Товар"), t("Количество"), t("Ед."), t("Цена RSD"), t("Ссылка")], ...rows.map(r => [o, r.p.supplier, r.p.name, r.orderQty, r.p.unit, r.p.price, r.p.url])].map(a => a.map(cell).join(';')).join('\r\n');
  download('pantry-order.csv', '\uFEFF' + content, 'text/csv;charset=utf-8');
}
async function copyOrder(rows) {
  const text = selectedOffice + t(" · список закупки\n") + [...new Set(rows.map(r => r.p.supplier))].map(s => '\n' + s + '\n' + rows.filter(r => r.p.supplier === s).map(r => `${r.p.name} — ${fmt(r.orderQty)} ${r.p.unit}${r.p.url ? ' · ' + r.p.url : ''}`).join('\n')).join('\n');
  try {
    await navigator.clipboard.writeText(text);
    notify(t("Список скопирован"));
  } catch {
    download('pantry-order.txt', text);
    notify(t("Список сохранён в файл"));
  }
}
function deliveriesView() {
  const ds = state.deliveries.filter(d => d.office === selectedOffice);
  $('#content').innerHTML = pagehead(t("ИСТОРИЯ ПОСТАВОК"), t("Всё, что приехало"), t("Один инвойс и отпремница — одна поставка. Учитываем товары один раз."), `<button class="btn primary" id="new-delivery">＋ ${t("Добавить поставку")}</button>`) + `<div class="notice info">PDF ${t("сохраняется как первичный документ. В этом MVP позиции вводятся и проверяются вручную: автоматического OCR и подключения к 1С пока нет. История из Excel не прибавляется повторно к остаткам на 19 октября.")}</div><div class="stats"><div class="stat"><label>${t("Поставок")}</label><strong>${ds.length}</strong><small>${t("в этом офисе")}</small></div><div class="stat"><label>${t("Поставщиков в истории")}</label><strong>${new Set(ds.map(d => d.supplier)).size}</strong><small>${t("из вашей таблицы и новых записей")}</small></div><div class="stat"><label>${t("Источник")}</label><strong style="font-size:21px">Excel + ${t("вручную")}</strong><small>${t("с полной историей изменений")}</small></div></div><div class="table-wrap"><table><thead><tr><th>${t("Дата")}</th><th>${t("Документ")}</th><th>${t("Поставщик")}</th><th>${t("Строк")}</th><th>${t("Сумма по ценам")}*</th><th></th></tr></thead><tbody>${ds.map(d => `<tr><td>${date(d.date)}</td><td>${esc(d.number)}${d.file_hash ? ` <a class="tiny" href="/api/file/${esc(d.file_hash)}">PDF ↓</a>` : ''}</td><td>${esc(d.supplier)}</td><td>${d.lines.length}</td><td>${d.lines.every(l => l.price != null) ? fmt(d.lines.reduce((s, l) => s + l.qty * l.price, 0)) + ' RSD' : '—'}</td><td><button class="btn small" data-delivery="${d.id}">${t("Открыть / изменить")}</button></td></tr>`).join('') || t("<tr><td colspan=\"6\">Поставок пока нет</td></tr>")}</tbody></table></div><p class="footer-note">* ${t("Цены строк вводятся за единицу с НДС после скидок. Сумма не заменяет бухгалтерскую сверку. Сохранение поставки меняет расчётный остаток только после даты последней проверки.")}</p><button class="btn" id="audit">${t("Журнал изменений")}</button>`;
  $('#new-delivery').onclick = () => deliveryModal();
  $$('[data-delivery]').forEach(b => b.onclick = () => deliveryModal(Number(b.dataset.delivery)));
  $('#audit').onclick = auditModal;
}
function deliveryModal(id) {
  const current=products().filter(p=>!p.archived);if (!current.length&&!id) return notify(t("Сначала добавьте товары в этом офисе"), true);
  const d = state.deliveries.find(d => d.id === id) || {
    office: selectedOffice,
    date: today(),
    supplier: 'Maxi',
    number: '',
    notes: '',
    lines: [{
      product_id: current[0].id,
      qty: 1,
      price: null
    }]
  };
  let lines = d.lines.map(l => ({
    ...l
  }));
  modal(id ? t("Редактировать поставку") : t("Новая поставка"), `<div class="form-grid">${field(t("Дата получения"), 'date', d.date, 'date', 'required max="' + today() + '"')}${field(t("Номер инвойса / накладной"), 'number', d.number, 'text', 'required')}${field(t("Поставщик"), 'supplier', d.supplier, 'text', 'required')}<label class="field"><span>PDF (${t("необязательно, до 15 МБ)")}</span><input name="pdf" type="file" accept="application/pdf"></label><label class="field full"><span>${t("Комментарий")}</span><input name="notes" value="${esc(d.notes)}"></label></div><div class="notice" style="margin-top:18px">${t("Количество — в единицах каталога: 2 упаковки по 24 банки")} = 48 ${t("банок. Цена — за одну единицу с НДС после скидок. Проверьте дату, офис и отсутствие дублей.")}</div><div class="line-item tiny muted"><span>${t("Товар")}</span><span>${t("Кол-во")}</span><span>${t("Цена RSD")}</span><span></span></div><div id="delivery-lines"></div><button type="button" class="btn small" id="add-line">＋ ${t("Позиция")}</button>${id ? `<button type="button" class="btn small danger" id="delete-delivery">${t("Удалить поставку")}</button>` : ''}<label class="checkbox" style="margin-top:20px"><input type="checkbox" required>${t("Проверил позиции. Товары уже получены.")}</label>${foot(id ? t("Сохранить изменения") : t("Подтвердить поступление"))}`, async f => {
    const payload = {
      ...d,
      ...Object.fromEntries(f),
      id,
      lines
    };
    const file = f.get('pdf');
    if (file?.size) {
      if (file.size > 15e6) throw Error(t("PDF должен быть меньше 15 МБ"));
      payload.attachment = {
        base64: (await dataURL(file)).split(',')[1]
      };
    }
    delete payload.pdf;
    await api('delivery', payload);
    notify(t("Поступление сохранено"));
  });
  cancel();
  function draw() {
    $('#delivery-lines').innerHTML = lines.map((l, i) => `<div class="line-item"><select aria-label="${t("Товар в строке")} ${i + 1}" data-line="${i}" data-key="product_id">${options(products().filter(p=>!p.archived||p.id===l.product_id), l.product_id)}</select><input type="number" aria-label="${t("Количество в строке")} ${i + 1}" data-line="${i}" data-key="qty" value="${l.qty}" required min="0.001" step="any"><input type="number" aria-label="${t("Цена в строке")} ${i + 1}" data-line="${i}" data-key="price" value="${l.price ?? ''}" min="0" step="any"><button class="close" type="button" data-remove="${i}" aria-label="${t("Удалить строку")}">×</button></div>`).join('');
    $$('[data-line]').forEach(el => el.onchange = () => {
      lines[Number(el.dataset.line)][el.dataset.key] = el.value === '' ? null : Number(el.value);
    });
    $$('[data-remove]').forEach(b => b.onclick = () => {
      lines.splice(Number(b.dataset.remove), 1);
      draw();
    });
  }
  $('#add-line').onclick = () => {
    lines.push({
      product_id: current[0].id,
      qty: 1,
      price: null
    });
    draw();
  };
  if (id) $('#delete-delivery').onclick = async () => {
    if (!confirm(t("Удалить поставку? Это изменит расчётные остатки и калибровку. Действие останется в журнале."))) return;
    try {
      await api('delete', {
        kind: 'delivery',
        id
      });
      $('#modal').close();
      await refresh();
      notify(t("Поставка удалена"));
    } catch (e) {
      notify(e.message, true);
    }
  };
  draw();
}
function attendanceView() {
  const as = state.attendance.filter(a => a.office === selectedOffice);
  $('#content').innerHTML = pagehead(t("ОФИС В ЦИФРАХ"), t("Посещаемость"), t("Фактические человеко-дни помогают уточнять нормы потребления."), `<button class="btn primary" id="add-attendance">＋ ${t("Добавить день")}</button>`) + `<div class="stats"><div class="stat"><label>${t("Человеко-дней в истории")}</label><strong>${fmt(as.reduce((s, a) => s + a.count, 0))}</strong><small>${t("сумма всех дневных посещений")}</small></div><div class="stat"><label>${t("Дней с данными")}</label><strong>${as.length}</strong><small>${t("пустой день не равен нулю")}</small></div><div class="stat"><label>${t("Последний день")}</label><strong style="font-size:23px">${date(as[0]?.date)}</strong><small>${esc(selectedOffice)}</small></div></div><div class="panel"><div class="section-head"><h3>${t("Импорт посещаемости из CSV")}</h3><button class="text-link" id="template">${t("Шаблон CSV")}</button></div><p class="help-text">${t("Колонки: date,count (дата YYYY-MM-DD, целое количество посещений). Разделитель — запятая или точка с запятой. Перед сохранением покажем строки для проверки; совпавшие даты будут заменены.")}</p><input type="file" id="attendance-csv" accept=".csv,text/csv" style="margin-top:12px"></div><div class="table-wrap"><table><thead><tr><th>${t("Дата")}</th><th>${t("Посещений")}</th><th>${t("Примечание")}</th><th></th></tr></thead><tbody>${as.map(a => `<tr><td>${date(a.date)}</td><td>${fmt(a.count)}</td><td class="name">${esc(a.notes)}</td><td><button class="text-link" data-attendance="${a.date}">${t("Изменить")}</button></td></tr>`).join('')}</tbody></table></div><div class="section-head"><h2>${t("История проверок остатков")}</h2><button class="btn small" id="count-stock">${t("Новая проверка")}</button></div><div class="table-wrap"><table><thead><tr><th>${t("Дата")}</th><th>${t("Товар")}</th><th>${t("Тип")}</th><th>${t("Количество / уровень")}</th><th></th></tr></thead><tbody>${state.observations.filter(o => products().some(p => p.id === o.product_id)).slice().reverse().map(o => `<tr><td>${date(o.date)}</td><td class="name">${esc(state.products.find(p => p.id === o.product_id)?.name)}<small>${esc(o.note)}</small></td><td>${{
    exact: t("Точный"),
    estimate: t("Оценка"),
    level: t("Уровень")
  }[o.kind]}</td><td>${o.kind === 'level' ? esc(label(state.levels[o.level])) : fmt(o.qty)}</td><td><button class="text-link" data-delete-observation="${o.id}">${t("Удалить ошибку")}</button></td></tr>`).join('')}</tbody></table></div>`;
  $('#add-attendance').onclick = () => attendanceModal();
  $$('[data-attendance]').forEach(b => b.onclick = () => attendanceModal(as.find(a => a.date === b.dataset.attendance)));
  $('#count-stock').onclick = () => observationModal();
  $('#template').onclick = () => download('attendance-template.csv', 'date,count\n2026-10-26,48\n2026-10-27,52\n', 'text/csv');
  $('#attendance-csv').onchange = async e => {
    try {
      const file = e.target.files[0];
      if (!file) return;
      if (file.size > 1e6) throw Error(t("CSV слишком большой"));
      const text = (await file.text()).replace(/^\uFEFF/, '').trim(),
        sep = text.split('\n')[0].includes(';') ? ';' : ',';
      const raw = text.split(/\r?\n/).map(l => l.split(sep).map(v => v.trim()));
      if (raw[0].join(',') !== 'date,count') throw Error(t("Заголовок должен быть date,count"));
      const records = raw.slice(1).map(([date, count]) => ({
        office: selectedOffice,
        date,
        count: Number(count)
      }));
      if (!records.length || records.some(a => !/^\d{4}-\d{2}-\d{2}$/.test(a.date) || !Number.isInteger(a.count) || a.count < 0)) throw Error(t("Проверьте даты и целые неотрицательные количества"));
      if (new Set(records.map(r => r.date)).size !== records.length) throw Error(t("В CSV повторяются даты"));
      modal(t("Проверка импорта"), `<p>${esc(selectedOffice)} · ${records.length} ${t("строк")}</p><div class="notice">${t("Существующие записи на эти даты будут заменены.")}</div><div class="table-wrap"><table>${records.map(a => `<tr><td>${esc(a.date)}</td><td>${a.count}</td></tr>`).join('')}</table></div>${foot(t("Подтвердить импорт"))}`, async () => {
        await api('attendance', {
          records
        });
        notify(t("Посещаемость импортирована"));
      });
      cancel();
    } catch (err) {
      notify(err.message, true);
    }
  };
  $$('[data-delete-observation]').forEach(b => b.onclick = async () => {
    if (!confirm(t("Удалить ошибочную проверку? Предыдущая запись снова станет актуальной."))) return;
    try {
      await api('delete', {
        kind: 'observation',
        id: Number(b.dataset.deleteObservation)
      });
      await refresh();
      notify(t("Проверка удалена"));
    } catch (e) {
      notify(e.message, true);
    }
  });
}
function attendanceModal(a) {
  modal(a ? t("Изменить посещаемость") : t("Добавить посещаемость"), `<div class="form-grid">${field(t("Дата"), 'date', a?.date || today(), 'date', 'required ' + (a ? 'readonly' : ''))}${field(t("Количество посещений"), 'count', a?.count ?? '', 'number', 'required min="0" step="1"')}<label class="field full"><span>${t("Примечание")}</span><textarea name="notes">${esc(a?.notes)}</textarea></label></div>${foot()}`, async f => {
    await api('attendance', {
      ...Object.fromEntries(f),
      office: selectedOffice
    });
    notify(t("Посещаемость сохранена"));
  });
  cancel();
}
async function auditModal() {
  try {
    const rows = await api('audit');
    modal(t("Журнал изменений"), `<p class="help-text">${t("Последние 300 действий. История сохраняет прежние и новые значения. Все пользователи MVP используют общую учётную запись.")}</p><div class="table-wrap" style="margin-top:15px"><table><thead><tr><th>${t("Время")}</th><th>${t("Действие")}</th><th>${t("Запись")}</th></tr></thead><tbody>${rows.map(r => `<tr><td>${new Date(r.at).toLocaleString(locale())}</td><td>${esc(r.action)}</td><td>${esc(r.kind)} #${esc(r.entity_id)}</td></tr>`).join('') || t("<tr><td>Изменений пока нет</td></tr>")}</tbody></table></div><a class="btn" href="/api/backup">${t("Полная история в JSON")}</a>`);
  } catch (e) {
    notify(e.message, true);
  }
}
try {
  $('#app').textContent=t('Загружаем кладовую…');
  await load();
  render();
} catch (e) {
  $('#app').innerHTML = t("<div class=\"empty\"><h2>Не удалось подключиться</h2><p>Проверьте, запущен ли сервер, и обновите страницу. Несохранённые изменения не отправлены.</p><button class=\"btn\" onclick=\"location.reload()\">Повторить</button></div>");
  notify(e.message, true);
}

async function supplierCatalogue(supplier='Maxi',query='',page=1){
 try{
  const data=await api('supplier-catalog?'+new URLSearchParams({supplier,q:query,page}));
  modal(t('Справочники поставщиков'),`<div class="notice info">${t('Название, артикул, фото и ссылка сохраняются из источника без перевода. Нормы и остатки не изменяются.')}</div><div class="toolbar"><select id="catalog-supplier">${Object.keys(data.suppliers).map(s=>`<option ${s===supplier?'selected':''}>${esc(s)}</option>`).join('')}</select><input id="supplier-search" placeholder="${t('Поиск в справочнике')}" value="${esc(query)}"></div><div class="actions"><label class="btn" for="catalog-file">${t('Загрузить CSV / JSON / HTML')}</label><input hidden multiple type="file" id="catalog-file" accept=".csv,.json,.html,.htm"><label class="btn" for="catalog-folder">${t('Выбрать папку')}</label><input hidden multiple type="file" id="catalog-folder" webkitdirectory directory><button class="btn" type="button" id="replace-catalog-files">${t('Заменить каталог из файлов')}</button><button type="button" class="btn" id="store-export">${t('Выгрузить из магазина')}</button><a class="btn" target="_blank" rel="noopener noreferrer" href="${data.suppliers[supplier]}">${t('Открыть магазин')} ↗</a><button type="button" class="text-link" id="catalog-template">${t('Шаблон CSV')}</button></div><p class="help-text" style="margin:15px 0">${t('Это справочник, а не полная синхронизация магазина. Цены и наличие относятся к моменту выгрузки.')}</p><div class="table-wrap"><table><thead><tr><th>${t('Товар')}</th><th>${t('Артикул поставщика')}</th><th></th></tr></thead><tbody>${data.rows.map(r=>`<tr><td class="name"><strong>${esc(r.name)}</strong>${r.url?`<small><a href="${esc(r.url)}" target="_blank" rel="noopener noreferrer">${t('Открыть магазин')} ↗</a></small>`:''}</td><td>${esc(r.sku||'—')}</td><td><button type="button" class="btn small" data-select-catalog="${r.id}">${t('Добавить в офис')} / ${t('Связать с товаром')}</button></td></tr>`).join('')||`<tr><td>${t('Пока нет товаров')}</td></tr>`}</tbody></table></div><div class="actions"><button class="btn small" id="catalog-prev" type="button" ${page<=1?'disabled':''}>${t('Предыдущая')}</button><span class="tiny">${t('Страница')} ${page} · ${data.total}</span><button class="btn small" id="catalog-next" type="button" ${page*40>=data.total?'disabled':''}>${t('Следующая')}</button></div>`);
  $('#catalog-supplier').onchange=e=>supplierCatalogue(e.target.value);
  $('#supplier-search').onchange=e=>supplierCatalogue(supplier,e.target.value);
  $('#catalog-prev').onclick=()=>supplierCatalogue(supplier,query,page-1);$('#catalog-next').onclick=()=>supplierCatalogue(supplier,query,page+1);
  $('#store-export').onclick=exporterModal;
  $('#catalog-template').onclick=()=>download('supplier-products.csv','name,sku,url,image,price,currency,unit,category\n','text/csv');
  let requestedMode='supplier';
  $('#replace-catalog-files').onclick=()=>{requestedMode='replace';$('#catalog-file').click()};
  $('label[for="catalog-file"]').onclick=()=>{requestedMode='supplier'};
  $('#catalog-file').onchange=e=>{const mode=requestedMode;requestedMode='supplier';prepareCatalogFiles(e.target.files,supplier,mode)};
  $('#catalog-folder').onchange=e=>prepareCatalogFiles(e.target.files,supplier);
  $$('[data-select-catalog]').forEach(b=>b.onclick=()=>selectCatalogue(data.rows.find(r=>r.id===Number(b.dataset.selectCatalog))));
 }catch(e){notify(e.message,true)}
}
async function prepareCatalogFiles(files,supplier,mode='supplier'){
 const selected=importFiles(files),ignored=files.length-selected.length;
 if(!selected.length)return notify(t('Выберите файлы products-*.json или папку сбора'),true);
 if(selected.some(f=>f.size>10e6)||selected.reduce((s,f)=>s+f.size,0)>1_000_000_000)return notify(t('Файл слишком большой'),true);
 let cancelled=false;const dialog=$('#modal');
 modal(t('Подготовка импорта'),`<p class="help-text">${t('Проверяем файлы. Каталог пока не меняется.')}</p><progress id="catalog-prepare-progress" max="${selected.length}" value="0" style="width:100%"></progress><p id="catalog-prepare-status" role="status"></p><button type="button" id="cancel-prepare" class="btn">${t('Отмена')}</button>`);
 const stop=()=>{cancelled=true};dialog.addEventListener('close',stop);$('#cancel-prepare').onclick=()=>dialog.close();
 const all=[],errors=[];let total=0;
 try{
  for(let i=0;i<selected.length;i++){
   if(cancelled)return;const file=selected[i];$('#catalog-prepare-status').textContent=`${i+1} / ${selected.length} · ${file.name}`;
   try{const ext=file.name.split('.').pop().toLowerCase();const data=await api('catalog/preview',{supplier,content:await file.text(),format:['html','htm'].includes(ext)?'html':ext});
    all.push(...data.rows);total+=data.total;errors.push(...data.errors.map(e=>({...e,file:file.name})))
   }catch(e){errors.push({file:file.name,error:e.message})}
   if(cancelled)return;$('#catalog-prepare-progress').value=i+1;
  }
  const rows=mergeCatalogRows(all);
  if(!cancelled)catalogPreview(supplier,{rows,errors,total,files:selected.length,ignored,duplicates:all.length-rows.length},mode);
 }finally{dialog.removeEventListener('close',stop)}
}
function catalogPreview(supplier,data,initialMode='supplier'){
 let jobId=null,chosen=null;const saved=new Set();
 modal(t('Проверка импорта'),`<p>${esc(supplier)} · ${t('Файлов')}: ${data.files||1} · ${t('Товаров')}: ${data.rows.length}</p><div class="notice info">${t('Фото уже находятся внутри products-*.json. Папка images и report.json отдельно не нужны.')}</div><p class="tiny muted">${t('Пропущено служебных файлов')}: ${data.ignored||0} · ${t('Повторов')}: ${data.duplicates||0}</p>${data.errors.length?`<div class="notice">${data.errors.map(e=>`${esc(e.file||'')} ${e.row?'#'+e.row:''}: ${esc(t(e.error))}`).join('<br>')}</div>`:''}<label class="field" style="margin:15px 0"><span>${t('Что сделать с товарами')}</span><select name="import_mode" id="catalog-import-mode"><option value="supplier">${t('Только в справочник поставщика')}</option><option value="add">${t('Добавить в товары CRM')}</option><option value="replace">${t('Заменить каталог текущего офиса')}</option></select></label><div class="notice" id="catalog-replace-warning" hidden>${esc(label(selectedOffice))}: ${t('Старые карточки уйдут в архив. История сохранится. Новый каталог появится только после загрузки всех выбранных товаров.')}</div><div class="notice" id="catalog-replace-errors" hidden>${t('Для замены исправьте ошибки во всех файлах.')}</div><label class="checkbox" style="margin:15px 0"><input type="checkbox" checked id="select-all">${t('Выбрать все')}</label><div class="table-wrap" style="max-height:40vh"><table><thead><tr><th></th><th>${t('Название из источника')}</th><th>${t('Артикул поставщика')}</th><th>${t('Ед.')}</th><th>${t('Цена RSD')}</th><th>${t('Фото')}</th></tr></thead><tbody>${data.rows.map((r,i)=>`<tr><td><input type="checkbox" checked name="row" value="${i}"></td><td class="name">${esc(r.name)}</td><td>${esc(r.sku)}</td><td>${esc(label(r.unit))}</td><td>${fmt(r.price)}</td><td>${r.image?(r.image.startsWith('data:')||r.image.startsWith('/assets/')?t('Локально'):t('Ссылка')):'—'}</td></tr>`).join('')}</tbody></table></div><label class="checkbox"><input type="checkbox" required>${t('Подтверждаю выбор товаров и источник данных')}</label><progress hidden id="catalog-import-progress" value="0" max="1" style="width:100%"></progress><p id="catalog-import-status" role="status" style="margin-top:12px"></p>${foot(t('Подтвердить выбранные'))}`,async f=>{
  if(!jobId)chosen=f.getAll('row').map(Number);
  if(!chosen.length)throw Error(t('Выберите товары'));
  const mode=$('#catalog-import-mode').value;
  if(mode==='replace'&&data.errors.length)throw Error(t('Для замены исправьте ошибки во всех файлах.'));
  const dialog=$('#modal'),prevent=e=>e.preventDefault(),unload=e=>{e.preventDefault();e.returnValue=''};
  dialog.addEventListener('cancel',prevent);window.addEventListener('beforeunload',unload);
  const controls=[...dialog.querySelectorAll('input,select,button')];controls.forEach(el=>el.disabled=true);
  const progress=$('#catalog-import-progress'),status=$('#catalog-import-status');progress.hidden=false;progress.max=chosen.length;
  try{
   if(!jobId)jobId=(await api('catalog/import-start',{supplier,office:selectedOffice,mode})).job_id;
   const pending=chosen.filter(i=>!saved.has(i));const indices=new Map(pending.map(i=>[data.rows[i],i]));
   const batches=importBatches(pending.map(i=>data.rows[i]),supplier,jobId);
   for(const batch of batches){status.textContent=`${t('Импорт товаров')}: ${saved.size} / ${chosen.length}`;await api('catalog/import',{supplier,job_id:jobId,rows:batch});batch.forEach(row=>saved.add(indices.get(row)));progress.value=saved.size}
   status.textContent=t('Применяем изменения каталога…');
   const result=await api('catalog/import-finish',{job_id:jobId,expected_count:chosen.length});
   catalogShowArchived=false;
   notify(`${t('Импорт завершён')}: ${result.count}. ${t('Новых карточек')}: ${result.created}. ${t('В архиве')}: ${result.archived}.`);
  }catch(e){status.textContent=`${t('Уже сохранено')}: ${saved.size} / ${chosen.length}. ${t('Повторите подтверждение, чтобы продолжить.')} ${t(e.message)}`;throw e}
  finally{
   dialog.removeEventListener('cancel',prevent);window.removeEventListener('beforeunload',unload);
   dialog.querySelector('.close').disabled=false;$('[data-cancel]').disabled=false;
   if(!jobId)controls.forEach(el=>el.disabled=false);
  }
 });
 cancel();const mode=$('#catalog-import-mode');mode.value=initialMode;
 const update=()=>{$('#catalog-replace-warning').hidden=mode.value!=='replace';$('#catalog-replace-errors').hidden=!(mode.value==='replace'&&data.errors.length);$('#modal-form button[type="submit"],#modal-form .modal-foot button:last-child').disabled=!data.rows.length||(mode.value==='replace'&&data.errors.length>0)};
 mode.onchange=update;update();$('#select-all').onchange=e=>$$('[name="row"]').forEach(c=>c.checked=e.target.checked);
}
function selectCatalogue(item){
 const existing=products().filter(p=>p.supplier===item.supplier);
 modal(t('Добавить в офис'),`<h3>${esc(item.name)}</h3><p class="muted">${esc(item.supplier)} · ${esc(item.sku)}</p><div class="notice info" style="margin-top:15px">${t('Привязка сохраняет нормы, остатки и историю. Название, артикул, фото и ссылка обновятся из справочника.')}</div><div class="notice">${t('Связывайте только тот же товар и ту же единицу учёта. Строку с несколькими вкусами или упаковками нельзя привязать к одному SKU без разделения.')}</div><label class="field"><span>${t('Выберите существующий товар')}</span><select name="product_id"><option value="">${t('Новый товар без нормы')}</option>${options(existing)}</select></label>${foot()}`,async f=>{const product_id=f.get('product_id')?Number(f.get('product_id')):null;await api('catalog/select',{catalog_id:item.id,office:selectedOffice,product_id});notify(t(product_id?'Товар связан, история сохранена':'Товар добавлен в офис'))});cancel();
}
async function exporterModal(){
 try{const r=await fetch('/supplier-exporter.js');if(!r.ok)throw Error(t('Ошибка запроса'));const code=await r.text();modal(t('Выгрузить из магазина'),`<p class="help-text">${t('Добавьте эту ссылку в закладки и нажмите её на странице магазина. Выгрузятся товары, доступные в разметке текущей страницы; другие страницы выгружаются отдельно. Пароли и cookies не передаются.')}</p><p style="margin:20px 0"><a id="export-bookmark" class="btn primary">${t('Экспортировать товары')}</a></p><p class="help-text">${t('Это справочник, а не полная синхронизация магазина. Цены и наличие относятся к моменту выгрузки.')}</p><details><summary>JavaScript</summary><textarea readonly id="export-code" style="width:100%;height:130px"></textarea></details><button class="btn" id="copy-export" type="button">${t('Скопировать код')}</button>`);$('#export-code').value=code;$('#export-bookmark').href='javascript:'+encodeURIComponent(code);$('#export-bookmark').onclick=e=>{e.preventDefault();notify(t('Добавьте эту ссылку в закладки и нажмите её на странице магазина. Выгрузятся товары, доступные в разметке текущей страницы; другие страницы выгружаются отдельно. Пароли и cookies не передаются.'))};$('#copy-export').onclick=async()=>{try{await navigator.clipboard.writeText(code);notify(t('Код скопирован'))}catch{$('#export-code').focus();$('#export-code').select()}};
 }catch(e){notify(e.message,true)}
}
