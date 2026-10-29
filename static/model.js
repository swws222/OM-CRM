export function recommend(product, visits, buffer) {
  const stock=product.estimated_stock;
  if(product.rate===null || stock===null) return {qty:null,need:null,target:null,stock,warning:product.rate===null?'Не задана норма':'Нет оценки остатка'};
  const need=product.rate*visits;
  let target=need*(1+buffer);
  if(product.max_stock!=null) target=Math.min(target,product.max_stock);
  const qty=Math.ceil(Math.max(0,target-stock)/product.step-1e-10)*product.step;
  return {qty:Math.max(0,Math.round(qty*1000)/1000),need,target,stock,warning:product.max_stock!=null&&stock+qty>product.max_stock?'Упаковка превышает лимит запаса':null};
}
