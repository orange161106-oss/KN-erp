# M7.2 independent technical expectations

These are invented **test fixtures**, not KNL consumables, supplier terms, operational
defaults or company-approved golden cases. Dates use UTC. Quantities share stock unit
`EA`; four decimal places are retained. Expected answers were worked out separately
from the implementation. Changing an expectation requires reviewing this arithmetic.

Common fixture: snapshot 100 at 2020-01-02; final requirement 80 = fulfilled 10 +
reserved already excluded 10 + remaining 60 due Jan 5. MSL 50. Reorder evaluated Jan 2,
exclusive horizon Jan 10, BELOW_MSL and BEFORE_CROSSING policy. Lead time 5 elapsed
days gives usable receipt Jan 7. Target 53; MOQ 20; pack 12; multiple 10; maxima not
applicable. All evidence explicitly covers the relevant dates, including December
order deadlines. No safety buffer or demand spreading is assumed.

| Case | Deliberate change | Projection at Jan 10 | Reorder / latest safe point | Purchase at receipt |
|---|---|---|---|---|
| T01 | Common fixture | 100 - 60 = 40; below MSL Jan 5 | Required; strictly before Dec 31 | 53 - 40 = 13; MOQ 20; LCM(12,10)=60; recommend 60; resulting stock 100 |
| T02 | Lead time 2 days; receipt Jan 4 | 40 | Not required yet; strictly before Jan 3 | Demand occurs after receipt: projected 100; raw -47; recommend 0 |
| T03 | Confirmed supply Jan 4: scheduled 100, received 60, cancelled 10; late 1,000 on Jan 11 | 100 + 30 - 60 = 70; no breach | Not required; no crossing/deadline | Incoming 30; raw -17; recommend 0; already received/cancelled and late supply excluded |
| T04 | Same outstanding 30 arrives Jan 6 | 70; earlier breach Jan 5 retained | Required; strictly before Dec 31 | Projected 70; raw -17; recommend 0 |
| T05 | Final 70 = 10 + 10 + remaining 50 | 50; exactly MSL; no strict breach | Not required; no deadline | 53 - 50 = 3; MOQ 20; recommend 60; stock 110 |
| T06 | T05 with AT_OR_BELOW_MSL policy | 50; still no strictly-below projection breach | Required; equality crossing Jan 5; strictly before Dec 31 | Same purchase as T05 |
| T07 | Usable snapshot 40 | -20; already below MSL, no new crossing | Required; crossing at-or-before Jan 2; historical deadline unknown | 53 - (-20) = 73; next common increment 120; stock 100 |
| T08 | Stock .3003; final/remaining .2002; MSL .15; target .4004; no MOQ; pack .25, multiple .30 | .1001; below MSL Jan 5 | Required; strictly before Dec 31 | Raw .3003; LCM(.25,.30)=1.50; recommend 1.50; stock 1.6001 |
| T09 | Common fixture with maximum order 59 | 40 | Required; strictly before Dec 31 | Candidate 60 conflicts with 59 maximum; recommendation null, not capped |
| T10 | Common fixture with pack UNKNOWN | 40 | Required; strictly before Dec 31 | Raw 13; INCOMPLETE / CONSTRAINT_UNCONFIRMED; recommendation null |
| T11 | Common fixture with target 40 | 40 | Required; strictly before Dec 31 | Raw 0; recommend 0 despite MOQ; TARGET_BELOW_MSL warning; stock 40 |
| T12 | Common fixture; older snapshot 999 at Jan 1 imported after Jan 2 snapshot | 40; current usable stock remains 100 | Required; strictly before Dec 31 | Same as T01; import arrival cannot replace a newer as-of baseline |

For projection only, no separately observed M4.2 lead-time interval is imported, so
`LEAD_TIME_UNCONFIGURED` is a non-blocking explanation. M4.3/M5.1 receive the explicit
duration above. Target/MOQ/pack/multiple/maxima are supplied fixture evidence.

Reorder and purchase are different questions: T04's later receipt repairs stock at
the purchase receipt date but cannot prevent the earlier MSL breach. The purchase
engine does not automatically add earlier replenishment, a buffer or a new target.

Event checks: T03 is 100 + 30 = 130 on Jan 4, then 130 - 60 = 70 on Jan 5.
T04 is 100 - 60 = 40 on Jan 5, then 40 + 30 = 70 on Jan 6. These event balances,
quantities and times are also independent expected fields, compared chronologically.
