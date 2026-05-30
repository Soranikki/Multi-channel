SEED_CONFIGS: dict[str, dict] = {
    "shopee": {
        "platform": "shopee",
        "field_mappings": {
            "external_order_id": "order_sn",
            "platform_order_status": "order_status",
            "platform_payment_status": "payment_status",
            "customer_name": "recipient_address.name",
            "customer_phone": "recipient_address.phone",
            "customer_email": "buyer_email",
            "shipping_address": "recipient_address.full_address",
            "order_date": "create_time",
            "total_amount": "total_amount",
            "currency": "currency",
        },
        "items_root": "items",
        "item_mappings": {
            "external_sku": "item_sku",
            "product_name": "item_name",
            "quantity": "quantity_purchased",
            "unit_price": "item_price",
        },
        "inventory_endpoint": {
            "method": "PUT",
            "url": "http://mock-shopee-api:8011/api/v1/products/{sku}/inventory",
            "body_template": {"qty": "{qty}"},
        }
    },
    "tiktok": {
        "platform": "tiktok",
        "field_mappings": {
            "external_order_id": "id",
            "platform_order_status": "order_status",
            "platform_payment_status": "payment_status",
            "customer_name": "buyer.name",
            "customer_phone": "buyer.phone",
            "customer_email": "buyer.email",
            "shipping_address": "shipping_address",
            "order_date": "created_at",
            "total_amount": "payment.total",
            "currency": "payment.currency",
        },
        "items_root": "line_items",
        "item_mappings": {
            "external_sku": "seller_sku",
            "product_name": "title",
            "quantity": "qty",
            "unit_price": "sale_price",
        },
        "inventory_endpoint": {
            "method": "PUT",
            "url": "http://mock-tiktok-api:8012/api/v1/products/{sku}/inventory",
            "body_template": {"qty": "{qty}"},
        }
    },
}
