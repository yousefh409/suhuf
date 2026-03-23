#!/bin/bash
# ============================================================
# v4 PCD Training Pipeline
#
# Fine-tunes FROM v3 checkpoint with targeted fatha discrimination
# data to improve tashkeel detection recall (currently 80.5%).
#
# Prerequisites on RunPod:
#   - data/clartts/ (ClArTTS train/test manifests + wavs)
#   - data/musan/ (MUSAN noise corpus)
#   - data/contrastive/ (v3 contrastive pairs)
#   - v3 model checkpoint (.nemo)
#
# Usage:
#   cd /workspace/i3rab && bash training/run_v4.sh
#
# Options (env vars):
#   V3_MODEL=path/to/v3.nemo  — override v3 model location
#   SKIP_TTS=1                — skip TTS generation (default: ClArTTS-only)
#   INCLUDE_V3=1              — include v3 contrastive pairs (default: yes)
#   LR=1e-5                   — learning rate override
#   EPOCHS=12                 — epoch count override
# ============================================================

set -e
export PYTHONUNBUFFERED=1

cd /workspace/i3rab

echo "========================================"
echo "  PCD v4 Fine-tuning Pipeline"
echo "  Target: fatha discrimination + tashkeel recall"
echo "========================================"

# ── Check GPU ──
if ! command -v nvidia-smi &> /dev/null; then
    echo "ERROR: No GPU detected."
    exit 1
fi
echo "GPU:"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
echo ""

# ── Find v3 model ──
V3_MODEL=${V3_MODEL:-""}
if [ -z "$V3_MODEL" ]; then
    for p in \
        checkpoints/v3/pcd_clartts_final.nemo \
        checkpoints/pcd_clartts_final.nemo \
        models/pcd_clartts_v3.nemo; do
        if [ -f "$p" ]; then
            V3_MODEL="$p"
            break
        fi
    done
fi

if [ -z "$V3_MODEL" ] || [ ! -f "$V3_MODEL" ]; then
    echo "ERROR: v3 model not found. Set V3_MODEL=path/to/v3.nemo"
    echo "Checked: checkpoints/v3/pcd_clartts_final.nemo, checkpoints/pcd_clartts_final.nemo, models/pcd_clartts_v3.nemo"
    exit 1
fi
echo "v3 model: $V3_MODEL"

# ── Check data ──
if [ ! -f "data/clartts/train_manifest.json" ]; then
    echo "ERROR: ClArTTS training manifest not found at data/clartts/train_manifest.json"
    echo "Run: python training/prepare_data.py --output-dir data/"
    exit 1
fi
echo "ClArTTS: $(wc -l < data/clartts/train_manifest.json) training samples"

# ── Install deps if needed ──
echo ""
echo "[0/5] Checking dependencies..."
python3 -c "import nemo.collections.asr" 2>/dev/null || {
    echo "Installing NeMo..."
    pip install -q 'nemo_toolkit[asr]>=2.0.0' pytorch-lightning omegaconf datasets soundfile scipy numpy
}

# Patch NeMo CUDA graphs bug if present
python3 -c "
import glob, os
for f in glob.glob(os.path.dirname(__import__('nemo').__file__) + '/**/label_looping_base.py', recursive=True):
    txt = open(f).read()
    if 'self.cuda_graphs_enabled' in txt and 'if False  # patched' not in txt:
        txt = txt.replace('if self.cuda_graphs_enabled', 'if False  # patched: self.cuda_graphs_enabled')
        open(f, 'w').write(txt)
        print(f'Patched {f}')
" 2>/dev/null || true

# ── Auto-detect batch size ──
GPU_MEM=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -1 | tr -d ' ')
if [ "$GPU_MEM" -gt 60000 ]; then
    BATCH_SIZE=32; PRECISION="bf16-mixed"; ACCUMULATE=2
    echo "GPU >60GB → batch=32, bf16"
elif [ "$GPU_MEM" -gt 35000 ]; then
    BATCH_SIZE=16; PRECISION="bf16-mixed"; ACCUMULATE=4
    echo "GPU >35GB → batch=16, bf16"
elif [ "$GPU_MEM" -gt 20000 ]; then
    BATCH_SIZE=8; PRECISION="16-mixed"; ACCUMULATE=8
    echo "GPU >20GB → batch=8, fp16"
else
    BATCH_SIZE=4; PRECISION="32"; ACCUMULATE=16
    echo "GPU <=20GB → batch=4, fp32"
