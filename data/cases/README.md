\# Trial Equity – Dataset Cases



This folder contains \*\*dataset cases\*\*: small, curated inputs that demonstrate how to use the Trial Equity CLI and validate key functionality end-to-end.



Each case is a subfolder under `data/cases/` with the following structure:



data/cases/

case-basic/

sample.csv

mapping.yaml

README.md

case-missing-cols/

sample.csv

mapping.yaml

README.md

case-edge/

sample.csv

mapping.yaml

README.md





---



\## How to Run a Case



From the project root:



```bash

\# Map → canonical

te map --in data/cases/<case>/sample.csv --map data/cases/<case>/mapping.yaml --salt TEST --out out/canonical.csv



\# Validate

te validate --in out/canonical.csv



\# Audit (e.g. selection by race)

te audit --in out/canonical.csv --group race --metric selection --out out/selection\_by\_race.csv



\# Risk ratios vs reference group

te rr --in out/canonical.csv --group race --metric selection --ref White --out out/rr\_selection\_by\_race.csv



Outputs are written to the out/ folder. You can open them in Excel or any CSV viewer.



Goals



Consistency: Each case is small but structured, so failures are easy to debug.



Coverage: Different cases test different schema issues or fairness metrics.



Reproducibility: Anyone cloning the repo can run these commands and verify behavior.



Case Types



Basic case



A minimal, valid dataset that maps cleanly to Canonical v1.



Used for smoke testing.



Missing columns case



Omits one or more required Canonical columns.



Validates that te validate fails as expected.



Edge case



Includes groups with zero denominators, extreme imbalance, or other tricky conditions.



Tests metrics like risk ratios and confidence intervals.



Adding a New Case



Create a new folder under data/cases/ (e.g. case-newscenario/).



Add sample.csv and mapping.yaml that illustrate the case.



Write a short README.md explaining what the case tests.



Verify it runs with the commands above.



