# MQ8 Duty-cycle: Interim Analysis

Date: 2026-07-29/30 (Asia/Jakarta)

## Scope actually recorded

The requested direct jump from 62.5% to 100% was applied. 62.5%, 75%, and
87.5% are not result-bearing rows; the partial 62.5% capture is invalid and
is excluded from conclusions.

After the 100% heating capture, acquisition was explicitly stopped for
analysis. The partial `16_ON375_OFF625_REPEAT` CSV is excluded too. IO8 was
then re-confirmed LOW using `0,1000` on Uno COM5.

## Cold baseline

`01B_OFF_COLD_CONFIRM_20260729_165153.csv` recorded 15 minutes with IO8 LOW.
Its MQ8 30-second-bin mean was -1.138 mV; bin standard deviation was 0.030 mV.
The final five-minute mean was -1.147 mV. This is the cold/output-noise
reference for the selected tests.

## Results

| Duty | Heating CSV | Observation | Interpretation |
|---:|---|---|---|
| 12.5% | `02_ON125_OFF875_HEATING_20260729_170716.csv` | First 5 min -1.133 mV; final 5 min -1.163 mV. | No sustained change above cold noise in 40 min. |
| 25% | `04_ON250_OFF750_HEATING_20260729_180309.csv` | First 5 min -1.144 mV; final 5 min -1.128 mV. | No sustained change above cold noise in 40 min. |
| 37.5% | `08_ON375_OFF625_HEATING_RETRY_20260729_195308.csv` | Minute 5-40 means were approximately 123-126 mV; one-minute ranges 3.3-4.1 mV. | Strong output transition in first 5 min, then a stable output band for the measured 40 min. |
| 50% | `10_ON500_OFF500_HEATING_20260729_204855.csv` | Minute 5-25 means approximately 225-232 mV; later rose to 234 mV. | Strong output transition and a relatively stable mid-session band; conservative plateau candidate starts around 25.5 min under the 30-second-bin rule. |
| 62.5% | partial only | User requested direct jump to 100%. | Excluded. |
| 75% | not recorded | User requested direct jump to 100%. | Not tested. |
| 87.5% | not recorded | User requested direct jump to 100%. | Not tested. |
| 100% | `15_ON1000_OFF0_HEATING_60MIN_20260729_230351.csv` | 1-minute mean: 44.4 mV (0), 16.6 (5), 6.1 (10), 3.0 (20), 11.7 (25), 20.1 (55). | No single stable plateau across the full 60 min; continuous ON is not the stable-output reference in this run. |

## Current evidence-based recommendation

For a stable *MQ8 voltage output* in this hardware/clean-air run, `375,625`
(37.5%, 1-second period) is the lowest tested setting that demonstrates a
stable elevated output band. Use a minimum 5-minute warm-up for that specific
criterion; use 10 minutes operationally until a second cold-start repetition
confirms the result.

Do not interpret this as an absolute heater-temperature calibration: the data
proves voltage-output behavior only. In particular, 100% ON did not converge
monotonically over 60 minutes in this run, so it must not be described as a
better warm-up setting without further validation.

## Remaining validation needed before a production policy

1. Repeat 37.5% from an independently cold start.
2. Run the 100%-warm-up -> 37.5%-maintenance transfer test.
3. If lower power is required, fine-scan 25-37.5% (e.g. 27.5%, 30%, 32.5%,
   35%) after each cold baseline.
