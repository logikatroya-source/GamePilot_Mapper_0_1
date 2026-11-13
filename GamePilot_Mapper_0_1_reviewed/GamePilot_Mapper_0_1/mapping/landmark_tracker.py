import cv2
import numpy as np


class LandmarkTracker:
    """Experimental frame-to-frame visual odometry; not calibrated world-coordinate SLAM."""
    def __init__(self):
        self.prev_gray = None
        self.total_dx = 0.0
        self.total_dy = 0.0

    def update(self, frame_bgr):
        if frame_bgr is None or not isinstance(frame_bgr, np.ndarray) or frame_bgr.size == 0:
            return {"dx": 0.0, "dy": 0.0, "matches": 0, "tracked": False,
                    "total_dx": self.total_dx, "total_dy": self.total_dy}
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY) if frame_bgr.ndim == 3 else frame_bgr
        result = {"dx": 0.0, "dy": 0.0, "matches": 0, "tracked": False}
        if self.prev_gray is not None and self.prev_gray.shape == gray.shape:
            p0 = cv2.goodFeaturesToTrack(self.prev_gray, maxCorners=500, qualityLevel=0.01,
                                         minDistance=8, blockSize=7)
            if p0 is not None and len(p0) >= 8:
                p1, status, _ = cv2.calcOpticalFlowPyrLK(
                    self.prev_gray, gray, p0, None,
                    winSize=(21, 21), maxLevel=3,
                    criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01))
                if p1 is not None and status is not None:
                    valid = status.ravel() == 1
                    old = p0[valid].reshape(-1, 2)
                    new = p1[valid].reshape(-1, 2)
                    if len(old) >= 8:
                        matrix, inliers = cv2.estimateAffinePartial2D(
                            old, new, method=cv2.RANSAC, ransacReprojThreshold=3.0)
                        if matrix is not None:
                            dx, dy = float(matrix[0, 2]), float(matrix[1, 2])
                            count = int(inliers.sum()) if inliers is not None else len(old)
                            if count >= 6 and np.isfinite([dx, dy]).all():
                                self.total_dx += dx
                                self.total_dy += dy
                                result = {"dx": dx, "dy": dy, "matches": count, "tracked": True}
        self.prev_gray = gray.copy()
        result["total_dx"] = self.total_dx
        result["total_dy"] = self.total_dy
        return result

    def reset(self):
        self.prev_gray = None
        self.total_dx = self.total_dy = 0.0
