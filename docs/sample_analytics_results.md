# Data quality analytics

## 1_record_failure_pct_by_run_and_dataset

```
                    run_id   dataset  files  rows_processed  rows_rejected  reject_pct
run_20261115T232316_4df407     sales      3             764            137       17.93
run_20261115T232316_4df407 customers      1             105             25       23.81
run_20261115T232351_418f18     sales      1             601              9        1.50
run_20261115T232351_418f18 customers      1             100              2        2.00
```

## 2_rule_failure_pct_by_run

```
                    run_id  rules_run  rules_failed  rule_fail_pct
run_20261115T232316_4df407         38            20          52.63
run_20261115T232351_418f18         23             7          30.43
```

## 3_most_common_issues_by_rule

```
  dataset                       rule_id         rule_type  rows_failed  rows_checked  failure_pct  times_failed
    sales        sales_required_columns  required_columns           50          1365         3.66             1
    sales    sales_customer_id_not_null          not_null           17          1315         1.29             3
    sales  sales_payment_method_allowed    allowed_values           13          1315         0.99             2
    sales       sales_quantity_positive     numeric_range           11          1315         0.84             2
    sales        sales_order_date_valid        valid_date           11          1315         0.84             2
    sales       sales_no_duplicate_rows no_duplicate_rows           11          1315         0.84             3
    sales sales_unit_price_not_negative     numeric_range            8          1315         0.61             2
    sales         sales_order_id_unique            unique            8          1315         0.61             1
customers        customers_email_format             regex            7           205         3.41             2
customers           customers_id_unique            unique            6           205         2.93             1
```

## 4_most_common_issue_categories

```
        rule_type  rows_failed  share_of_all_failures_pct
 required_columns           50                      28.09
   allowed_values           29                      16.29
         not_null           26                      14.61
    numeric_range           19                      10.67
       valid_date           14                       7.87
           unique           14                       7.87
no_duplicate_rows           13                       7.30
            regex            7                       3.93
            dtype            6                       3.37
```

## 5_run_over_run_reject_trend

```
  dataset                     run_id          started_at  reject_pct  previous_reject_pct  change_pct_points
customers run_20261115T232316_4df407 2026-11-15 23:23:44       23.81                  NaN                NaN
customers run_20261115T232351_418f18 2026-11-15 23:24:11        2.00                23.81             -21.81
    sales run_20261115T232316_4df407 2026-11-15 23:23:16       17.93                  NaN                NaN
    sales run_20261115T232351_418f18 2026-11-15 23:23:51        1.50                17.93             -16.43
```

## 6_rule_comparison_latest_vs_previous_run

```
  dataset                       rule_id  previous_failure_pct  latest_failure_pct         trend
customers      customers_email_not_null                  3.81                0.00         FIXED
customers           customers_id_unique                  5.71                0.00         FIXED
customers   customers_no_duplicate_rows                  1.90                0.00         FIXED
customers   customers_signup_date_valid                  2.86                0.00         FIXED
customers        customers_email_format                  5.71                1.00 STILL FAILING
customers     customers_segment_allowed                  3.81                1.00 STILL FAILING
customers           customers_id_format                  0.00                0.00 STILL PASSING
customers         customers_id_not_null                  0.00                0.00 STILL PASSING
customers    customers_required_columns                  0.00                0.00 STILL PASSING
    sales        sales_category_allowed                  0.84                0.00         FIXED
    sales     sales_order_date_not_null                  0.70                0.00         FIXED
    sales         sales_order_id_unique                  1.12                0.00         FIXED
    sales     sales_quantity_is_integer                  0.84                0.00         FIXED
    sales        sales_required_columns                  6.54                0.00         FIXED
    sales sales_unit_price_not_negative                  1.12                0.00         FIXED
    sales    sales_customer_id_not_null                  2.10                0.33 STILL FAILING
    sales       sales_no_duplicate_rows                  1.40                0.17 STILL FAILING
    sales        sales_order_date_valid                  1.40                0.17 STILL FAILING
    sales  sales_payment_method_allowed                  1.40                0.50 STILL FAILING
    sales       sales_quantity_positive                  1.26                0.33 STILL FAILING
    sales           sales_country_known                  0.70                0.00 STILL PASSING
    sales       sales_order_id_not_null                  0.00                0.00 STILL PASSING
    sales    sales_unit_price_is_number                  0.00                0.00 STILL PASSING
```

## 7_rejected_files

```
                    run_id dataset                     source_file  rows_processed         finished_at
run_20261115T232316_4df407   sales sales_2026_01_legacy_export.csv              50 2026-11-15 23:23:17
```
