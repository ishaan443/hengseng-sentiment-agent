"""Transparent multilingual baseline; optional frozen transformer adapter."""
from __future__ import annotations

import re
import numpy as np

POSITIVE = ("bullish", "growth", "beat", "upgrade", "profit", "strong", "rally",
            "看好", "利好", "盈利", "上升", "大升", "看涨", "看漲", "增長",
            "상승", "호재", "성장", "흑자", "매수", "급등")
NEGATIVE = ("bearish", "loss", "miss", "downgrade", "weak", "decline", "crash",
            "看淡", "利空", "虧損", "下跌", "大跌", "看跌", "亏损",
            "하락", "악재", "적자", "매도", "급락", "손실")


class LexiconScorer:
    metadata = {"backend": "lexicon-v1", "validated_for_finance": False,
                "note": "Small EN/ZH/KO demonstration lexicon; sarcasm and target attribution unresolved."}

    def score(self, texts):
        def one(text):
            text = re.sub(r"https?://\S+", "", text.casefold())
            pos = neg = 0
            for words, sign in ((POSITIVE, 1), (NEGATIVE, -1)):
                for word in words:
                    pattern = r"\b" + re.escape(word) + r"\b" if word.isascii() else re.escape(word)
                    for match in re.finditer(pattern, text):
                        local_sign = sign
                        if re.search(r"\b(?:not|no|never)\s+(?:\w+\s+){0,2}$", text[max(0, match.start()-24):match.start()]):
                            local_sign *= -1
                        pos += local_sign > 0
                        neg += local_sign < 0
            return float((pos-neg) / (pos+neg)) if pos+neg else 0.0
        return [one(t) for t in texts]


class TransformerScorer:
    def __init__(self, revision=None):
        import torch
        from transformers import AutoTokenizer, AutoModelForSequenceClassification
        self.torch = torch
        name = "cardiffnlp/twitter-xlm-roberta-base-sentiment"
        self.tokenizer = AutoTokenizer.from_pretrained(name, revision=revision, trust_remote_code=False)
        self.model = AutoModelForSequenceClassification.from_pretrained(
            name, revision=revision, trust_remote_code=False).eval()
        labels = {int(k): v.casefold() for k, v in self.model.config.id2label.items()}
        self.positive = next(k for k, v in labels.items() if v == "positive")
        self.negative = next(k for k, v in labels.items() if v == "negative")
        self.metadata = {"backend": name, "revision": self.model.config._commit_hash,
                         "validated_for_finance": False,
                         "note": "ZH/KO finance domain needs a human-labelled evaluation set."}

    def score(self, texts):
        output = []
        for start in range(0, len(texts), 16):
            batch = self.tokenizer(texts[start:start+16], return_tensors="pt", padding=True,
                                   truncation=True, max_length=256)
            with self.torch.inference_mode():
                probs = self.model(**batch).logits.softmax(dim=-1).cpu().numpy()
            output.extend((probs[:, self.positive]-probs[:, self.negative]).tolist())
        return output


def score_posts(posts, scorer):
    scores = scorer.score([p["text"] for p in posts])
    if len(scores) != len(posts) or not np.isfinite(scores).all():
        raise ValueError("Sentiment backend returned invalid scores")
    return [dict(p, sentiment=float(np.clip(s, -1, 1))) for p, s in zip(posts, scores)]
