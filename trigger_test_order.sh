#!/bin/bash
echo "Triggering new test order for Shopee..."

TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

PAYLOAD='{
  "event_id": "shopee-SHOPEE-TEST-999",
  "event_type": "order.created",
  "payload": {
    "order_sn": "SHOPEE-TEST-999",
    "buyer_username": "test_e2e_user",
    "buyer_email": "e2e@example.test",
    "recipient_address": {
      "name": "E2E Tester",
      "phone": "0999999999",
      "full_address": "E2E Street"
    },
    "create_time": "'$TIMESTAMP'",
    "order_status": "READY_TO_SHIP",
    "payment_status": "PAID",
    "currency": "VND",
    "total_amount": 885000,
    "items": [
      {
        "item_sku": "FURN-0789",
        "item_name": "Bàn làm việc cá nhân",
        "quantity_purchased": 2,
        "item_price": 442500
      }
    ]
  }
}'

# Sign payload (secret is dev-webhook-secret)
SECRET="dev-webhook-secret"
SIGNATURE=$(echo -n "${TIMESTAMP}.${PAYLOAD}" | openssl dgst -sha256 -hmac "$SECRET" | awk '{print "sha256=" $2}')

curl -X POST http://localhost:8020/webhook/shopee \
  -H "Content-Type: application/json" \
  -H "X-MC-Timestamp: $TIMESTAMP" \
  -H "X-MC-Signature: $SIGNATURE" \
  -d "$PAYLOAD"

echo ""
