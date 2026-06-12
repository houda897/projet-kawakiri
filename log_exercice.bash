--- *** --- join_inference --- *** ---

2026-06-12 09:38:11,304 - inference.join_candidate - INFO - [PREFILTER] 28 columns -> 8 kept (20 removed)
Nombre de boucles : 47 | temps écoulé : 0:00:01.134750
--- *** --- taille candidates : 23 --- *** ---

2026-06-12 09:38:12,578 - inference.join_candidate - INFO - sales.date_id -> calendar.date_id | ratio=1.0
2026-06-12 09:38:12,579 - inference.join_candidate - INFO - calendar.month -> customers.customer_id | ratio=1.0
2026-06-12 09:38:12,579 - inference.join_candidate - INFO - sales.customer_id -> customers.customer_id | ratio=1.0
2026-06-12 09:38:12,579 - inference.join_candidate - INFO - sales.product_id -> customers.customer_id | ratio=1.0
2026-06-12 09:38:12,579 - inference.join_candidate - INFO - sales.quantity -> customers.customer_id | ratio=1.0
2026-06-12 09:38:12,579 - inference.join_candidate - INFO - sales.sale_id -> customers.customer_id | ratio=1.0
2026-06-12 09:38:12,579 - inference.join_candidate - INFO - shipments.customer_id -> customers.customer_id | ratio=1.0
2026-06-12 09:38:12,579 - inference.join_candidate - INFO - shipments.sale_id -> customers.customer_id | ratio=1.0
2026-06-12 09:38:12,579 - inference.join_candidate - INFO - calendar.month -> products.product_id | ratio=1.0
2026-06-12 09:38:12,579 - inference.join_candidate - INFO - sales.customer_id -> products.product_id | ratio=1.0
2026-06-12 09:38:12,579 - inference.join_candidate - INFO - sales.product_id -> products.product_id | ratio=1.0
2026-06-12 09:38:12,579 - inference.join_candidate - INFO - sales.quantity -> products.product_id | ratio=1.0
2026-06-12 09:38:12,579 - inference.join_candidate - INFO - sales.sale_id -> products.product_id | ratio=1.0
2026-06-12 09:38:12,579 - inference.join_candidate - INFO - shipments.customer_id -> products.product_id | ratio=1.0
2026-06-12 09:38:12,579 - inference.join_candidate - INFO - shipments.sale_id -> products.product_id | ratio=1.0
2026-06-12 09:38:12,580 - inference.join_candidate - INFO - calendar.month -> sales.sale_id | ratio=1.0
2026-06-12 09:38:12,580 - inference.join_candidate - INFO - shipments.customer_id -> sales.sale_id | ratio=1.0
2026-06-12 09:38:12,580 - inference.join_candidate - INFO - shipments.sale_id -> sales.sale_id | ratio=1.0
2026-06-12 09:38:12,580 - inference.join_candidate - INFO - calendar.month -> shipments.sale_id | ratio=1.0
2026-06-12 09:38:12,580 - inference.join_candidate - INFO - sales.customer_id -> shipments.sale_id | ratio=1.0
2026-06-12 09:38:12,580 - inference.join_candidate - INFO - sales.product_id -> shipments.sale_id | ratio=1.0
2026-06-12 09:38:12,580 - inference.join_candidate - INFO - sales.quantity -> shipments.sale_id | ratio=1.0
2026-06-12 09:38:12,580 - inference.join_candidate - INFO - sales.sale_id -> shipments.sale_id | ratio=1.0