fi

LR=${LR:-"1e-5"}
EPOCHS=${EPOCHS:-"12"}
FREEZE_EPOCHS=${FREEZE_EPOCHS:-"3"}

# ============================================================
# STEP 1: Generate v4 contrastive data from ClArTTS
# ============================================================
echo ""
echo "============================================"
echo "[1/5] Generating v4 contrastive data..."
echo "============================================"

python3 training/generate_v4_contrastive.py \
    --clartts-only \
    --data-dir data/ \
    --max-clartts-pairs 2000 \
    --seed 42

echo "v4 contrastive data generated."
ls -lh data/contrastive_v4/contrastive_v4_manifest.json

# ============================================================
# STEP 2: Prepare v4 combined manifest
# ============================================================
echo ""
echo "============================================"
echo "[2/5] Preparing v4 combined manifest..."
echo "============================================"

INCLUDE_V3=${INCLUDE_V3:-"1"}
V4_PREPARE_ARGS="--data-dir data/"

if [ "$INCLUDE_V3" = "1" ] && [ -f "data/contrastive/contrastive_manifest.json" ]; then
    V4_PREPARE_ARGS="$V4_PREPARE_ARGS --include-v3-contrastive"
    echo "Including v3 contrastive pairs"
fi

# Check if MUSAN exists for noise augmentation
if [ ! -d "data/musan" ]; then
    V4_PREPARE_ARGS="$V4_PREPARE_ARGS --no-noise"
    echo "MUSAN not found, skipping noise augmentation"
fi

python3 training/prepare_v4.py $V4_PREPARE_ARGS

echo ""
echo "Combined manifest:"
wc -l data/train_v4_combined.json

# ============================================================
# STEP 3: Fine-tune from v3
# ============================================================
echo ""
echo "============================================"
echo "[3/5] Fine-tuning PCD v4 from v3..."
echo "  LR=$LR, Epochs=$EPOCHS, Freeze=$FREEZE_EPOCHS"
echo "  Batch=$BATCH_SIZE x $ACCUMULATE (grad accum)"
echo "============================================"

mkdir -p checkpoints/v4/

python3 training/finetune_pcd.py \
    --from-nemo "$V3_MODEL" \
    --train-manifest data/train_v4_combined.json \
    --output-dir checkpoints/v4/ \
    --epochs "$EPOCHS" \
    --batch-size "$BATCH_SIZE" \
    --precision "$PRECISION" \
    --accumulate-grad "$ACCUMULATE" \
    --lr "$LR" \
    --warmup-steps 100 \
    --freeze-encoder-epochs "$FREEZE_EPOCHS"

echo ""
echo "Training complete!"
ls -lh checkpoints/v4/

# ============================================================
# STEP 4: Evaluate v4 model
# ============================================================
echo ""
echo "============================================"
echo "[4/5] Evaluating v4 model on ClArTTS..."
echo "============================================"

# Find best checkpoint or final model
V4_MODEL="checkpoints/v4/pcd_clartts_final.nemo"
if [ ! -f "$V4_MODEL" ]; then
    V4_MODEL=$(ls -t checkpoints/v4/*.nemo 2>/dev/null | head -1)
fi

if [ -z "$V4_MODEL" ] || [ ! -f "$V4_MODEL" ]; then
    echo "WARNING: No v4 .nemo model found, skipping evaluation"
else
    python3 training/evaluate.py \
        --model "$V4_MODEL" \
        --data-dir data/ \
        --decoder ctc

    echo ""
    echo "Evaluation complete."
fi

# ============================================================
# STEP 5: Copy model for download
# ============================================================
echo ""
echo "============================================"
echo "[5/5] Exporting v4 model..."
echo "============================================"

mkdir -p models/
if [ -f "$V4_MODEL" ]; then
    cp "$V4_MODEL" models/pcd_clartts_v4.nemo
    echo "Model exported to: models/pcd_clartts_v4.nemo"
    ls -lh models/pcd_clartts_v4.nemo
fi

echo ""
echo "========================================"
echo "  v4 Pipeline Complete!"
echo "========================================"
echo ""
echo "To download to your Mac:"
echo "  scp <server>:~/i3rab/models/pcd_clartts_v4.nemo models/"
echo ""
echo "To test locally:"
echo "  python run_tests_pcd.py --model models/pcd_clartts_v4.nemo --tashkeel-on --verbose"
echo "  python eval_recall.py --tashkeel-on --exclude-final --max-samples 200"
