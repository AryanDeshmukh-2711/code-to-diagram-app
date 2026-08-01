-- NFR-M4: what does each plan cost to serve, against what it earns?
--
-- Median rather than mean, deliberately. Inference cost per run is a long
-- tailed distribution — one enormous project description drags a mean far
-- above what a typical run costs, and a plan priced against that mean is
-- priced against a customer who does not exist. The mean is reported beside
-- it so the gap between them is visible; when they diverge, the tail is worth
-- looking at on its own.
--
-- The tier comes from the run row, not from the account. A student who
-- upgrades in October must not retroactively turn September's free-plan runs
-- into paid ones — that would make the free plan look profitable by moving
-- its costs onto the plan that replaced it.
--
-- Postgres has no numeric overload of percentile_cont: the argument is cast
-- to double precision and the result comes back as one, which round(x, n)
-- does not accept. Hence the explicit ::numeric on every percentile.
--
-- :months  how far back to look (default 1 = the current calendar month)

WITH window_runs AS (
    SELECT
        r.tier,
        r.account_id,
        COALESCE(NULLIF(r.llm_cost_usd, ''), '0')::numeric AS cost_usd,
        r.duration_ms,
        r.llm_input_tokens + r.llm_output_tokens AS tokens
    FROM generation_runs r
    WHERE r.tier IS NOT NULL
      AND r.status = 'succeeded'
      AND r.created_at >= date_trunc('month', now()) - make_interval(months => :months - 1)
),
per_tier AS (
    SELECT
        tier,
        count(*)                                                   AS runs,
        count(DISTINCT account_id)                                 AS active_accounts,
        (percentile_cont(0.5) WITHIN GROUP (ORDER BY cost_usd))::numeric AS median_cost_per_run,
        avg(cost_usd)                                              AS mean_cost_per_run,
        (percentile_cont(0.9) WITHIN GROUP (ORDER BY cost_usd))::numeric AS p90_cost_per_run,
        sum(cost_usd)                                              AS total_cost,
        (percentile_cont(0.5) WITHIN GROUP (ORDER BY duration_ms))::numeric AS median_duration_ms,
        sum(tokens)                                                AS total_tokens
    FROM window_runs
    GROUP BY tier
),
priced AS (
    SELECT
        p.*,
        t.monthly_price,
        t.monthly_price * p.active_accounts AS revenue
    FROM per_tier p
    JOIN (VALUES {tier_prices}) AS t(tier, monthly_price) ON t.tier = p.tier
)
SELECT
    tier,
    runs,
    active_accounts,
    round(median_cost_per_run, 6)                         AS median_cost_per_run,
    round(mean_cost_per_run, 6)                           AS mean_cost_per_run,
    round(p90_cost_per_run, 6)                            AS p90_cost_per_run,
    round(total_cost, 4)                                  AS total_inference_cost,
    round(monthly_price, 2)                               AS price_per_account,
    round(revenue, 2)                                     AS revenue,
    round(revenue - total_cost, 2)                        AS gross_margin,
    CASE
        WHEN revenue > 0 THEN round(100 * (revenue - total_cost) / revenue, 1)
        ELSE NULL
    END                                                   AS margin_pct,
    CASE
        WHEN median_cost_per_run > 0
        THEN floor(monthly_price / median_cost_per_run)
        ELSE NULL
    END                                                   AS runs_until_breakeven,
    round(median_duration_ms)                             AS median_duration_ms,
    total_tokens
FROM priced
ORDER BY tier;
