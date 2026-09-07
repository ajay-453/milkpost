# Analyst report — barnboard

_3 question(s) over the governed semantic layer._

## Which cows are the top and bottom producers, and is herd yield trending up or down?

**Metric:** `cows` (sum, unassigned, v1) — Count of cows (additive rollup of cows_count).

**Answer:** 12 count

<sub>receipt · lineage ['gold.agg_cows_daily'] · `SELECT sum("cows_count") AS "cows" FROM "agg_cows_daily"`</sub>

## What is average daily milk yield per cow and per breed?

> No metric matched this question.

## How much revenue have milk sales generated and at what average price per litre?

**Metric:** `price_per_litre` (sum, unassigned, v1) — Sum of price_per_litre over the agg_sales_daily fact.

**Answer:** 422.38 

<sub>receipt · lineage ['gold.agg_sales_daily'] · `SELECT sum("price_per_litre") AS "price_per_litre" FROM "agg_sales_daily"`</sub>

