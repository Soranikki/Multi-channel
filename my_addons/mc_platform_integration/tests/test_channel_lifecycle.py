from datetime import datetime, timezone

from odoo.tests import TransactionCase, tagged


@tagged('-at_install', 'post_install')
class TestChannelLifecycle(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.shopee = cls.env['mc.channel'].search([('code', '=', 'shopee')], limit=1)
        cls.tiktok = cls.env['mc.channel'].search([('code', '=', 'tiktok')], limit=1)
        cls.manual = cls.env['mc.channel'].search([('code', '=', 'manual')], limit=1)

        if not cls.shopee or not cls.tiktok:
            raise ValueError('Seed channels (shopee, tiktok) not found. Install mc_core first.')

        cls.shopee.write({'active': True, 'integration_enabled': True})
        cls.tiktok.write({'active': True, 'integration_enabled': True})

    def _verify(self, ch, active, integ, sync):
        self.assertEqual(ch.active, active, f'{ch.code}: active={active}')
        self.assertEqual(ch.integration_enabled, integ, f'{ch.code}: integ={integ}')
        self.assertEqual(ch.sync_status, sync, f'{ch.code}: sync={sync}')
        print(f'  ✓ {ch.code}: active={ch.active} integ={ch.integration_enabled} sync={ch.sync_status}')

    def _shopee_payload(self, oid='SHOPEE-TEST-001'):
        return {
            'channel_code': 'shopee',
            'external_order_id': oid,
            'platform_order_status': 'READY_TO_SHIP',
            'platform_payment_status': 'PAID',
            'customer_name': 'Nguyen Van A',
            'customer_phone': '0901234567',
            'customer_email': 'test@test.com',
            'shipping_address': '123 Street',
            'order_date': '2026-05-05T09:00:00Z',
            'total_amount': 885000.0,
            'currency': 'VND',
            'items': [{
                'external_sku': 'FURN-0789',
                'product_name': 'Ban lam viec',
                'quantity': 1.0,
                'unit_price': 885000.0,
            }],
        }

    def _tiktok_payload(self, oid='TIKTOK-TEST-001'):
        return {
            'channel_code': 'tiktok',
            'external_order_id': oid,
            'platform_order_status': 'AWAITING_SHIPMENT',
            'platform_payment_status': 'PAID',
            'customer_name': 'Le Van C',
            'customer_phone': '0933333333',
            'customer_email': 'levanc@test.com',
            'shipping_address': '789 Street',
            'order_date': '2026-05-06T10:30:00Z',
            'total_amount': 750000.0,
            'currency': 'VND',
            'items': [{
                'external_sku': 'FURN-0789',
                'product_name': 'Ban lam viec',
                'quantity': 1.0,
                'unit_price': 750000.0,
            }],
        }

    # ── Tests ──────────────────────────────────────────────

    def test_01_archive_shopee(self):
        """Archive sets active=False, integ=False, sync=idle"""
        print('\n--- Archive Shopee ---')
        self.shopee.write({'active': False})
        self._verify(self.shopee, False, False, 'idle')

    def test_02_reactivate_shopee(self):
        """Reactivate sets active=True, integ=True, sync=success"""
        print('\n--- Reactivate Shopee ---')
        self.shopee.write({'active': False})
        self.shopee.write({'active': True})
        self._verify(self.shopee, True, True, 'success')

    def test_03_archive_tiktok(self):
        """Archive sets active=False, integ=False, sync=idle"""
        print('\n--- Archive TikTok ---')
        self.tiktok.write({'active': False})
        self._verify(self.tiktok, False, False, 'idle')

    def test_04_reactivate_tiktok(self):
        """Reactivate sets active=True, integ=True, sync=success"""
        print('\n--- Reactivate TikTok ---')
        self.tiktok.write({'active': False})
        self.tiktok.write({'active': True})
        self._verify(self.tiktok, True, True, 'success')

    def test_05_ingest_shopee(self):
        """Ingest Shopee after reactivate → pipeline OK"""
        print('\n--- Ingest Shopee ---')
        self.shopee.write({'active': True, 'integration_enabled': True})
        result = self.env['mc.channel'].ingest_normalized_order(self._shopee_payload())
        self.assertIn(result['status'], ('created', 'updated'))
        self.assertEqual(self.shopee.sync_status, 'success')
        print(f'  ✓ result={result["status"]} state={result.get("raw_order_state")}')

    def test_06_ingest_tiktok(self):
        """Ingest TikTok after reactivate → pipeline OK"""
        print('\n--- Ingest TikTok ---')
        self.tiktok.write({'active': True, 'integration_enabled': True})
        result = self.env['mc.channel'].ingest_normalized_order(self._tiktok_payload())
        self.assertIn(result['status'], ('created', 'updated'))
        self.assertEqual(self.tiktok.sync_status, 'success')
        print(f'  ✓ result={result["status"]} state={result.get("raw_order_state")}')

    def test_07_full_cycle(self):
        """Full archive/reactive cycle → both channels working"""
        print('\n--- Full cycle ---')
        for ch in (self.shopee, self.tiktok):
            ch.write({'active': False})
            self._verify(ch, False, False, 'idle')
        for ch in (self.shopee, self.tiktok):
            ch.write({'active': True})
            self._verify(ch, True, True, 'success')
        for code, mk in [('shopee', self._shopee_payload), ('tiktok', self._tiktok_payload)]:
            ch = self.env['mc.channel'].search([('code', '=', code)], limit=1)
            result = self.env['mc.channel'].ingest_normalized_order(mk(f'{code.upper()}-CYCLE-001'))
            self.assertIn(result['status'], ('created', 'updated'))
            self.assertEqual(ch.sync_status, 'success')
            print(f'  ✓ {code} ingest OK')
