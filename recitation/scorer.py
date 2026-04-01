"""MixGoP scorer: GMM-based diacritic scoring on frozen SSL hidden states.

Fits per-diacritic Gaussian Mixture Models on concatenated hidden states
from transformer layers 14/16/18 (3072-dim for XLS-R 300M with 1024 hidden).

Based on MixGoP approach (NAACL 2025): intermediate SSL layers contain
richer phonetic information than the final output layer.
"""

import pickle
import json
import numpy as np
from pathlib import Path

from arabic import FATHA, DAMMA, KASRA, FATHATAN, DAMMATAN, KASRATAN, SUKOON, HARAKAT, SHADDA

# Layers to extract (0-indexed from hidden_states tuple, where 0=embedding)
MIX_LAYERS = [14, 16, 18]

# Diacritic groups for comparison
_SHORT_VOWELS = frozenset({FATHA, DAMMA, KASRA})
_TANWEEN = frozenset({FATHATAN, DAMMATAN, KASRATAN})
_ALL_DIACS = _SHORT_VOWELS | _TANWEEN

_DIAC_NAMES = {
    FATHA: "fatha", DAMMA: "damma", KASRA: "kasra",
    FATHATAN: "fathatan", DAMMATAN: "dammatan", KASRATAN: "kasratan",
}


class MixGoPScorer:
    """Per-diacritic GMM scorer using mixed SSL layer features."""

    def __init__(self, gmm_dir=None):
        self.gmms = {}       # diac_char -> fitted GMM
        self.config = {}
        if gmm_dir is not None:
            self.load(gmm_dir)

    @staticmethod
    def extract_feature(hidden_states, frame_idx, context=1):
        """Extract concatenated features from MIX_LAYERS at given frame(s).

        Args:
            hidden_states: tuple of (T, H) tensors, one per layer
            frame_idx: int or (start, end) for a range of frames
            context: number of context frames on each side

        Returns:
            numpy array of shape (D,) where D = len(MIX_LAYERS) * H
        """
        if isinstance(frame_idx, tuple):
            sf, ef = frame_idx
            center = (sf + ef) // 2
        else:
            center = frame_idx

        T = hidden_states[0].shape[0]
        frames = list(range(max(0, center - context), min(T, center + context + 1)))
        if not frames:
            return None

        # Weighted average: center gets 1.0, context gets 0.5
        weights = np.array([1.0 if f == center else 0.5 for f in frames])
        weights /= weights.sum()

        parts = []
        for layer_idx in MIX_LAYERS:
            if layer_idx >= len(hidden_states):
                continue
            layer = hidden_states[layer_idx]  # (T, H) tensor
            layer_np = layer[frames].numpy() if hasattr(layer, 'numpy') else np.array(layer[frames])
            avg = (layer_np * weights[:, None]).sum(axis=0)
            parts.append(avg)

        if not parts:
            return None
        return np.concatenate(parts).astype(np.float32)

    def fit(self, features_by_diac, n_components=4):
        """Fit GMMs from collected features.

        Args:
            features_by_diac: dict {diac_char: np.array of shape (N, D)}
            n_components: number of GMM components
        """
        from sklearn.mixture import GaussianMixture

        self.gmms = {}
        self.config = {
            "layers": MIX_LAYERS,
            "n_components": n_components,
            "diacritics": {},
        }

        for diac, feats in features_by_diac.items():
            if len(feats) < n_components * 2:
                print(f"  Skipping {_DIAC_NAMES.get(diac, diac)}: only {len(feats)} samples")
                continue

            n_comp = min(n_components, len(feats) // 2)
            gmm = GaussianMixture(
                n_components=n_comp,
                covariance_type="diag",
                max_iter=200,
                random_state=42,
            )
            gmm.fit(feats)
            self.gmms[diac] = gmm
            self.config["diacritics"][_DIAC_NAMES.get(diac, diac)] = {
                "n_samples": len(feats),
                "n_components": n_comp,
                "dim": feats.shape[1],
            }
            print(f"  Fitted {_DIAC_NAMES.get(diac, diac)}: {len(feats)} samples, "
                  f"{n_comp} components, dim={feats.shape[1]}")

    def score_diacritic(self, feature, diac_char):
        """Score a feature vector under a specific diacritic's GMM.

        Returns log-likelihood (float) or None if GMM not available.
        """
        gmm = self.gmms.get(diac_char)
        if gmm is None:
            return None
        return float(gmm.score_samples(feature.reshape(1, -1))[0])

    def score_all_alternatives(self, feature, diac_char):
        """Score feature under expected diac and all alternatives in its group.

        Returns dict with margin and best alternative info.
        """
        if diac_char in _SHORT_VOWELS:
            group = _SHORT_VOWELS
        elif diac_char in _TANWEEN:
            group = _TANWEEN
        else:
            return None

        expected_ll = self.score_diacritic(feature, diac_char)
        if expected_ll is None:
            return None

        best_alt_ll = -1e9
        best_alt_char = None
        for alt in group:
            if alt == diac_char:
                continue
            alt_ll = self.score_diacritic(feature, alt)
            if alt_ll is not None and alt_ll > best_alt_ll:
                best_alt_ll = alt_ll
                best_alt_char = alt

        if best_alt_char is None:
            return None

        return {
            "expected_ll": expected_ll,
            "best_alt_ll": best_alt_ll,
            "best_alt_char": best_alt_char,
            "margin": expected_ll - best_alt_ll,
        }

    def save(self, gmm_dir):
        """Save GMMs and config to directory."""
        gmm_dir = Path(gmm_dir)
        gmm_dir.mkdir(parents=True, exist_ok=True)

        with open(gmm_dir / "gmms.pkl", "wb") as f:
            pickle.dump(self.gmms, f)
        with open(gmm_dir / "config.json", "w") as f:
            json.dump(self.config, f, indent=2)

    def load(self, gmm_dir):
        """Load GMMs and config from directory."""
        gmm_dir = Path(gmm_dir)
        with open(gmm_dir / "gmms.pkl", "rb") as f:
            self.gmms = pickle.load(f)
        with open(gmm_dir / "config.json") as f:
            self.config = json.load(f)
