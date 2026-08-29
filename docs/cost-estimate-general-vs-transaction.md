# Cost Estimate: General vs. Transaction Questions

Simple reference for budgeting: what a given volume of questions costs, depending on the mix of general (knowledge-base) questions vs. transaction questions - the two cost very differently because transaction questions use `gpt-5.6-sol` for the resolve step (`RESOLVE_MODEL` in `app/config.py`), which is ~27-33x pricier per token than `gpt-4o-mini`.

## Measured per-query cost

| Type | Cost/query (USD) | Cost/query (INR, ~₹83/USD) | Source |
|---|---:|---:|---|
| General (KB) | $0.0002 | ₹0.017 | `scripts/eval_faq_coverage.py` - $0.036 / 180 |
| Transaction | $0.0023 | ₹0.19 | `scripts/eval_transaction_queries.py` - $0.0459 / 20 |

Real measured numbers, not estimates - see `docs/judgment-model-comparison.md` for how each was run.

## Cost at 1,00,000 (1 lakh) queries/month, by mix

| General : Transaction | Cost (USD) | Cost (INR) |
|---|---:|---:|
| 100% : 0% | $20.00 | ₹1,660 |
| 75% : 25% | $72.50 | ₹6,018 |
| **50% : 50%** | **$125.00** | **₹10,375** |
| 25% : 75% | $177.50 | ₹14,732 |
| 0% : 100% | $230.00 | ₹19,090 |

**50/50 mix: ≈ $125/month ≈ ₹10,375/month** for 1 lakh queries - this is **over** a ₹10,000/month budget, by about ₹375.

## Reading this

- The cost is driven almost entirely by the *transaction* share of traffic. At 50/50: transaction questions (50,000 × ₹0.19 ≈ ₹9,500) account for ~92% of the month's total; general questions (50,000 × ₹0.017 ≈ ₹850) are a small fraction by comparison.
- Break-even for a ₹10,000/month budget at 1 lakh queries is **≈ 47.8% transaction share**. Since a 50/50 split is above that line, it lands just over budget, not under it.
- Every 10 percentage points of traffic shifted from general to transaction adds roughly ₹1,750/month at this volume (₹21/1,000 questions).

## The lever, if traffic runs transaction-heavy

Every transaction question currently pays the expensive `gpt-5.6-sol` rate unconditionally, even though only status/recency-ambiguous questions ("my last purchase", "how much did I pay") actually needed it - plain ones ("show me my transactions", "why did my last order fail") don't hit that failure pattern. Narrowing the expensive model to only the questions that need it (not measured/built yet) would pull the transaction-question cost back down toward the general rate for most of that traffic, giving real headroom instead of sitting right at (or just over) the ₹10,000 line.
