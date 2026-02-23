import numpy as np

def embed_images_to_templates(image_paths: list[str]) -> tuple[list[list[float]], list[float]]:
    """
    Returns (embeddings, qualities).
    Requires `insightface` + `onnxruntime`.
    """
    try:
        from insightface.app import FaceAnalysis
    except Exception as e:
        raise RuntimeError(
            "InsightFace not installed. Install with: pip install insightface onnxruntime"
        ) from e

    import cv2

    app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
    # det_size can be tuned; 640 is a good start
    app.prepare(ctx_id=0, det_size=(640, 640))

    embeddings = []
    qualities = []

    for p in image_paths:
        img = cv2.imread(p)
        if img is None:
            continue
        faces = app.get(img)
        if not faces:
            continue
        # choose largest face
        f = max(faces, key=lambda x: (x.bbox[2]-x.bbox[0])*(x.bbox[3]-x.bbox[1]))
        emb = f.normed_embedding.astype(np.float32)  # (512,)
        # simple quality proxy: det_score + face area ratio
        x1,y1,x2,y2 = f.bbox
        area = max(1.0, (x2-x1)*(y2-y1))
        q = float(getattr(f, "det_score", 0.0)) * float(min(1.0, area / (200*200)))
        embeddings.append(emb.tolist())
        qualities.append(q)

    return embeddings, qualities
