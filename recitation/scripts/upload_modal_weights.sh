#!/usr/bin/env bash
# Upload recitation model artifacts to the Modal Volume "suhuf-recitation-models".
# Run from recitation/ AFTER `modal setup`. The Volume mounts at /app/models in
# the container, so each artifact lands where server.py / ensemble_config.json expect it.
#
# Weights are gitignored (~4GB) and live only locally — this is how they reach prod.
set -euo pipefail
cd "$(dirname "$0")/.."   # -> recitation/
VOL="suhuf-recitation-models"

# (dir-or-file in models/)  ->  remote path on the Volume (== /app/models/<remote>)
ARTIFACTS=(
  "ssl_xls_r_v5"          # base (primary)
  "xlsr_i3rab_contr"      # i3rab agreement member
  "xlsr_contr1000"        # consonant member
  "gmm"                   # MixGoP GMMs (engine)
  "error_classifier.pkl"  # classify_words GBM
  "type_classifier.pkl"
)

for a in "${ARTIFACTS[@]}"; do
  if [ ! -e "models/$a" ]; then
    echo "MISSING models/$a — download it from the volume/S3 first" >&2; exit 1
  fi
  echo ">> uploading models/$a -> $VOL:/$a"
  modal volume put --force "$VOL" "models/$a" "/$a"
done
echo "done. verify: modal volume ls $VOL"
