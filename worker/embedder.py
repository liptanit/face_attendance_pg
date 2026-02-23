from __future__ import annotations
import os
import numpy as np

class DummyEmbedder:
    dim = 512
    def detect_and_embed(self, bgr_image: np.ndarray):
        # No detection/recognition; returns nothing
        return []

class InsightFaceEmbedder:
    dim = 512
    def __init__(self):
        from insightface.app import FaceAnalysis
        self.app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
        self.app.prepare(ctx_id=0, det_size=(640, 640))

    def detect_and_embed(self, bgr_image: np.ndarray):
        faces = self.app.get(bgr_image)
        out = []
        for f in faces:
            x1,y1,x2,y2 = f.bbox
            area = max(1.0, (x2-x1)*(y2-y1))
            q = float(getattr(f, "det_score", 0.0)) * float(min(1.0, area / (200*200)))
            emb = f.normed_embedding.astype(np.float32)  # (512,)
            out.append({"bbox": [float(x1),float(y1),float(x2),float(y2)], "quality": q, "embedding": emb})
        return out

def make_embedder():
    name = os.getenv("EMBEDDER", "dummy").strip().lower()
    if name == "insightface":
        try:
            return InsightFaceEmbedder()
        except Exception as e:
            raise RuntimeError("Failed to init InsightFace embedder. Install: pip install insightface onnxruntime") from e
    return DummyEmbedder()
