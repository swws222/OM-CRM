import copy
import json
import unittest
import test_http
import server as s

class PurchasingTest(unittest.TestCase):
 setUp=test_http.HTTPTest.setUp
 tearDown=test_http.HTTPTest.tearDown
 request=test_http.HTTPTest.request
 def state(self):return self.request('/api/state')[1]
 def product(self,pid):return next(p for p in self.state()['products'] if p['id']==pid)
 def catalog_product(self):
  p=copy.deepcopy(self.product(1));p.pop('id');p.update(name='Test marmelada',purchase_policy='catalog',in_pantry=False)
  code,r=self.request('/api/product',p);self.assertEqual(code,200);return r['id']
 def policy(self,pid,policy,reason=''):
  code,r=self.request('/api/product-policy',dict(product_id=pid,policy=policy,reason=reason));self.assertEqual(code,200);return r
 def test_trial_lifecycle_requires_receipt_and_explicit_regular_choice(self):
  pid=self.catalog_product();before=len(self.state()['orders'])
  code,r=self.request('/api/proposals',dict(product_id=pid,note='Try this'));self.assertEqual(code,200);proposal=r['id']
  self.assertEqual(self.request('/api/proposals',dict(product_id=pid))[1]['id'],proposal)
  self.assertEqual(self.product(pid)['purchase_policy'],'catalog');self.assertFalse(self.product(pid)['in_pantry'])
  self.assertEqual(len(self.state()['orders']),before)
  self.assertEqual(self.request('/api/proposals/decide',dict(id=proposal,decision='approve',qty=0))[0],400)
  code,approved=self.request('/api/proposals/decide',dict(id=proposal,decision='approve',qty=2));self.assertEqual(code,200)
  self.assertEqual(self.request('/api/proposals/decide',dict(id=proposal,decision='approve',qty=2))[1],approved)
  self.assertEqual(len(self.state()['orders']),before+1)
  p=self.product(pid);self.assertEqual(p['purchase_policy'],'trial');self.assertFalse(p['in_pantry']);self.assertFalse(p['trial_received'])
  self.assertEqual(self.request('/api/delivery',dict(office='Белград',supplier='Maxi',number='TRIAL-1',date='2026-10-29',lines=[dict(product_id=pid,qty=2,price=100)]))[0],200)
  p=self.product(pid);self.assertTrue(p['in_pantry']);self.assertTrue(p['trial_received']);self.assertEqual(p['purchase_policy'],'trial')
  self.request('/api/observation',dict(product_id=pid,date='2026-10-30',kind='level',level=0))
  self.assertTrue(self.product(pid)['in_pantry']);self.assertEqual(self.product(pid)['purchase_policy'],'trial')
  self.policy(pid,'regular');self.assertTrue(self.product(pid)['in_pantry'])
  self.assertEqual(self.product(pid)['purchase_policy'],'regular')
 def test_regular_to_trial_preserves_stock_history_and_reason(self):
  self.request('/api/observation',dict(product_id=1,date='2026-10-30',kind='level',level=0))
  self.request('/api/product-flags',dict(product_id=1,favorite=True));before=self.product(1)
  self.policy(1,'trial','Quality changed');p=self.product(1)
  self.assertTrue(p['in_pantry']);self.assertTrue(p['trial_received']);self.assertEqual(p['policy_reason'],'Quality changed')
  for k in ('estimated_stock','observation','favorite','name','image','thresholds','rate'):self.assertEqual(p.get(k),before.get(k))
  s.init();self.assertEqual(self.product(1)['purchase_policy'],'trial')
  self.policy(1,'catalog');self.assertFalse(self.product(1)['in_pantry']);self.assertEqual(self.product(1)['observation'],before['observation'])
  _,backup=self.request('/api/backup');self.assertTrue(backup['tables']['audit']);self.assertIn('trial_proposals',backup['tables'])
 def test_editor_keeps_received_regular_product_in_pantry_on_trial_transition(self):
  p=self.product(1);p['purchase_policy']='trial';self.assertEqual(self.request('/api/product',p)[0],200)
  self.assertTrue(self.product(1)['trial_received']);self.assertTrue(self.product(1)['in_pantry'])
 def test_rejection_and_invalid_policy_never_change_stock(self):
  pid=self.catalog_product();_,r=self.request('/api/proposals',dict(product_id=pid))
  self.assertEqual(self.request('/api/proposals/decide',dict(id=r['id'],decision='reject'))[0],200)
  self.assertEqual(self.product(pid)['purchase_policy'],'catalog');self.assertFalse(self.product(pid)['in_pantry'])
  self.assertEqual(self.request('/api/proposals/decide',dict(id=r['id'],decision='approve',qty=1))[0],400)
  self.assertEqual(self.request('/api/product-policy',dict(product_id=pid,policy='invalid'))[0],400)
  self.assertFalse(self.product(pid)['in_pantry'])
 def test_backup_restores_trial_proposal_order_links(self):
  from pathlib import Path
  from scripts.restore_backup import restore
  pid=self.catalog_product();_,proposal=self.request('/api/proposals',dict(product_id=pid))
  self.request('/api/proposals/decide',dict(id=proposal['id'],decision='approve',qty=2))
  _,backup=self.request('/api/backup');path=Path(self.tmp.name)/'backup.json';path.write_text(json.dumps(backup))
  old=s.DATA
  try:
   restore(path,Path(self.tmp.name)/'restored-trial');s.init()
   with s.connect() as c:
    state=s.state(c);self.assertEqual(len(state['proposals']),1);self.assertEqual(state['proposals'][0]['order_id'],state['orders'][0]['id']);self.assertEqual(next(p for p in state['products'] if p['id']==pid)['purchase_policy'],'trial')
  finally:s.DATA=old
