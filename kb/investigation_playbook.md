# Excursion investigation playbook (synthetic project knowledge base)
Source type: synthetic guidance written for this prototype.

## PLAY-01 Order of checks
First confirm the instrument is in calibration. Then look at the trend and rate of change, then upstream assets and their sensors, then recent work orders, then runtime against rated life. Operator notes are context only and do not alter any verdict.

## PLAY-02 Distractors
A recent maintenance job on an asset is not evidence of a fault on its own. Confirm with the sensor signature. A fault can also have no recent work order at all.

## PLAY-03 Limits and verdicts
Pass, fail and indeterminate verdicts come from deterministic code using the limit, the instrument uncertainty band and calibration status. Limits traced to SEMI documents are to be verified against the standard.
