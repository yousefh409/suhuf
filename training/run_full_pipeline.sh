#!/bin/bash
# Full pipeline: wait for TTS → augment → retrain
# Run this after generate_tts_data.py is already running
set -e

cd /workspace/i3rab
export PYTHONUNBUFFERED=1

echo "=== STEP 1: Wait for TTS generation ==="
while pgrep -f generate_tts > /dev/null 2>&1; do
    COUNT=$(ls data/tts/wavs/*.wav 2>/dev/null | wc -l)
    echo "  TTS generating... $COUNT WAVs so far"
    sleep 60
done
echo "TTS generation complete!"
wc -l data/tts/tts_manifest.json

echo ""
echo "=== STEP 2: Prepare augmented data (speed perturb + MUSAN noise) ==="
python3 training/prepare_augmented.py \
    --data-dir data/ \
    --noise-fraction 0.4

echo ""
echo "=== STEP 3: Clear old checkpoints ==="
rm -rf checkpoints/v2/
mkdir -p checkpoints/v2/

echo ""
echo "=== STEP 4: Retrain PCD with augmented data ==="
python3 training/finetune_pcd.py \
    --data-dir data/ \
    --output-dir checkpoints/v2/ \
    --train-manifest data/train_combined.json \
    --epochs 40 \
    --batch-size 32 \
    --precision bf16-mixed \
    --accumulate-grad 2 \
    --lr 2e-5 \
    --warmup-steps 500 \
    --freeze-encoder-epochs 3 \

echo ""
echo "=== DONE ==="
ls -lh checkpoints/v2/
echo "Training complete!"
