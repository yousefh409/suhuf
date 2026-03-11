#!/bin/bash
set -e
export PYTHONUNBUFFERED=1
cd /workspace/i3rab

echo "=== STEP 2: Prepare augmented data ==="
python3 training/prepare_augmented.py --data-dir data/ --noise-fraction 0.4

echo ""
echo "=== STEP 3: Clear old v2 checkpoints ==="
rm -rf checkpoints/v2/
mkdir -p checkpoints/v2/

echo ""
echo "=== STEP 4: Retrain PCD ==="
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
    --freeze-encoder-epochs 3

echo ""
echo "=== DONE ==="
ls -lh checkpoints/v2/
