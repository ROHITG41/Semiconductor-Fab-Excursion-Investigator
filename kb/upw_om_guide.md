# UPW operations and troubleshooting guide (synthetic project knowledge base)
Source type: synthetic guidance written for this prototype. Not a SEMI standard and not vendor documentation.

## UPW-01 TOC rising at point of use
A slow, steady rise in total organic carbon (TOC) at the point of use, with the upstream EDI outlet TOC rising in step, points to the organic-oxidation stage. Check the UV-185nm lamp intensity trend and the lamp runtime against its rated life before looking at downstream causes. If the EDI outlet TOC is normal while only the point-of-use analyzer rises, suspect the analyzer.

## UPW-02 UV-185nm lamp ageing
UV lamp output falls as running hours accumulate. When lamp hours exceed the rated life, oxidation of organics becomes incomplete and TOC drifts upward, often with a falling UV intensity reading. Corrective action: plan lamp replacement, verify intensity after replacement, and re-measure TOC after the loop has flushed.

## UPW-03 Resistivity drop at point of use
A sudden fall in resistivity downstream of the polishing stage, with normal resistivity at the EDI outlet, points to the mixed-bed polishing resin. Compare resin runtime with its rated life. A gradual fall that follows rising RO permeate conductivity points upstream to the RO stage instead.

## UPW-04 Mixed-bed polishing resin exhaustion
Exhausted ion-exchange resin lets ions break through, so resistivity drops quickly. Corrective action: replace or regenerate the resin bed, flush to rinse down, and verify resistivity recovers toward the limit before returning the loop to service.

## UPW-05 RO membrane degradation
Ageing or fouled RO membranes pass more ions, so permeate conductivity rises and the load on downstream EDI and polishing stages increases. Check membrane runtime against rated life and the cleaning-in-place history. Corrective action: schedule cleaning or membrane replacement.

## UPW-06 Dissolved oxygen rise after valve work
A step rise in dissolved oxygen at the point of use shortly after maintenance on a valve or fitting upstream suggests air ingress through a leaking diaphragm or seal. Check the work-order history for recent valve work on assets upstream of the point of use. Corrective action: re-inspect and re-seat or replace the diaphragm, leak-test, and flush.

## UPW-07 Analyzer out of calibration
A reading that drifts alone, while upstream sensors and neighbouring parameters stay normal, and whose calibration is overdue, should not be trusted as a real excursion. Corrective action: verify with a reference instrument or grab sample and recalibrate before any lot decision.
