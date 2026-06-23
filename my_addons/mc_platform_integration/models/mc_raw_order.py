# -*- coding: utf-8 -*-
import json
from datetime import datetime, timezone

from odoo import api, fields, models


class McRawOrder(models.Model):
    _inherit = 'mc.raw.order'

    CANONICAL_ORDER_STATUS = [
        ('unknown', 'Không rõ'),
        ('pending', 'Chờ xử lý'),
        ('confirmed', 'Đã xác nhận'),
        ('shipping', 'Đang giao'),
        ('delivered', 'Đã giao'),
        ('cancelled', 'Đã hủy'),
        ('refunded', 'Đã hoàn tiền'),
    ]
    CANONICAL_PAYMENT_STATUS = [
        ('unknown', 'Không rõ'),
        ('pending', 'Chờ xử lý'),
        ('paid', 'Đã thanh toán'),
        ('failed', 'Thất bại'),
        ('refunded', 'Đã hoàn tiền'),
    ]

    integration_event_id = fields.Char(string="Mã sự kiện tích hợp", readonly=True, copy=False, index=True)
    normalized_at = fields.Datetime(string="Thời gian chuẩn hóa", readonly=True, copy=False)
    platform_order_status = fields.Char(string="Trạng thái đơn hàng (Sàn)", readonly=True, copy=False)
    platform_payment_status = fields.Char(string="Trạng thái thanh toán (Sàn)", readonly=True, copy=False)
    platform_status_updated_at = fields.Datetime(string="Thời gian cập nhật trạng thái (Sàn)", readonly=True, copy=False, index=True)
    canonical_order_status = fields.Selection(selection=CANONICAL_ORDER_STATUS, string="Trạng thái Đơn hàng", default='unknown', readonly=True, copy=False, index=True)
    canonical_payment_status = fields.Selection(selection=CANONICAL_PAYMENT_STATUS, string="Trạng thái Thanh toán", default='unknown', readonly=True, copy=False, index=True)
    mapping_status = fields.Selection(
        selection=[
            ('unchecked', 'Chưa kiểm tra'),
            ('mapped', 'Đã map'),
            ('partial', 'Map một phần'),
            ('unmapped', 'Chưa map'),
        ],
        string="Trạng thái Map SKU",
        default='unchecked',
        readonly=True,
        copy=False,
        index=True,
    )
    mapped_product_count = fields.Integer(string="Số SP đã map", readonly=True, copy=False)
    unmapped_skus = fields.Text(string="Các SKU chưa map", readonly=True, copy=False)
    reconcile_state = fields.Selection(
        selection=[
            ('unchecked', 'Chưa kiểm tra'),
            ('matched', 'Khớp'),
            ('mismatched', 'Lệch'),
            ('skipped', 'Bỏ qua'),
        ],
        string="Trạng thái Đối soát",
        default='unchecked',
        readonly=True,
        copy=False,
        index=True,
    )
    reconcile_message = fields.Text(string="Thông báo đối soát", readonly=True, copy=False)
    reconciled_at = fields.Datetime(string="Thời gian đối soát", readonly=True, copy=False)

    @api.model
    def _prepare_integration_vals_from_payload(self, payload: dict, integration_event_id=False, normalized_at=False) -> dict:
        platform_order_status = str(payload.get('platform_order_status') or '').strip()
        platform_payment_status = str(payload.get('platform_payment_status') or '').strip()
        status_dt = self._parse_external_datetime(payload.get('platform_status_updated_at'))
        vals = {
            'integration_event_id': integration_event_id or False,
            'normalized_at': normalized_at or fields.Datetime.now(),
        }
        has_order_status = bool(platform_order_status)
        has_payment_status = bool(platform_payment_status)
        if platform_order_status:
            vals['platform_order_status'] = platform_order_status
        if platform_payment_status:
            vals['platform_payment_status'] = platform_payment_status
        if status_dt:
            vals['platform_status_updated_at'] = status_dt
        if has_order_status or has_payment_status:
            vals['canonical_order_status'] = self._map_canonical_order_status(platform_order_status, platform_payment_status)
            vals['canonical_payment_status'] = self._map_canonical_payment_status(platform_payment_status)
        return vals

    def _apply_integration_payload(self, payload: dict, integration_event_id=False, normalized_at=False) -> dict:
        self.ensure_one()
        incoming_vals = self._prepare_integration_vals_from_payload(
            payload,
            integration_event_id=integration_event_id,
            normalized_at=normalized_at,
        )
        incoming_status_dt = self._coerce_datetime_string(incoming_vals.get('platform_status_updated_at'))
        current_status_dt = self._coerce_datetime_string(self.platform_status_updated_at)
        if current_status_dt and incoming_status_dt and incoming_status_dt < current_status_dt:
            self.env['mc.sync.log']._log(
                'warning',
                f'Ignored stale event {integration_event_id} for {self.external_order_id}.',
                channel_id=self.channel_id.id,
                reference=self.external_order_id,
            )
            return {'stale': True}

        self.write({
            'raw_payload': json.dumps(payload, ensure_ascii=False),
            **incoming_vals,
        })
        return {'stale': False}

    def _reconcile_with_sale_order(self) -> dict:
        self.ensure_one()
        now = fields.Datetime.now()
        if not self.sale_order_id:
            message = 'No linked sales order to reconcile.'
            self.write({
                'reconcile_state': 'skipped',
                'reconcile_message': message,
                'reconciled_at': now,
            })
            return {'state': 'skipped', 'message': message}

        desired_order = self.canonical_order_status or 'unknown'
        desired_payment = self.canonical_payment_status or 'unknown'
        self.sale_order_id._mc_apply_channel_statuses(
            desired_order,
            desired_payment,
            self.platform_status_updated_at,
        )

        actual_order = self.sale_order_id._mc_get_canonical_order_status()
        actual_payment = self.sale_order_id._mc_get_canonical_payment_status()

        order_match = self._is_order_reconcile_match(desired_order, actual_order)
        payment_match = desired_payment in ('unknown', False) or desired_payment == actual_payment
        soft_payment_match = False
        if not payment_match:
            soft_payment_match = self._is_soft_payment_match(
                desired_payment,
                actual_payment,
                self.sale_order_id,
            )
            payment_match = soft_payment_match

        mismatch_parts = []
        if not order_match:
            mismatch_parts.append(f'order expected={desired_order} actual={actual_order}')
        if not payment_match:
            mismatch_parts.append(f'payment expected={desired_payment} actual={actual_payment}')

        if mismatch_parts:
            state = 'mismatched'
            message = '; '.join(mismatch_parts)
            self.env['mc.sync.log']._log(
                'warning',
                f'Reconcile mismatch for {self.external_order_id}: {message}',
                channel_id=self.channel_id.id,
                reference=self.external_order_id,
            )
        else:
            state = 'matched'
            if soft_payment_match:
                message = 'Order reconciled; payment temporarily accepted while Odoo invoices are not finalized.'
            else:
                message = 'Order and payment status reconciled successfully.'

        self.write({
            'reconcile_state': state,
            'reconcile_message': message,
            'reconciled_at': now,
        })
        return {'state': state, 'message': message}

    def _check_product_mapping(self) -> dict:
        self.ensure_one()
        if self.state not in ('parsed', 'processed') or not self.parsed_items_json:
            self.write({
                'mapping_status': 'unchecked',
                'mapped_product_count': 0,
                'unmapped_skus': False,
            })
            return {'status': 'unchecked', 'mapped_count': 0, 'unmapped_skus': []}

        items = json.loads(self.parsed_items_json or '[]')
        skus = sorted({str(item.get('external_sku') or '').strip() for item in items if item.get('external_sku')})
        if not skus:
            self.write({
                'mapping_status': 'unmapped',
                'mapped_product_count': 0,
                'unmapped_skus': False,
            })
            return {'status': 'unmapped', 'mapped_count': 0, 'unmapped_skus': []}

        mappings = self.env['mc.product.mapping'].search([
            ('channel_id', '=', self.channel_id.id),
            ('external_sku', 'in', skus),
            ('is_active', '=', True),
        ])
        mapped_skus = set(mappings.mapped('external_sku'))
        unmapped = [sku for sku in skus if sku not in mapped_skus]
        if not unmapped:
            status = 'mapped'
        elif mapped_skus:
            status = 'partial'
        else:
            status = 'unmapped'

        self.write({
            'mapping_status': status,
            'mapped_product_count': len(mapped_skus),
            'unmapped_skus': '\n'.join(unmapped) if unmapped else False,
        })
        return {'status': status, 'mapped_count': len(mapped_skus), 'unmapped_skus': unmapped}

    @staticmethod
    def _parse_external_datetime(raw):
        if not raw:
            return False
        try:
            value = str(raw).strip().replace('Z', '+00:00')
            dt_value = datetime.fromisoformat(value)
            if dt_value.tzinfo:
                dt_value = dt_value.astimezone(timezone.utc).replace(tzinfo=None)
            return dt_value
        except Exception:
            return False

    @staticmethod
    def _coerce_datetime_string(raw):
        if not raw:
            return False
        if isinstance(raw, datetime):
            return fields.Datetime.to_string(raw)
        if isinstance(raw, str):
            try:
                return fields.Datetime.to_string(fields.Datetime.from_string(raw))
            except Exception:
                return False
        try:
            return fields.Datetime.to_string(fields.Datetime.to_datetime(raw))
        except Exception:
            return False

    @staticmethod
    def _normalize_status_token(raw: str) -> str:
        return str(raw or '').strip().upper().replace('-', '_').replace(' ', '_')

    @classmethod
    def _map_canonical_order_status(cls, order_status: str, payment_status: str) -> str:
        token = cls._normalize_status_token(order_status)
        pay_token = cls._normalize_status_token(payment_status)
        if 'REFUND' in token or 'REFUND' in pay_token:
            return 'refunded'
        if any(key in token for key in ('CANCEL', 'FAILED', 'VOID')):
            return 'cancelled'
        if any(key in token for key in ('DELIVERED', 'COMPLETED', 'FINISHED')):
            return 'delivered'
        if any(key in token for key in ('SHIPPING', 'SHIPPED', 'IN_TRANSIT', 'READY_TO_SHIP', 'AWAITING_SHIPMENT')):
            return 'shipping'
        if any(key in token for key in ('PAID', 'CONFIRM', 'PROCESSING', 'PICKING', 'PACKED')) or pay_token in ('PAID', 'CAPTURED', 'SUCCESS', 'SETTLED'):
            return 'confirmed'
        if token:
            return 'pending'
        return 'unknown'

    @classmethod
    def _map_canonical_payment_status(cls, payment_status: str) -> str:
        token = cls._normalize_status_token(payment_status)
        if 'REFUND' in token:
            return 'refunded'
        if any(key in token for key in ('PAID', 'CAPTURED', 'SUCCESS', 'SETTLED')):
            return 'paid'
        if any(key in token for key in ('FAILED', 'CANCEL', 'VOID', 'DECLINED', 'UNPAID')):
            return 'failed'
        if any(key in token for key in ('PENDING', 'PROCESSING', 'AUTH')):
            return 'pending'
        if token:
            return 'pending'
        return 'unknown'

    @staticmethod
    def _is_order_reconcile_match(expected: str, actual: str) -> bool:
        if expected in ('unknown', False):
            return True
        if expected == 'refunded' and actual == 'cancelled':
            return True
        if expected == 'shipping' and actual in ('confirmed', 'shipping'):
            return True
        if expected == 'delivered' and actual in ('confirmed', 'shipping', 'delivered'):
            return True
        return expected == actual

    @staticmethod
    def _is_soft_payment_match(expected: str, actual: str, sale_order) -> bool:
        if expected in ('unknown', False):
            return True
        if actual != 'pending':
            return False
        if expected not in ('paid', 'failed', 'refunded'):
            return False

        posted_invoices = sale_order.invoice_ids.filtered(lambda inv: inv.state == 'posted')
        return not posted_invoices
