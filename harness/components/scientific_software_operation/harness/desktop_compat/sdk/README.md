# Controller SDK compatibility

The SDK is an external deployment dependency. Its exact upstream revision is
recorded in manifest.json; the applicable license is in LICENSES/controller-sdk.txt.
Source identity here is retained for reproducible dependency installation.

compatibility.patch modifies three upstream files: lazy evaluator imports avoid
unrelated grading dependencies; VMware commands use configured paths, checked
completion, diagnostic records and bounded IP discovery. The preparation command
validates original and patched SHA256 values and retains upstream licensing.
No complete upstream benchmark task collection is copied into this repository.
