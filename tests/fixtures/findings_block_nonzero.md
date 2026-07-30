### Experiment 1: can SWE-bench Verified separate its adjacent top 20?

**Statistically distinguishable adjacent pairs: 1 of 19**, at
500 instances under the pre-registered exact McNemar plus Holm procedure. Of the
19, 9 are indistinguishable by tie arithmetic (equal published counts
force the exact test to its maximum p-value), and 10 admit a real test, with 1 rejecting and 9 not.

This headline is derived from published leaderboard aggregates alone: the adjacent gaps follow
from the published rates, the smallest attainable p-value from the registered test convention,
and the Holm threshold from the family size. The per-instance work below characterizes the
finding but cannot overturn it.

The family gateway floor is 10 resolved instances: no adjacent pair whose gap is below
10 can produce the family's first rejection at any discordance configuration. The
largest observed gap is 7. 2 of 19 pairs could reject under best-case overlaps.

Scope: adjacent pairs only. Non-adjacent comparisons (rank 1 against rank
20, for example) are out of scope and may well separate. Separable count
2 (best case, D2.7), resolved count 1 (observed).

| pair | resolved-count gap | observed discordance | observed p-value | Holm-adjusted p-value |
|---|---|---|---|---|
| rank_1_vs_2 | 0 | 36 | 1.000 | 1.000 |
| rank_2_vs_3 | 2 | 64 | 0.901 | 1.000 |
| rank_3_vs_4 | 7 | 65 | 0.457 | 1.000 |
| rank_4_vs_5 | 3 | 53 | 0.784 | 1.000 |
| rank_5_vs_6 | 0 | 56 | 1.000 | 1.000 |
| rank_6_vs_7 | 0 | 66 | 1.000 | 1.000 |
| rank_7_vs_8 | 2 | 64 | 0.901 | 1.000 |
| rank_8_vs_9 | 3 | 63 | 0.801 | 1.000 |
| rank_9_vs_10 | 0 | 56 | 1.000 | 1.000 |
| rank_10_vs_11 | 1 | 75 | 1.000 | 1.000 |
| rank_11_vs_12 | 0 | 66 | 1.000 | 1.000 |
| rank_12_vs_13 | 2 | 68 | 0.904 | 1.000 |
| rank_13_vs_14 | 2 | 36 | 0.868 | 1.000 |
| rank_14_vs_15 | 0 | 52 | 1.000 | 1.000 |
| rank_15_vs_16 | 1 | 57 | 1.000 | 1.000 |
| rank_16_vs_17 | 0 | 56 | 1.000 | 1.000 |
| rank_17_vs_18 | 1 | 59 | 1.000 | 1.000 |
| rank_18_vs_19 | 0 | 74 | 1.000 | 1.000 |
| rank_19_vs_20 | 0 | 80 | 1.000 | 1.000 |

The observed discordance, p-values, intervals, and MDEs read per-instance artifacts and carry
the D4 harness comparability caveat: submissions do not record their harness version. The
pair identity and the resolved-count gap derive from published aggregates and do not.

Secondaries, as registered: the non-tied family (10 pairs, first critical
0.005, gap floor 9) rejects 0. The
no_logs sensitivity drops unlogged instances pairwise, affects 5 of the 19
pairs, and its Holm pass rejects 1 of them. The harness straddle diagnostic finds rank_3_vs_4 straddling the 2024-04-15 evaluation fix (analysed entries predating it: 1); the earliest analysed submission date is 2025-06-03.
