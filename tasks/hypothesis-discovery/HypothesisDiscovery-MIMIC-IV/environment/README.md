# Data: MIMIC-IV

Source: https://physionet.org/content/mimiciv/3.1/

Access: Credentialed PhysioNet access: complete the required training and sign the data use agreement.

`python -m sle_run prepare` downloads version 3.1 from PhysioNet with the account named by `PHYSIONET_USERNAME` and `PHYSIONET_PASSWORD` in `secret/.env`, and verifies every file against the project's `SHA256SUMS.txt`. The account must already have access to this project. To download it yourself, place the extracted project so that the files below exist.

```text
data/hypothesis-discovery/mimic-iv/
    hosp/patients.csv.gz
    hosp/admissions.csv.gz
    icu/icustays.csv.gz
```

`python -m sle_run check` reports whether this layout is complete. The data stay on your machine under the
provider's terms; do not commit, upload or redistribute them.
