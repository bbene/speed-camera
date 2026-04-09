"""
Camera abstraction layer supporting multiple camera types
"""

import cv2
import logging
import time
from abc import ABC, abstractmethod


class CameraBase(ABC):
    """Abstract base class for camera inputs"""

    @abstractmethod
    def start(self):
        """Initialize and start the camera"""
        pass

    @abstractmethod
    def get_frame(self):
        """Get the next frame as a numpy array (BGR format)"""
        pass

    @abstractmethod
    def stop(self):
        """Stop the camera and cleanup resources"""
        pass

    @abstractmethod
    def get_resolution(self):
        """Get camera resolution as (width, height)"""
        pass


class PiCameraInput(CameraBase):
    """Raspberry Pi PiCamera input"""

    def __init__(self, resolution, framerate, vflip=False, hflip=False):
        self.resolution = resolution
        self.framerate = framerate
        self.vflip = vflip
        self.hflip = hflip
        self.camera = None
        self.capture = None

    def start(self):
        """Initialize PiCamera"""
        try:
            from picamera import PiCamera
            from picamera.array import PiRGBArray
        except ImportError:
            logging.error("picamera library not found. Install with: pip install picamera")
            raise RuntimeError("PiCamera not available. Are you running on Raspberry Pi?")

        logging.info("Initializing PiCamera")

        self.camera = PiCamera(resolution=self.resolution, framerate=self.framerate, sensor_mode=5)
        self.camera.vflip = self.vflip
        self.camera.hflip = self.hflip

        from picamera.array import PiRGBArray
        self.capture = PiRGBArray(self.camera, size=self.camera.resolution)

        # Allow camera to warm up
        time.sleep(2)

        # Create a generator for continuous capture
        self.frame_iterator = self.camera.capture_continuous(
            self.capture, format="bgr", use_video_port=True
        )

    def get_frame(self):
        """Get next frame from PiCamera"""
        if self.camera is None:
            raise RuntimeError("Camera not started. Call start() first.")

        frame = next(self.frame_iterator)
        image = frame.array

        # Clear the stream for the next frame
        self.capture.truncate(0)

        return image

    def stop(self):
        """Stop PiCamera"""
        if self.camera:
            self.camera.close()
            self.camera = None

    def get_resolution(self):
        """Get camera resolution"""
        return tuple(self.resolution)


class RTSPCameraInput(CameraBase):
    """RTSP (network) camera input using OpenCV"""

    def __init__(self, rtsp_url, username=None, password=None, timeout=10):
        self.rtsp_url = rtsp_url
        self.username = username
        self.password = password
        self.timeout = timeout
        self.cap = None
        self.width = None
        self.height = None

    def start(self):
        """Initialize RTSP connection"""
        logging.info(f"Connecting to RTSP stream: {self.rtsp_url}")

        # Build OpenCV-compatible URL with authentication if provided
        url = self.rtsp_url
        if self.username and self.password:
            # Insert credentials into RTSP URL
            # Format: rtsp://username:password@host/path
            url = self.rtsp_url.replace("rtsp://", f"rtsp://{self.username}:{self.password}@")

        # Open video capture
        self.cap = cv2.VideoCapture(url)

        if not self.cap.isOpened():
            logging.error(f"Failed to open RTSP stream: {url}")
            raise RuntimeError(f"Cannot connect to RTSP stream: {self.rtsp_url}")

        # Set read timeout
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        # Get resolution
        self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        logging.info(f"RTSP stream connected: {self.width}x{self.height}")

    def get_frame(self):
        """Get next frame from RTSP stream"""
        if self.cap is None:
            raise RuntimeError("Camera not started. Call start() first.")

        ret, frame = self.cap.read()

        if not ret:
            logging.error("Failed to read frame from RTSP stream")
            raise RuntimeError("RTSP stream disconnected or timeout")

        return frame

    def stop(self):
        """Stop RTSP stream"""
        if self.cap:
            self.cap.release()
            self.cap = None

    def get_resolution(self):
        """Get camera resolution"""
        if self.width is None or self.height is None:
            raise RuntimeError("Camera not started")
        return (self.width, self.height)


def create_camera(config):
    """
    Factory function to create appropriate camera input based on config

    Args:
        config: Config object with camera settings

    Returns:
        CameraBase: Appropriate camera implementation
    """
    camera_config = getattr(config, 'camera', {})

    # Default to PiCamera for backward compatibility
    camera_type = camera_config.get('type', 'picamera') if isinstance(camera_config, dict) else 'picamera'

    if camera_type == 'picamera':
        return PiCameraInput(
            resolution=config.resolution,
            framerate=config.fps,
            vflip=config.camera_vflip,
            hflip=config.camera_hflip
        )
    elif camera_type == 'rtsp':
        rtsp_url = camera_config.get('rtsp_url')
        if not rtsp_url:
            raise ValueError("RTSP camera type specified but rtsp_url not provided in config")

        return RTSPCameraInput(
            rtsp_url=rtsp_url,
            username=camera_config.get('username'),
            password=camera_config.get('password'),
            timeout=camera_config.get('timeout', 10)
        )
    else:
        raise ValueError(f"Unknown camera type: {camera_type}")
