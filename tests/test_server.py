import base64
import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server as s

class PantryTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.previous=s.DATA;s.DATA=Path(self.tmp.name);s.init()
    def tearDown(self): s.DATA=self.previous;self.tmp.cleanup()
    def test_seed_is_idempotent_and_preserves_approximate_source(self):
        s.init()
        with s.connect() as c:
            st=s.state(c)
            self.assertEqual(len(st['products']),35)
            self.assertEqual(len(st['deliveries']),35)
            self.assertEqual(len(st['attendance']),55)
            self.assertTrue(all(o['kind']=='estimate' for o in st['observations']))
            p=st['products'][0]
            self.assertEqual(p['estimated_stock'],160)
            self.assertTrue(any(p['rate'] is None for p in st['products']))
    def test_delivery_updates_stock_once_and_edits_recompute(self):
        with s.connect() as c:
            d=dict(office='Белград',supplier='Maxi',number='test',date='2026-10-20',lines=[dict(product_id=1,qty=24,price=100)])
            id=s.save_delivery(c,d)
            self.assertEqual(s.state(c)['products'][0]['estimated_stock'],184)
            with self.assertRaises(ValueError): s.save_delivery(c,d)
            d['lines'][0]['qty']=12;s.save_delivery(c,d,id)
            self.assertEqual(s.state(c)['products'][0]['estimated_stock'],172)
            s.save_observation(c,dict(product_id=1,date='2026-10-21',kind='exact',qty=100))
            self.assertEqual(s.state(c)['products'][0]['estimated_stock'],100)
    def test_level_mapping_can_be_edited_and_is_not_exact(self):
        with s.connect() as c:
            s.save_observation(c,dict(product_id=1,date='2026-10-21',kind='level',level=1))
            p=s.state(c)['products'][0];p['thresholds']=[0,2,4,8,12,24];s.save_product(c,p,p['id'])
            self.assertEqual(s.state(c)['products'][0]['estimated_stock'],2)
            self.assertIn('error',s.calibration(s.state(c),1))
    def test_calibration_requires_complete_attendance_and_exact_anchors(self):
        with s.connect() as c:
            s.save_observation(c,dict(product_id=1,date='2026-10-20',kind='exact',qty=100))
            s.save_observation(c,dict(product_id=1,date='2026-10-22',kind='exact',qty=80))
            s.save_delivery(c,dict(office='Белград',supplier='Maxi',number='calibration',date='2026-10-21',lines=[dict(product_id=1,qty=20)]))
            self.assertIn('error',s.calibration(s.state(c),1))
            c.executemany('INSERT INTO attendance VALUES(?,?,?,?)',[('Белград','2026-10-21',10,''),('Белград','2026-10-22',10,'')])
            result=s.calibration(s.state(c),1)
            self.assertEqual(result['rate'],2)
            self.assertEqual(result['used'],40)
    def test_office_isolation(self):
        with s.connect() as c:
            with self.assertRaises(ValueError): s.save_delivery(c,dict(office='Нови-Сад',supplier='Maxi',number='x',date='2026-10-21',lines=[dict(product_id=1,qty=1)]))
    def test_invalid_numbers_and_thresholds_are_rejected(self):
        for n in ('NaN','inf',-1):
            with self.assertRaises(ValueError): s.num(n)
        with s.connect() as c:
            p=s.state(c)['products'][0];p['thresholds']=[0,3,2,5,6,7]
            with self.assertRaises(ValueError): s.save_product(c,p,1)
    def test_pdf_duplicate_and_type_validation(self):
        with s.connect() as c:
            d=dict(office='Белград',supplier='Maxi',number='pdf1',date='2026-10-21',lines=[dict(product_id=1,qty=1)],attachment={'base64':base64.b64encode(b'%PDF-1.7\ntest invoice').decode()})
            s.save_delivery(c,d);d['number']='pdf2'
            with self.assertRaisesRegex(ValueError,'PDF уже'): s.save_delivery(c,d)
            d['attachment']['base64']=base64.b64encode(b'not a pdf').decode()
            with self.assertRaisesRegex(ValueError,'PDF-файл'): s.save_delivery(c,d)

if __name__=='__main__': unittest.main()
