"""Pose estimation interfaces and implementations."""
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import abc
import math
from pathlib import Path

import numpy as np

from app.models import Keypoint, PoseSummary
from app.utils.logging import get_logger

logger = get_logger(__name__)

# MoveNet keypoint indices
KEYPOINT_NAMES = [
    "nose", "left_eye", "right_eye", "left_ear", "right_ear",
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_hip", "right_hip",
    "left_knee", "right_knee", "left_ankle", "right_ankle",
]


class PoseEstimator(abc.ABC):
    """Abstract interface for pose estimation backends."""

    @abc.abstractmethod
    async def initialize(self) -> None:
        """Load model and prepare for inference."""

    @abc.abstractmethod
    async def estimate_pose(self, frame: np.ndarray) -> PoseSummary | None:
        """Estimate pose from a video frame. Returns None if no person detected."""

    @abc.abstractmethod
    def is_ready(self) -> bool:
        """Check if the estimator is loaded and ready."""


class MoveNetEstimator(PoseEstimator):
    """MoveNet Lightning/Thunder TFLite pose estimator."""

    MODEL_URLS = {
        "movenet_lightning": "https://tfhub.dev/google/lite-model/movenet/singlepose/lightning/tflite/int8/4?lite-format=tflite",
        "movenet_thunder": "https://tfhub.dev/google/lite-model/movenet/singlepose/thunder/tflite/int8/4?lite-format=tflite",
    }

    INPUT_SIZES = {
        "movenet_lightning": 192,
        "movenet_thunder": 256,
    }

    def __init__(self, model_variant: str = "movenet_lightning", model_dir: str = "/data/models"):
        self._model_variant = model_variant
        self._model_dir = Path(model_dir)
        self._interpreter = None  # Will be tflite.Interpreter
        self._input_size = self.INPUT_SIZES.get(model_variant, 192)
        self._ready = False

    async def initialize(self) -> None:
        """Load the TFLite model, downloading from TF Hub if necessary."""
        self._model_dir.mkdir(parents=True, exist_ok=True)
        model_path = self._model_dir / f"{self._model_variant}.tflite"

        if not model_path.exists():
            await self._download_model(model_path)

        if not model_path.exists():
            logger.warning(
                "model_not_found",
                path=str(model_path),
                message="Model file not found after download attempt. Using fallback.",
            )
            self._ready = False
            return

        try:
            import tflite_runtime.interpreter as tflite
            self._interpreter = tflite.Interpreter(model_path=str(model_path))
            self._interpreter.allocate_tensors()
            self._ready = True
            logger.info("pose_model_loaded", variant=self._model_variant, input_size=self._input_size)
        except Exception:
            logger.exception("pose_model_load_failed", variant=self._model_variant)
            self._ready = False

    async def _download_model(self, model_path: Path) -> None:
        """Download TFLite model from TF Hub."""
        url = self.MODEL_URLS.get(self._model_variant)
        if not url:
            logger.error("unknown_model_variant", variant=self._model_variant)
            return

        logger.info("downloading_model", variant=self._model_variant, url=url)
        try:
            import httpx

            async with httpx.AsyncClient(follow_redirects=True, timeout=120.0) as client:
                response = await client.get(url)
                if response.status_code == 200:
                    model_path.write_bytes(response.content)
                    logger.info(
                        "model_downloaded",
                        variant=self._model_variant,
                        size_mb=round(len(response.content) / 1024 / 1024, 1),
                    )
                else:
                    logger.error("model_download_failed", status=response.status_code)
        except Exception:
            logger.exception("model_download_error", variant=self._model_variant)

    async def estimate_pose(self, frame: np.ndarray) -> PoseSummary | None:
        """Run MoveNet inference on a frame."""
        if not self._ready or self._interpreter is None:
            return self._fallback_estimate(frame)

        try:
            import cv2

            # Resize frame to model input size
            input_image = cv2.resize(frame, (self._input_size, self._input_size))
            input_image = np.expand_dims(input_image, axis=0).astype(np.int32)

            # Run inference
            input_details = self._interpreter.get_input_details()
            output_details = self._interpreter.get_output_details()
            self._interpreter.set_tensor(input_details[0]["index"], input_image)
            self._interpreter.invoke()

            # Parse keypoints: shape [1, 1, 17, 3] -> y, x, confidence
            keypoints_raw = self._interpreter.get_tensor(output_details[0]["index"])
            keypoints_data = keypoints_raw[0][0]  # [17, 3]

            keypoints = []
            for i, name in enumerate(KEYPOINT_NAMES):
                y, x, conf = keypoints_data[i]
                keypoints.append(Keypoint(name=name, x=float(x), y=float(y), confidence=float(conf)))

            return self._build_pose_summary(keypoints)

        except Exception:
            logger.exception("pose_estimation_failed")
            return self._fallback_estimate(frame)

    def is_ready(self) -> bool:
        return self._ready

    def _build_pose_summary(self, keypoints: list[Keypoint]) -> PoseSummary:
        """Compute derived metrics from keypoints."""
        avg_confidence = sum(k.confidence for k in keypoints) / len(keypoints) if keypoints else 0.0

        # Calculate torso angle from shoulders and hips
        torso_angle = self._calculate_torso_angle(keypoints)
        is_upright = torso_angle is not None and abs(torso_angle) > 45
        is_prone = torso_angle is not None and abs(torso_angle) < 30

        # Body aspect ratio from bounding box of keypoints
        valid_kps = [k for k in keypoints if k.confidence > 0.3]
        aspect_ratio = None
        if len(valid_kps) >= 4:
            xs = [k.x for k in valid_kps]
            ys = [k.y for k in valid_kps]
            width = max(xs) - min(xs)
            height = max(ys) - min(ys)
            if width > 0.01:
                aspect_ratio = height / width

        return PoseSummary(
            keypoints=keypoints,
            torso_angle=torso_angle,
            is_upright=is_upright,
            is_prone=is_prone,
            body_aspect_ratio=aspect_ratio,
            pose_confidence=avg_confidence,
        )

    @staticmethod
    def _calculate_torso_angle(keypoints: list[Keypoint]) -> float | None:
        """Calculate torso angle from vertical (90=standing, 0=lying flat)."""
        kp_map = {k.name: k for k in keypoints}

        # Use shoulders and hips midpoints
        ls = kp_map.get("left_shoulder")
        rs = kp_map.get("right_shoulder")
        lh = kp_map.get("left_hip")
        rh = kp_map.get("right_hip")

        if not all(k and k.confidence > 0.2 for k in [ls, rs, lh, rh]):
            return None

        shoulder_mid_x = (ls.x + rs.x) / 2
        shoulder_mid_y = (ls.y + rs.y) / 2
        hip_mid_x = (lh.x + rh.x) / 2
        hip_mid_y = (lh.y + rh.y) / 2

        dx = shoulder_mid_x - hip_mid_x
        dy = shoulder_mid_y - hip_mid_y

        # Angle from horizontal (0 = horizontal/lying, 90 = vertical/standing)
        if abs(dx) < 1e-6 and abs(dy) < 1e-6:
            return None

        angle_from_horizontal = abs(math.degrees(math.atan2(abs(dy), abs(dx))))
        return angle_from_horizontal

    @staticmethod
    def _fallback_estimate(frame: np.ndarray) -> PoseSummary | None:
        """Fallback when model is unavailable: use basic aspect ratio heuristics."""
        if frame is None or frame.size == 0:
            return None
        h, w = frame.shape[:2]
        if w == 0:
            return None
        aspect_ratio = h / w
        return PoseSummary(
            body_aspect_ratio=aspect_ratio,
            pose_confidence=0.1,  # Low confidence for fallback
        )


