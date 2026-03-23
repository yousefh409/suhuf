**Describe the bug**

The Arabic FastConformer PCD model ([`nvidia/stt_ar_fastconformer_hybrid_large_pcd_v1.0`](https://huggingface.co/nvidia/stt_ar_fastconformer_hybrid_large_pcd_v1.0)) does not produce diacritized output despite being the "PCD" (Punctuation, Capitalization, Diacritics) variant. The output is always undiacritized, identical in behavior to the PC model.

This contradicts the results in the paper ["Open Automatic Speech Recognition Models for Classical and Modern Standard Arabic"](https://arxiv.org/abs/2507.13977) (ICASSP 2025) which reports **1.55% WER_PC,D** on EveryAyah — proving a working PCD checkpoint exists internally.

**Steps/Code to reproduce bug**

```python
import nemo.collections.asr as nemo_asr

model = nemo_asr.models.EncDecHybridRNNTCTCBPEModel.from_pretrained(
    "nvidia/stt_ar_fastconformer_hybrid_large_pcd_v1.0"
)
model.change_decoding_strategy(decoder_type="ctc")

transcriptions = model.transcribe(["any_arabic_audio.wav"])
print(transcriptions[0])
# Output: undiacritized text (e.g., "قرأ الطالب الكتاب في المكتبة")
# Expected: diacritized text (e.g., "قَرَأَ الطَّالِبُ الكِتَابَ فِي المَكْتَبَةِ")
```

Same result with RNNT decoder (default).

**Expected behavior**

The PCD model should produce fully diacritized Arabic transcriptions with harakat (fatha, damma, kasra, shadda, sukun, tanwin) as reported in the paper (1.55% WER_PC,D on EveryAyah).

**Environment overview (please complete the following information)**

- Environment location: Bare-metal (macOS)
- Method of NeMo install: `pip install nemo_toolkit[asr]`

**Environment details**

- OS version: macOS 15 (Darwin 25.3.0)
- PyTorch version: 2.x
- Python version: 3.10
- NeMo version: tested with both 2.0.0 (model card version) and 2.7.0

**Additional context**

We performed extensive investigation into why this model does not produce diacritics:

**CTC logit analysis:** Diacritized tokens have near-zero probability (~0.0001) while undiacritized tokens dominate (~0.999+). The encoder does not encode diacritization information:

```
Token "فِي" (with kasra): probability 0.0001
Token "في" (without):     probability 0.9994
```

This pattern is consistent across all tokens in the vocabulary.

**PC vs PCD model comparison:**

| Property | PC model | PCD model (current) |
|----------|----------|---------------------|
| File size | 404.5 MB | 438.0 MB |
| Parameter count | 114,621,442 | 114,621,442 |
| Tokenizer hash | `980b4bb5...` | `43c84e71...` |
| Diacritics in tokenizer | No (outputs ⁇) | Yes (round-trips perfectly) |
| Encoder layers differ | — | All 641 layers differ from PC |
| **Produces diacritics** | **No** | **No** |

The models ARE different (different weights, different tokenizers, different sizes), but the PCD model still produces identical undiacritized output.

**Logit masking experiment:** We masked undiacritized tokens in CTC logits to force the model to pick diacritized alternatives. Partial diacritics appeared (e.g., "فِي" with kasra) but overall text was garbled — confirming the encoder representations don't carry diacritization information.

**Tested across multiple conditions:**
- NeMo 2.0.0 and 2.7.0 — same result
- Both RNNT and CTC decoders — same result
- TTS-generated MSA audio and Quranic TTS audio — same result
- Original commit `c5358b4` (404MB) and current commit (438MB) — same result

**HuggingFace discussions:** [Discussion #1](https://huggingface.co/nvidia/stt_ar_fastconformer_hybrid_large_pcd_v1.0/discussions/1) confirmed the PC checkpoint was accidentally uploaded instead of PCD. A fix was claimed, but the current model still does not produce diacritics. [Discussion #4](https://huggingface.co/nvidia/stt_ar_fastconformer_hybrid_large_pcd_v1.0/discussions/4) has multiple additional users reporting the same issue.

**Request:** Could the correct PCD checkpoint (the one that achieved 1.55% WER_PC,D in the paper) be re-uploaded to HuggingFace? The tokenizer is correct (handles diacritics perfectly), so only the model weights appear to be wrong.
