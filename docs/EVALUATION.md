# WorthIt Evaluation Summary

## Evaluation setup

The evaluation uses 36 user queries and 451 manually assigned product-query relevance judgments. Relevance is graded from 0 (bad) to 3 (excellent). The primary evaluation script is `eval/run_eval.py`; it evaluates the same query set with four ranking systems and reports the mean nDCG@10 and MAP@10.

- **nDCG@10** evaluates the ordering of graded relevance in the top 10; higher is better.
- **MAP@10** treats grades 2 and 3 as relevant and summarizes precision at relevant ranks; higher is better.
- The paired bootstrap compares per-query nDCG differences using 10,000 paired resamples. Reported p-values are one-sided tests for a positive improvement.

## Primary results (unguarded; report these first)

| System | nDCG@10 | MAP@10 |
|---|---:|---:|
| `rating_sort` | 0.5682 | 0.3473 |
| `weight_zero` | 0.9240 | 0.8984 |
| `floor_only` | 0.9054 | 0.8648 |
| `full` | 0.9303 | 0.8471 |

The full system achieved the highest nDCG@10, while `weight_zero` achieved the highest MAP@10. The results therefore do not show that the full system is best on every metric. The unguarded floor-only system scored 0.0186 lower in nDCG@10 than priority-only ranking in the reported run. Adding price efficiency to floor-only ranking increased nDCG@10 by 0.0249; the reported one-sided bootstrap p-value was 0.0583, which is above the conventional 0.05 threshold.

## Post-hoc guard experiment

| System | nDCG@10 | MAP@10 |
|---|---:|---:|
| `floor_raw` | 0.9054 | 0.8648 |
| `floor_guarded` | 0.9227 | 0.8874 |
| `full_raw` | 0.9303 | 0.8471 |
| `full_guarded` | 0.9437 | 0.8629 |

The guard skips a floor when its threshold is at or above the median of valid aspect scores in the candidate pool. It altered 8 of 36 queries in the reported experiment. The guarded full system had the highest nDCG@10 in this table, but its comparison reported a one-sided p-value of 0.1293. This is a post-hoc experiment and should not replace the primary unguarded result.

## Limitations

1. Relevance judgments were created by one annotator using price and aspect scores related to the ranking features. This creates potential circularity and can favour aspect-based methods.
2. The dataset is small (reported as 25 laptops and 493 reviews); results may not generalize to other products or marketplaces.
3. The default ABSA is rule/lexicon-based and can miss context, sarcasm, and nuanced sentiment.
4. Price efficiency is relative to the candidate pool, so scores can change when the available products change.
5. A bootstrap p-value near zero is rounded output, not literally zero. Statistical significance should be described only for the specific one-sided comparison tested.

## Reproducibility commands

```powershell
python eval/status.py
python eval/run_eval.py
python eval/guarded.py
python eval/diagnose.py
```

The figures above are the outputs previously reported by the project owner. Re-run the commands against the final local database before submitting if the data or ranking code has changed.
