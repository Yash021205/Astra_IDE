"""
Stages 2 & 3 — Random Forest workload classifier + ensemble of Isolation Forests
(paper §IV-B-2/3/4, Eq. 1).

- Stage 2: a supervised RandomForest (100 estimators) trained on the N normal
  workload classes. Outputs class probabilities + a decision.
- Stage 3: N Isolation Forests (100 estimators each), one per normal class,
  each trained on that class contaminated with 2.5% samples from other classes
  (Mix-2022 protocol). Eq. 1 anomaly score: s(x,n) = 2^(-E(h(x))/c(n)).
- Final decision (§IV-B-4):
    * all IF scores below threshold except the n-th -> class n
    * all below threshold                            -> anomaly
    * more than one above threshold                  -> anomaly

sklearn's IsolationForest implements Eq. 1 internally; `score_samples` returns
the negative of the normalized path-length score, so anomaly_score = -score_samples
recovers the paper's s(x,n) orientation (higher = more anomalous).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Sequence

try:
    import numpy as np
    from sklearn.ensemble import RandomForestClassifier, IsolationForest
    _SKLEARN = True
except ImportError:
    _SKLEARN = False


# Paper parameters
N_ESTIMATORS   = 100      # both RF and IF use 100 estimators
CONTAMINATION  = 0.025    # 2.5% (Mix-2022); Cui-2020 used 0.05


class Decision(str, Enum):
    NORMAL  = "NORMAL"     # matched exactly one class below threshold
    ANOMALY = "ANOMALY"


@dataclass
class IDSResult:
    decision:       Decision
    predicted_class: Optional[str]   # set when NORMAL
    class_scores:   Dict[str, float] # per-class anomaly score (higher = anomalous)
    rf_class:       Optional[str]    # Stage-2 RF top class


class ContainerIDS:
    """Three-stage graph-based IDS. Features are 15-dim anonymous-walk embeddings."""

    def __init__(self, n_estimators: int = N_ESTIMATORS,
                 contamination: float = CONTAMINATION, seed: int = 42):
        if not _SKLEARN:
            raise ImportError("scikit-learn required: pip install -r ml/requirements.txt")
        self.n_estimators = n_estimators
        self.contamination = contamination
        self.seed = seed
        self.classes_: List[str] = []
        self._rf: Optional[RandomForestClassifier] = None
        self._ifs: Dict[str, IsolationForest] = {}
        # anomaly-score threshold: IsolationForest.decision_function ~ 0 boundary,
        # so on the -score_samples scale the threshold tracks the trained offset.
        self._thresholds: Dict[str, float] = {}

    def fit(self, by_class: Dict[str, Sequence[Sequence[float]]]) -> "ContainerIDS":
        """
        Train on NORMAL data only (no labelled attacks), exactly as the paper:
          by_class = {class_name: list of 15-dim embedding vectors}
        """
        self.classes_ = sorted(by_class.keys())
        X, y = [], []
        for cls in self.classes_:
            for vec in by_class[cls]:
                X.append(list(vec)); y.append(cls)
        X = np.asarray(X, dtype=float)

        # Stage 2: supervised RF over normal classes (input = 15-dim embeddings)
        self._rf = RandomForestClassifier(
            n_estimators=self.n_estimators, random_state=self.seed)
        self._rf.fit(X, y)

        # Stage 3 (paper §IV-B-3): the IFs are trained on the RF's PROBABILITY
        # vectors — "the probabilities given by the second stage are imputed to
        # an ensemble of N IF modules" — NOT on the raw embeddings.
        proba_by_class: Dict[str, np.ndarray] = {}
        for cls in self.classes_:
            emb = np.asarray([list(v) for v in by_class[cls]], dtype=float)
            proba_by_class[cls] = self._rf.predict_proba(emb)

        rng = np.random.default_rng(self.seed)
        for cls in self.classes_:
            own = proba_by_class[cls]
            others = np.vstack([proba_by_class[c] for c in self.classes_ if c != cls])
            n_contam = max(1, int(len(own) * self.contamination))
            if len(others):
                idx = rng.choice(len(others), size=min(n_contam, len(others)), replace=False)
                train = np.vstack([own, others[idx]])
            else:
                train = own
            iforest = IsolationForest(
                n_estimators=self.n_estimators, contamination=self.contamination,
                random_state=self.seed)
            iforest.fit(train)
            self._ifs[cls] = iforest
            self._thresholds[cls] = 0.0   # decision_function > 0 => inlier
        return self

    def _anomaly_scores(self, vec: Sequence[float]) -> Dict[str, float]:
        """
        Eq. 1 oriented score per class (higher = more anomalous). The per-class
        IF scores the RF probability vector for this sample (paper §IV-B-3).
        """
        emb = np.asarray([list(vec)], dtype=float)
        proba = self._rf.predict_proba(emb)               # 2nd-stage probabilities
        # decision_function: positive = inlier; anomaly_score = -decision_function.
        return {cls: float(-self._ifs[cls].decision_function(proba)[0])
                for cls in self.classes_}

    def predict(self, vec: Sequence[float]) -> IDSResult:
        """
        §IV-B-4 decision rules. anomaly_score <= 0 means the per-class IF reports
        an inlier ("below threshold"). For a true class-n sample only IF_n should
        report inlier; all other IF_m see it as foreign (above threshold). Hence:
          * exactly one inlier  -> NORMAL, that class
          * zero inliers        -> ANOMALY (nothing recognizes it)
          * multiple inliers    -> ANOMALY (ambiguous)
        """
        if self._rf is None:
            raise RuntimeError("call fit() first")
        scores = self._anomaly_scores(vec)
        rf_class = str(self._rf.predict(np.asarray([list(vec)], dtype=float))[0])

        inliers = [c for c, s in scores.items() if s <= 0.0]
        if len(inliers) == 1:
            return IDSResult(Decision.NORMAL, inliers[0], scores, rf_class)
        return IDSResult(Decision.ANOMALY, None, scores, rf_class)
