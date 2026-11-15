-- name: 1_record_failure_pct_by_run_and_dataset
-- What share of incoming records was rejected, per run and dataset?
SELECT run_id,
       dataset,
       COUNT(*)                                                   AS files,
       SUM(rows_processed)                                        AS rows_processed,
       SUM(rows_rejected)                                         AS rows_rejected,
       ROUND(100.0 * SUM(rows_rejected) / NULLIF(SUM(rows_processed), 0), 2) AS reject_pct
FROM dq_pipeline_runs
GROUP BY run_id, dataset
ORDER BY MIN(started_at), dataset;

-- name: 2_rule_failure_pct_by_run
-- What share of validation rules failed in each run?
SELECT run_id,
       COUNT(*)                                             AS rules_run,
       SUM(CASE WHEN status = 'FAIL' THEN 1 ELSE 0 END)     AS rules_failed,
       ROUND(100.0 * SUM(CASE WHEN status = 'FAIL' THEN 1 ELSE 0 END) / COUNT(*), 2) AS rule_fail_pct
FROM dq_validation_results
GROUP BY run_id
ORDER BY MIN(executed_at);

-- name: 3_most_common_issues_by_rule
-- Which rules reject the most rows, across all runs?
SELECT dataset,
       rule_id,
       rule_type,
       SUM(rows_failed)                                       AS rows_failed,
       SUM(rows_checked)                                      AS rows_checked,
       ROUND(100.0 * SUM(rows_failed) / NULLIF(SUM(rows_checked), 0), 2) AS failure_pct,
       SUM(CASE WHEN status = 'FAIL' THEN 1 ELSE 0 END)       AS times_failed
FROM dq_validation_results
GROUP BY dataset, rule_id, rule_type
HAVING SUM(rows_failed) > 0
ORDER BY rows_failed DESC
LIMIT 10;

-- name: 4_most_common_issue_categories
-- Which kind of problem is most common (missing values, duplicates, bad dates ...)?
SELECT rule_type,
       SUM(rows_failed)            AS rows_failed,
       ROUND(100.0 * SUM(rows_failed) / NULLIF((SELECT SUM(rows_failed) FROM dq_validation_results), 0), 2)
                                   AS share_of_all_failures_pct
FROM dq_validation_results
GROUP BY rule_type
HAVING SUM(rows_failed) > 0
ORDER BY rows_failed DESC;

-- name: 5_run_over_run_reject_trend
-- Is each dataset getting better or worse compared with the previous run?
WITH per_run AS (
    SELECT run_id,
           dataset,
           MIN(started_at) AS started_at,
           ROUND(100.0 * SUM(rows_rejected) / NULLIF(SUM(rows_processed), 0), 2) AS reject_pct
    FROM dq_pipeline_runs
    GROUP BY run_id, dataset
)
SELECT dataset,
       run_id,
       started_at,
       reject_pct,
       LAG(reject_pct) OVER (PARTITION BY dataset ORDER BY started_at, run_id) AS previous_reject_pct,
       ROUND(reject_pct - LAG(reject_pct) OVER (PARTITION BY dataset ORDER BY started_at, run_id), 2)
                                                                       AS change_pct_points
FROM per_run
ORDER BY dataset, started_at, run_id;

-- name: 6_rule_comparison_latest_vs_previous_run
-- Rule by rule: latest run against the run before it.
WITH runs AS (
    SELECT run_id, ROW_NUMBER() OVER (ORDER BY MIN(started_at) DESC, run_id DESC) AS recency
    FROM dq_pipeline_runs
    GROUP BY run_id
),
per_rule AS (
    SELECT r.recency,
           v.dataset,
           v.rule_id,
           ROUND(100.0 * SUM(v.rows_failed) / NULLIF(SUM(v.rows_checked), 0), 2) AS failure_pct,
           MAX(CASE WHEN v.status = 'FAIL' THEN 1 ELSE 0 END)                   AS failed
    FROM dq_validation_results v
    JOIN runs r ON r.run_id = v.run_id
    WHERE r.recency <= 2
    GROUP BY r.recency, v.dataset, v.rule_id
)
SELECT cur.dataset,
       cur.rule_id,
       prev.failure_pct AS previous_failure_pct,
       cur.failure_pct  AS latest_failure_pct,
       CASE
           WHEN prev.rule_id IS NULL                 THEN 'NEW RULE'
           WHEN prev.failed = 1 AND cur.failed = 0   THEN 'FIXED'
           WHEN prev.failed = 0 AND cur.failed = 1   THEN 'REGRESSED'
           WHEN cur.failed = 1                       THEN 'STILL FAILING'
           ELSE 'STILL PASSING'
       END              AS trend
FROM per_rule cur
LEFT JOIN per_rule prev
       ON prev.recency = 2 AND prev.dataset = cur.dataset AND prev.rule_id = cur.rule_id
WHERE cur.recency = 1
ORDER BY cur.dataset, trend, cur.rule_id;

-- name: 7_rejected_files
-- Files rejected outright (for example schema drift), newest first.
SELECT run_id, dataset, source_file, rows_processed, finished_at
FROM dq_pipeline_runs
WHERE file_status = 'REJECTED'
ORDER BY finished_at DESC;