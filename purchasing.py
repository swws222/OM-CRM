"""Office assortment policy is independent of observed stock and bookmarks."""
import json
POLICIES=('regular','trial','catalog')

def normalize(p):
    if p.get('purchase_policy') not in POLICIES:p['purchase_policy']='regular' if p.get('in_pantry') else 'catalog'
    p['trial_received']=bool(p.get('trial_received',False)) if p['purchase_policy']=='trial' else False
    p['in_pantry']=p['purchase_policy']=='regular' or (p['purchase_policy']=='trial' and p['trial_received'])
    return p

def change_policy(p,policy):
    if policy not in POLICIES:raise ValueError('Неизвестный статус закупки')
    was_in_pantry=bool(p.get('in_pantry'));received=bool(p.get('trial_received'))
    p['purchase_policy']=policy;p['trial_received']=(received or was_in_pantry) if policy=='trial' else False
    return normalize(p)

def receive(p):
    normalize(p)
    if p['purchase_policy']=='catalog':p['purchase_policy']='trial'
    if p['purchase_policy']=='trial':p['trial_received']=True
    return normalize(p)

def product(c,pid):
    row=c.execute('SELECT data FROM products WHERE id=?',(int(pid),)).fetchone()
    if not row:raise ValueError('Товар не найден')
    return normalize(json.loads(row[0]))

def save(c,pid,p):c.execute('UPDATE products SET data=? WHERE id=?',(json.dumps(p,ensure_ascii=False),pid))

def policy_action(c,b,stamp,log):
    c.execute('BEGIN IMMEDIATE')
    pid=int(b['product_id']);p=product(c,pid);before=p.copy();change_policy(p,b['policy'])
    p.update(policy_reason=str(b.get('reason','')).strip()[:2000],policy_changed_at=stamp)
    save(c,pid,p);log(c,'purchase-policy','product',pid,before,p)
    return {'product_id':pid,**{k:p[k] for k in ('purchase_policy','in_pantry','trial_received','policy_reason','policy_changed_at')}}

def propose(c,b,stamp,log):
    c.execute('BEGIN IMMEDIATE');pid=int(b['product_id']);p=product(c,pid)
    if p.get('archived') or not p.get('active',True):raise ValueError('Товар недоступен для заказа')
    if p['purchase_policy']!='catalog':raise ValueError('Товар уже закупается регулярно или на пробу')
    old=c.execute("SELECT id FROM trial_proposals WHERE product_id=? AND status='pending'",(pid,)).fetchone()
    if old:return {'id':old[0],'status':'pending'}
    note=str(b.get('note','')).strip()[:2000]
    id=c.execute("INSERT INTO trial_proposals(product_id,office,status,note,created_at) VALUES(?,?,'pending',?,?)",(pid,p['office'],note,stamp)).lastrowid
    log(c,'propose-trial','product',pid,None,{'proposal_id':id,'note':note})
    return {'id':id,'status':'pending'}

def decide(c,b,stamp,log):
    c.execute('BEGIN IMMEDIATE');id=int(b['id']);row=c.execute('SELECT * FROM trial_proposals WHERE id=?',(id,)).fetchone()
    if not row:raise ValueError('Предложение не найдено')
    decision=b.get('decision')
    if decision not in ('approve','reject'):raise ValueError('Неизвестное решение')
    status='approved' if decision=='approve' else 'rejected'
    if row['status']==status:return {'id':id,'status':status,'order_id':row['order_id']}
    if row['status']!='pending':raise ValueError('Предложение уже рассмотрено')
    p=product(c,row['product_id']);order_id=None
    if decision=='approve':
        if p.get('archived') or not p.get('active',True):raise ValueError('Товар недоступен для заказа')
        import math
        try:qty=float(b['qty'])
        except (TypeError,ValueError,KeyError):raise ValueError('Укажите количество для пробной закупки')
        if not math.isfinite(qty) or not 0<qty<=1e9:raise ValueError('Укажите количество для пробной закупки')
        line={k:p.get(k) for k in ('name','supplier','unit','price','url')};line.update(product_id=row['product_id'],qty=qty)
        order={'office':p['office'],'visits':0,'buffer':0,'lines':[line],'source':'trial_proposal','proposal_id':id}
        order_id=c.execute('INSERT INTO orders(created_at,data) VALUES(?,?)',(stamp,json.dumps(order,ensure_ascii=False))).lastrowid
        # Approval is an ordering decision, never confirmation that goods arrived.
        if p['purchase_policy']=='catalog':p.update(purchase_policy='trial',trial_received=False)
        normalize(p);save(c,row['product_id'],p);log(c,'create','order',order_id,None,order)
    c.execute('UPDATE trial_proposals SET status=?,decided_at=?,order_id=?,decision_note=? WHERE id=?',(status,stamp,order_id,str(b.get('note',''))[:2000],id))
    log(c,'decide-trial','trial_proposal',id,{'status':'pending'},{'status':status,'order_id':order_id})
    return {'id':id,'status':status,'order_id':order_id}
