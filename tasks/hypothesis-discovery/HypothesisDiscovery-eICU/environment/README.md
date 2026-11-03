# Data: eICU Collaborative Research Database

Source: https://physionet.org/content/eicu-crd/2.0/

Access: Request access to the eICU Collaborative Research Database separately on PhysioNet.

`python -m sle_run prepare` downloads version 2.0 from PhysioNet with the account named by `PHYSIONET_USERNAME` and `PHYSIONET_PASSWORD` in `secret/.env`, and verifies every file against the project's `SHA256SUMS.txt`. The account must already have access to this project. To download it yourself, place the extracted project so that the files below exist.

```text
data/hypothesis-discovery/eicu/
    patient.csv.gz
    lab.csv.gz
```

`python -m sle_run check` reports whether this layout is complete. The data stay on your machine under the
provider's terms; do not commit, upload or redistribute them.
