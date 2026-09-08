# Analyst report — barnboard

_2 question(s) over the governed semantic layer._

## What is the avg daily yield per cow?

**Metric:** `avg_daily_yield_per_cow` (derived, data-designer, v1) — Average litres one cow gives in one day (AM+PM). Computed as total litres divided by cow-days at the cow-day grain — never by summing per-cow averages.

**Answer:** 23.18 L/cow/day

<sub>receipt · lineage ['gold.agg_milk_cow_daily', 'silver.milk_logs', 'silver.cows'] · `SELECT sum("litres")*1.0/nullif(count(*),0) AS "avg_daily_yield_per_cow" FROM "agg_milk_cow_daily"`</sub>

## What is the avg price per litre?

**Metric:** `price_per_litre` (derived, data-designer, v2) — Volume-weighted average rupees per litre: total revenue divided by total litres. AUTHORED OVERRIDE of the auto-proposed sum — a price is a ratio and must be recomputed, never summed (the governance guard exists for exactly this).

**Answer:** 42.24 INR/L

<sub>receipt · lineage ['gold.agg_sales_daily', 'silver.sales'] · `SELECT sum("litres"*"price_per_litre")*1.0/nullif(sum("litres"),0) AS "price_per_litre" FROM "agg_sales_daily"`</sub>

