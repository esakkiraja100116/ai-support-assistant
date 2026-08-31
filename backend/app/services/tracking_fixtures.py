"""Deterministic mock data for the internal tracking API
(app/routers/internal_tracking.py), matching the documented contract shape
exactly. Fixed event_time values (not datetime.now()-relative) so every test
and demo run against these is fully reproducible.
"""

TRACKING_FIXTURES: dict[str, dict] = {
    "PRO19460771": {
        "success": True,
        "message": "Transaction details retrieved successfully",
        "error": "",
        "data": {
            "user_id": 43,
            "txn_id": "j54Po7qTYi",
            "total_price": 850.0,
            "product_name": "Gold Bar",
            "gold_quantity_purchased": 5.0,
            "txn_status": "DELIVERED",
            "awb_number": "PRO19460771",
            "product_type": "bar",
            "karat": "24",
            "created_at": "2026-07-08T08:35:34.642305+00:00",
            "metal_type": "gold",
            "tracking": {
                "pod_no": "PRO19460771",
                "history": [
                    {
                        "type": "InTransit",
                        "remarks": "Despatched to Mysore",
                        "area": "Chennai",
                        "event_time": "2026-07-23T16:37:00+00:00",
                    },
                    {
                        "type": "InTransit",
                        "remarks": "Despatched to Mysore",
                        "area": "Bengaluru - South",
                        "event_time": "2026-07-24T14:37:00+00:00",
                    },
                    {
                        "type": "Attempted",
                        "remarks": "Out for Delivery",
                        "area": "Udayagiri",
                        "event_time": "2026-07-25T05:20:00+00:00",
                    },
                    {
                        "type": "Attempted",
                        "remarks": "Holding on Request",
                        "area": "Udayagiri",
                        "event_time": "2026-07-25T12:20:34+00:00",
                    },
                    {
                        "type": "Attempted",
                        "remarks": "Out for Delivery",
                        "area": "Udayagiri",
                        "event_time": "2026-07-27T07:03:00+00:00",
                    },
                    {
                        "type": "Delivered",
                        "remarks": "Delivered",
                        "area": "Udayagiri",
                        "event_time": "2026-07-27T11:37:56+00:00",
                    },
                ],
            },
        },
    },
    "PRO19460772": {
        "success": True,
        "message": "Transaction details retrieved successfully",
        "error": "",
        "data": {
            "user_id": 43,
            "txn_id": "rTx2n8LmQe",
            "total_price": 340.0,
            "product_name": "Gold Coin",
            "gold_quantity_purchased": 2.0,
            "txn_status": "IN_TRANSIT",
            "awb_number": "PRO19460772",
            "product_type": "coin",
            "karat": "24",
            "created_at": "2026-08-27T09:10:00+00:00",
            "metal_type": "gold",
            "tracking": {
                "pod_no": "PRO19460772",
                "history": [
                    {
                        "type": "InTransit",
                        "remarks": "Despatched from Chennai",
                        "area": "Chennai",
                        "event_time": "2026-08-28T10:15:00+00:00",
                    },
                    {
                        "type": "InTransit",
                        "remarks": "Arrived at hub",
                        "area": "Bengaluru - South",
                        "event_time": "2026-08-29T08:07:00+00:00",
                    },
                ],
            },
        },
    },
    "PRO19460773": {
        "success": True,
        "message": "Transaction details retrieved successfully",
        "error": "",
        "data": {
            "user_id": 43,
            "txn_id": "kP9wZ3vBdA",
            "total_price": 170.0,
            "product_name": "Gold Bar",
            "gold_quantity_purchased": 1.0,
            "txn_status": "OUT_FOR_DELIVERY",
            "awb_number": "PRO19460773",
            "product_type": "bar",
            "karat": "24",
            "created_at": "2026-08-26T11:00:00+00:00",
            "metal_type": "gold",
            "tracking": {
                "pod_no": "PRO19460773",
                "history": [
                    {
                        "type": "InTransit",
                        "remarks": "Arrived at local facility",
                        "area": "New Delhi",
                        "event_time": "2026-08-29T06:40:00+00:00",
                    },
                    {
                        "type": "Attempted",
                        "remarks": "Out for Delivery",
                        "area": "New Delhi",
                        "event_time": "2026-08-29T09:05:00+00:00",
                    },
                ],
            },
        },
    },
    "PRO19460774": {
        "success": True,
        "message": "Transaction details retrieved successfully",
        "error": "",
        "data": {
            "user_id": 43,
            "txn_id": "mN4qX7cRfG",
            "total_price": 510.0,
            "product_name": "Gold Coin",
            "gold_quantity_purchased": 3.0,
            "txn_status": "ATTEMPTED",
            "awb_number": "PRO19460774",
            "product_type": "coin",
            "karat": "24",
            "created_at": "2026-08-24T13:20:00+00:00",
            "metal_type": "gold",
            "tracking": {
                "pod_no": "PRO19460774",
                "history": [
                    {
                        "type": "InTransit",
                        "remarks": "Arrived at local facility",
                        "area": "Pune",
                        "event_time": "2026-08-27T07:30:00+00:00",
                    },
                    {
                        "type": "Attempted",
                        "remarks": "Customer unavailable",
                        "area": "Pune",
                        "event_time": "2026-08-27T15:50:00+00:00",
                    },
                ],
            },
        },
    },
}
