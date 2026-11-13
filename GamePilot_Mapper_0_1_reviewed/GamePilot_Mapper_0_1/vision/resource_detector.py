from pathlib import Path
import cv2
import numpy as np


class ResourceDetector:
    """Experimental multi-scale template detector. Results are visual candidates only."""
    def __init__(self, template_path: Path):
        raw = cv2.imread(str(template_path), cv2.IMREAD_UNCHANGED)
        if raw is None or raw.size == 0:
            raise FileNotFoundError(f"Не удалось загрузить шаблон: {template_path}")
        if raw.ndim == 2:
            self.template = cv2.cvtColor(raw, cv2.COLOR_GRAY2BGR)
            self.mask = None
        elif raw.shape[2] == 4:
            self.template = raw[:, :, :3]
            alpha = raw[:, :, 3]
            self.mask = alpha if np.any(alpha) else None
        else:
            self.template = raw[:, :, :3]
            self.mask = None
        if min(self.template.shape[:2]) < 8:
            raise ValueError("Шаблон слишком мал для надёжного поиска")

    @staticmethod
    def _iou(a, b):
        _, ax, ay, aw, ah = a
        _, bx, by, bw, bh = b
        x1, y1 = max(ax, bx), max(ay, by)
        x2, y2 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
        inter = max(0, x2 - x1) * max(0, y2 - y1)
        union = aw * ah + bw * bh - inter
        return inter / union if union else 0.0

    def detect(self, frame_bgr, threshold=0.78, scales=None, max_hits=30):
        if frame_bgr is None or not isinstance(frame_bgr, np.ndarray) or frame_bgr.size == 0:
            return []
        if frame_bgr.ndim == 2:
            frame_bgr = cv2.cvtColor(frame_bgr, cv2.COLOR_GRAY2BGR)
        if frame_bgr.ndim != 3 or frame_bgr.shape[2] < 3:
            raise ValueError("Ожидается изображение BGR или grayscale")
        threshold = float(np.clip(threshold, 0.0, 1.0))
        h0, w0 = self.template.shape[:2]
        scales = scales or np.linspace(0.55, 1.65, 12)
        hits = []
        for scale in scales:
            w, h = int(round(w0 * float(scale))), int(round(h0 * float(scale)))
            if w < 8 or h < 8 or h > frame_bgr.shape[0] or w > frame_bgr.shape[1]:
                continue
            interp = cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC
            templ = cv2.resize(self.template, (w, h), interpolation=interp)
            mask = cv2.resize(self.mask, (w, h), interpolation=cv2.INTER_NEAREST) if self.mask is not None else None
            try:
                result = cv2.matchTemplate(frame_bgr[:, :, :3], templ, cv2.TM_CCORR_NORMED, mask=mask)
            except cv2.error:
                # Masked CCORR is not supported by every OpenCV build.
                result = cv2.matchTemplate(frame_bgr[:, :, :3], templ, cv2.TM_CCOEFF_NORMED)
            result = np.nan_to_num(result, nan=-1.0, posinf=-1.0, neginf=-1.0)
            ys, xs = np.where(result >= threshold)
            # Keep only local maxima to avoid collecting every pixel in one response plateau.
            for x, y in zip(xs.tolist(), ys.tolist()):
                score = float(result[y, x])
                x0, x1 = max(0, x - 2), min(result.shape[1], x + 3)
                y0, y1 = max(0, y - 2), min(result.shape[0], y + 3)
                if score >= float(result[y0:y1, x0:x1].max()):
                    hits.append((score, int(x), int(y), w, h))
        hits.sort(key=lambda item: item[0], reverse=True)
        kept = []
        for hit in hits:
            if all(self._iou(hit, old) < 0.35 for old in kept):
                kept.append(hit)
                if len(kept) >= max(1, int(max_hits)):
                    break
        return kept
