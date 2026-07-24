# Trial 1 — Affine Matrix Explain Sheet

Use this when walking through the calibration math.

Companion JSON (exact floats): `trial1_affine_matrix_explain.json`

---

## Affine matrix (fitted on 8 of 9 points)

```text
[x']   [  4.5399    0.5050   -3402.55 ] [x]
[y'] = [  0.0817    3.9479   -2241.79 ] [y]
[1 ]   [  0.0000    0.0000      1.00 ] [1]
```

### Parameter meanings

| Symbol | Value    | Meaning |
|--------|----------|---------|
| `a`    | 4.5399   | X scale / stretch |
| `b`    | 0.5050   | Shear: how much Y affects corrected X |
| `tx`   | −3402.55 | X translation (bias in pixels) |
| `c`    | 0.0817   | Shear: how much X affects corrected Y |
| `d`    | 3.9479   | Y scale / stretch |
| `ty`   | −2241.79 | Y translation (bias in pixels) |

**Equations:**

```text
x' = 4.5399·x + 0.5050·y − 3402.55
y' = 0.0817·x + 3.9479·y − 2241.79
```

---

## How to interpret Trial 1

- **Large negative `tx`, `ty`:** raw gaze sits far from true targets; the matrix shifts the cloud.
- **`a` and `d` ≈ 4:** observed coords are compressed vs true screen space; the matrix stretches them.
- **Small `b`, `c`:** mild shear/tilt, not a big rotation.
- **Fit set:** 8 points used; **Target ID 2 excluded** as a post-fit outlier.

### Key metrics

| Metric | Value |
|--------|-------|
| Mean error (fit set) before → after | **205.9 → 29.5 px** |
| MSE before (all) | 58453 px² |
| MSE after (all) | 1907 px² |
| MSE after (fit set) | 1050 px² |
| Alignment | `grid_d-10.00_t0.3` (trim 0.3 s) |
| Condition # | ~30655 |
| Excluded | ID 2 (post-fit outlier) |

---

## Per-target table (Trial 1)

| ID | Used? | True (x, y) | Observed (x, y) | Corrected (x, y) | Err before | Err after |
|----|-------|-------------|-----------------|------------------|------------|-----------|
| 1 | fit | (641, 335) | (822.4, 635.8) | (651.9, 335.5) | 351.2 | **10.9** |
| 2 | **excluded** | (864, 335) | (865.7, 658.5) | (860.3, 428.5) | 323.5 | 93.6 |
| 3 | fit | (1087, 335) | (913.6, 634.3) | (1065.4, 337.2) | 345.9 | 21.7 |
| 4 | fit | (641, 558) | (812.2, 702.3) | (639.2, 597.0) | 223.8 | 39.1 |
| 5 | fit | (864, 558) | (868.2, 684.7) | (884.5, 532.4) | 126.8 | 32.8 |
| 6 | fit | (1087, 558) | (912.6, 693.6) | (1090.6, 570.8) | 220.9 | 13.3 |
| 7 | fit | (641, 782) | (804.9, 737.2) | (623.9, 734.2) | 169.9 | 50.7 |
| 8 | fit | (864, 782) | (855.7, 759.1) | (865.6, 825.0) | 24.3 | 43.1 |
| 9 | fit | (1087, 782) | (907.4, 741.0) | (1091.0, 757.8) | 184.2 | 24.5 |

**Exclusion note:** ID 2 was dropped because after fitting it still had ~94 px error (> 75 px threshold). It is still shown corrected, but it did **not** influence the matrix.

---

## Worked example — Target ID 1

Observed: `(822.36, 635.80)`  
True: `(641, 335)`

```text
x' = 4.5399×822.36 + 0.5050×635.80 − 3402.55 = 651.93
y' = 0.0817×822.36 + 3.9479×635.80 − 2241.79 = 335.49
```

| | Value |
|--|-------|
| Corrected | ≈ (651.9, 335.5) |
| Error before | **351.2 px** |
| Error after | **10.9 px** |

Talking point: *“One multiply by this matrix moves a badly offset fixation almost onto the true target.”*

---

## 20-second script

> “This 3×3 affine matrix maps observed gaze pixels to true screen pixels. The diagonal terms (~4.5 and ~3.9) stretch X and Y; the last column (−3400, −2240) removes a large bias. We fit it with least squares on the calibration grid, dropped one outlier (ID 2), and mean error on the remaining points fell from about 206 px to 30 px.”
