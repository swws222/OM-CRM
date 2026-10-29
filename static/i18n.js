const languages=['ru','sr','en'];
let language=localStorage.getItem('pantry_language')||'ru';
if(!languages.includes(language))language='ru';
let dictionary={};
{
  const response=await fetch(`/locales/${language}.json`);
  if(!response.ok)throw new Error('Cannot load interface language');
  dictionary=await response.json();
}
export const getLanguage=()=>language;
export const locale=()=>({ru:'ru-RU',sr:'sr-Latn-RS',en:'en-GB'})[language];
export function setLanguage(value){if(languages.includes(value)){localStorage.setItem('pantry_language',value);location.reload();}}
export function t(value){
  if(value==null)return '';
  if(Object.hasOwn(dictionary,value))return dictionary[value];
  if(language==='ru')return value;
  const field=/^Заполните поле (.+)$/.exec(value);
  if(field)return language==='sr'?`Popunite polje ${field[1]}`:language==='en'?`Fill in ${field[1]}`:value;
  const missing=/^Не заполнена посещаемость за (\d+) будних дней$/.exec(value);
  if(missing)return language==='sr'?`Nedostaje posećenost za ${missing[1]} radnih dana`:`Attendance missing for ${missing[1]} weekdays`;
  if(value.startsWith('Точные остатки '))return t('Точные остатки')+' '+value.slice('Точные остатки '.length);
  const colon=value.indexOf(': ');
  if(colon>0)return t(value.slice(0,colon))+': '+t(value.slice(colon+2));
  return value;
}
export const label=t;
document.documentElement.lang=language==='sr'?'sr-Latn':language;
document.title=language==='ru'?'Office Pantry — офисные запасы':language==='sr'?'Office Pantry — kancelarijske zalihe':'Office Pantry — office stock';
