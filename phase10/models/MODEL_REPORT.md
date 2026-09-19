# UrbanTwin Random Forest validation report

Overall verdict: **mixed_results_do_not_claim_overall_accuracy**

The final test contains eight participants excluded from training and model selection.
All cross-validation splits are also grouped by participant.

| Target | Final unseen score | Baseline | Verdict |
|---|---:|---:|---|
| comfort | MAE 0.82; R2 0.35 | MAE 1.25 | promising |
| stress | MAE 0.71; R2 0.14 | MAE 0.81 | supported_for_prototype |
| walking_likelihood | MAE 0.70; R2 0.56 | MAE 1.06 | supported_for_prototype |
| avoidance_likelihood | MAE 1.28; R2 -0.08 | MAE 1.38 | not_validated |
| route_choice | macro F1 0.22 | macro F1 0.47 | not_validated |

## Interpretation

A lower MAE is better for 1–5 survey scores; a higher macro F1 is better for route choice.
A target is not accepted merely because it has a score: it must beat both the simple baseline and shuffled-label control in grouped cross-validation and beat the baseline on the untouched final participants.
`supported_for_prototype` permits a hackathon demonstration with an explicit limitation. It does not establish city-wide or real-world predictive accuracy.

## Known limitations

- Only 41 participants; most are under 25.
- Temperature, crowding and shade co-vary across the four scenarios.
- Labels are self-reported intentions, not observed pedestrian behavior.
- Avoidance and route-choice each have only one labeled scenario per participant.
