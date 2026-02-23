from zoneinfo import ZoneInfo
from datetime import datetime
import numpy as np

def thai_date_from_utc(dt_utc: datetime, tz_name: str) -> "datetime.date":
    tz = ZoneInfo(tz_name)
    return dt_utc.astimezone(tz).date()

def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    # returns cosine similarity in [-1, 1]
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na == 0 or nb == 0:
        return -1.0
    return float(np.dot(a, b) / (na * nb))
