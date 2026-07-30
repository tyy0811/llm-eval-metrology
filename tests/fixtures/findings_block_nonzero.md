### Experiment 1: can SWE-bench Verified separate its adjacent top 3?

**Statistically distinguishable adjacent pairs: 1 of 2**, at
500 instances under the pre-registered exact McNemar plus Holm procedure. Of the
2, 0 are indistinguishable by tie arithmetic (equal published counts
force the exact test to its maximum p-value), and 2 admit a real test, with 1 rejecting and 1 not.

This headline is derived from published leaderboard aggregates alone: the adjacent gaps follow
from the published rates, the smallest attainable p-value from the registered test convention,
and the Holm threshold from the family size. The per-instance work below characterizes the
finding but cannot overturn it.

The family gateway floor is 7 resolved instances: no adjacent pair whose gap is below
7 can produce the family's first rejection at any discordance configuration. The
largest observed gap is 40. 2 of 2 pairs could reject under best-case overlaps.

Scope: adjacent pairs only. Non-adjacent comparisons (rank 1 against rank
3, for example) are out of scope and may well separate. Separable count
2 (best case, D2.7), resolved count 1 (observed).

| pair | resolved-count gap | observed discordance | observed p-value | Holm-adjusted p-value |
|---|---|---|---|---|
| rank_1_vs_2 | 40 | 50 | 0.000 | 0.000 |
| rank_2_vs_3 | 6 | 50 | 0.480 | 0.480 |

The observed discordance, p-values, intervals, and MDEs read per-instance artifacts and carry
the D4 harness comparability caveat: submissions do not record their harness version. The
pair identity and the resolved-count gap derive from published aggregates and do not.

Secondaries, as registered: the non-tied family (2 pairs, first critical
0.025, gap floor 7) rejects 1. The
no_logs sensitivity drops unlogged instances pairwise, affects 1 of the 2
pairs, and its Holm pass rejects 1 of them. The harness straddle diagnostic finds rank_2_vs_3 straddling the 2024-04-15 evaluation fix (analysed entries predating it: 1); the earliest analysed submission date is 2023-11-01.