class YoloPoseEstimator(PoseEstimator):
    """YOLO-Pose estimator using PyTorch with GPU acceleration (ROCm/CUDA).

    Performs person detection + keypoint estimation in a single pass.
    Supports AMD ROCm and NVIDIA CUDA GPUs via PyTorch.
    Falls back to CPU if no GPU is available.
    """

    # YOLO-Pose uses COCO keypoint order (same 17 keypoints as MoveNet)
    YOLO_KEYPOINT_NAMES = [
        "nose", "left_eye", "right_eye", "left_ear", "right_ear",
        "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
        "left_wrist", "right_wrist", "left_hip", "right_hip",
        "left_knee", "right_knee", "left_ankle", "right_ankle",
    ]

    MODEL_VARIANTS = {
        "yolo_pose_nano": "yolo11n-pose.pt",
        "yolo_pose_small": "yolo11s-pose.pt",
        "yolo_pose_medium": "yolo11m-pose.pt",
    }

    def __init__(
        self,
        model_variant: str = "yolo_pose_nano",
        model_dir: str = "/data/models",
        device: str = "auto",
    ):
        self._model_variant = model_variant
        self._model_dir = Path(model_dir)
        self._model = None
        self._device = device
        self._ready = False
        self._gpu_name: str | None = None

    async def initialize(self) -> None:
        """Load YOLO-Pose model and select device."""
        self._model_dir.mkdir(parents=True, exist_ok=True)

        try:
            import torch
            from ultralytics import YOLO

            # Resolve device
            if self._device == "auto":
                if torch.cuda.is_available():
                    self._device = "cuda:0"
                    self._gpu_name = torch.cuda.get_device_name(0)
                else:
                    self._device = "cpu"
                    self._gpu_name = None

            # Determine model filename
            model_file = self.MODEL_VARIANTS.get(
                self._model_variant, "yolo11n-pose.pt"
            )
            model_path = self._model_dir / model_file

            # YOLO auto-downloads if not present
            self._model = YOLO(str(model_path) if model_path.exists() else model_file)

            # Warm up the model on the target device
            dummy = np.zeros((192, 192, 3), dtype=np.uint8)
            self._model(dummy, device=self._device, verbose=False)

            self._ready = True
            logger.info(
                "yolo_pose_model_loaded",
                variant=self._model_variant,
                device=self._device,
                gpu=self._gpu_name or "cpu",
            )
        except Exception:
            logger.exception("yolo_pose_load_failed", variant=self._model_variant)
            self._ready = False

    async def estimate_pose(self, frame: np.ndarray) -> PoseSummary | None:
        """Run YOLO-Pose inference (person detection + keypoints in one pass)."""
        if not self._ready or self._model is None:
            return self._fallback_estimate(frame)

        try:
            results = self._model(
                frame,
                device=self._device,
                verbose=False,
                conf=0.3,
            )

            if not results or len(results) == 0:
                return None

            r = results[0]

            # No persons detected
            if r.keypoints is None or len(r.boxes) == 0:
                return None

            # Use the highest-confidence person detection
            best_idx = int(r.boxes.conf.argmax())
            person_conf = float(r.boxes.conf[best_idx])
            kp_data = r.keypoints.data[best_idx].cpu().numpy()  # [17, 3]

            keypoints = []
            for i, name in enumerate(self.YOLO_KEYPOINT_NAMES):
                x, y, conf = kp_data[i]
                # YOLO outputs pixel coords; normalize to [0, 1]
                h, w = frame.shape[:2]
                keypoints.append(Keypoint(
                    name=name,
                    x=float(x / w) if w > 0 else 0.0,
                    y=float(y / h) if h > 0 else 0.0,
                    confidence=float(conf),
                ))

            return self._build_pose_summary(keypoints, person_conf)

        except Exception:
            logger.exception("yolo_pose_estimation_failed")
            return self._fallback_estimate(frame)

    def is_ready(self) -> bool:
        return self._ready

    def _build_pose_summary(
        self, keypoints: list[Keypoint], person_confidence: float = 0.0
    ) -> PoseSummary:
        """Compute derived metrics from YOLO keypoints."""
        avg_kp_conf = (
            sum(k.confidence for k in keypoints) / len(keypoints)
            if keypoints
            else 0.0
        )

        torso_angle = MoveNetEstimator._calculate_torso_angle(keypoints)
        is_upright = torso_angle is not None and abs(torso_angle) > 45
        is_prone = torso_angle is not None and abs(torso_angle) < 30

        valid_kps = [k for k in keypoints if k.confidence > 0.3]
        aspect_ratio = None
        if len(valid_kps) >= 4:
            xs = [k.x for k in valid_kps]
            ys = [k.y for k in valid_kps]
            width = max(xs) - min(xs)
            height = max(ys) - min(ys)
            if width > 0.01:
                aspect_ratio = height / width

        return PoseSummary(
            keypoints=keypoints,
            torso_angle=torso_angle,
            is_upright=is_upright,
            is_prone=is_prone,
            body_aspect_ratio=aspect_ratio,
            pose_confidence=max(avg_kp_conf, person_confidence),
        )

    @staticmethod
    def _fallback_estimate(frame: np.ndarray) -> PoseSummary | None:
        """Fallback when model is unavailable."""
        return MoveNetEstimator._fallback_estimate(frame)
