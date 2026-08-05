# Statistical methods

## What the strategies predict

Each strategy assigns nonnegative weights to every white and special ball. Tickets are then sampled from those weights. White balls are sampled without replacement; the special ball is sampled separately.

The weights are hypotheses, not claims that historical frequency changes the mathematical odds of an independently drawn ball.

## Strategies

### Pure Random

Every number receives equal weight. This is the control and must remain in every comparison.

### Bayesian Hot and Cold

Observed marginal inclusion counts are combined with a prior centered on the fair-draw probability:

$$p_0 = k/N$$

$$\hat p_i = \frac{c_i + p_0 s}{D + s}$$

where $k$ is the number selected, $N$ is the pool size, $c_i$ is the observed count for number $i$, $D$ is the number of drawings, and $s$ is the prior strength. This shrinkage prevents small datasets from producing extreme weights too easily.

### Hot/Cold Mix

This strategy favors both tails of the shrinkage-adjusted frequency distribution. It tests the idea that unusually common and unusually uncommon numbers may both be informative.

### Recent Trend

Draws receive exponentially decreasing weights with a configurable half-life. A prior centered on the theoretical probability is retained so a short burst cannot completely dominate the generator.

### Overdue

The current absence of each number is compared with the theoretical average gap. This is included as an explicit test of a popular hypothesis; it does not assume the gambler's fallacy is true.

### Combined

Bayesian Hot, Recent Trend, and Overdue weights are combined using a weighted geometric mean. Geometric blending prevents a single large component value from dominating as easily as a raw arithmetic sum.

## Walk-forward testing

For target drawing $t$, a strategy receives only drawings $1$ through $t-1$. The backtester then generates seeded ticket portfolios, reveals $t$, scores the results, and moves to $t+1$. The model is never trained using a future drawing.

Each strategy is measured using:

- average white-ball overlap per ticket
- special-ball match rate
- lift relative to the theoretical random expectation
- top-ranked white-ball hits
- Brier scores for probability quality
- a draw-level bootstrap interval around white-match lift
- the full white-match distribution and jackpot-hit count

Ticket simulations are repeated because a single generated portfolio can be unusually lucky or unlucky. Seeds make results reproducible.

## Interpretation

A result is not persuasive merely because its lift is positive. At minimum it should:

1. outperform the random control across a large walk-forward period;
2. show probability scores better than the fair-draw baseline;
3. remain stable under different starting dates and parameters;
4. survive correction for the fact that many strategies were tested; and
5. continue to perform in locked predictions created before real drawings.

Mega Millions' April 2025 rule era remains especially data-limited. Its results should be treated as exploratory until substantially more current-format drawings accumulate.

