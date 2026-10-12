"""Threaded tracker and camera-failure handling, using fake/synthetic sources."""

import time

from src.vision import (HSVRange, SyntheticSource, TrackerStatus, VisionSettings, VisionTracker,
                        make_source_factory)


def wait_for(tracker, predicate, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        state = tracker.snapshot()
        if predicate(state):
            return state
        time.sleep(0.02)
    return tracker.snapshot()


class ClosedCamera:
    def isOpened(self):
        return False

    def release(self):
        pass


class DyingCamera:
    """Opens fine, then every read fails (unplugged / permission revoked)."""

    def isOpened(self):
        return True

    def read(self):
        return False, None

    def release(self):
        pass


def test_no_camera_reports_status_without_crashing():
    t = VisionTracker(VisionSettings(), source_factory=lambda: None)
    t.start()
    s = wait_for(t, lambda s: s.status == TrackerStatus.NO_CAMERA)
    assert s.status == TrackerStatus.NO_CAMERA and s.position is None
    t.stop()
    assert t.snapshot().status == TrackerStatus.OFF


def test_closed_camera_reports_no_camera():
    t = VisionTracker(VisionSettings(), source_factory=ClosedCamera)
    t.start()
    assert wait_for(t, lambda s: s.status == TrackerStatus.NO_CAMERA).status == TrackerStatus.NO_CAMERA
    t.stop()


def test_camera_exception_reports_error():
    def boom():
        raise RuntimeError("driver exploded")
    t = VisionTracker(VisionSettings(), source_factory=boom)
    t.start()
    s = wait_for(t, lambda s: s.status == TrackerStatus.ERROR)
    assert s.status == TrackerStatus.ERROR and "driver exploded" in s.message
    t.stop()


def test_read_failures_end_in_error():
    t = VisionTracker(VisionSettings(), source_factory=DyingCamera)
    t.start()
    assert wait_for(t, lambda s: s.status == TrackerStatus.ERROR).status == TrackerStatus.ERROR
    t.stop()


def test_missing_video_file_is_handled():
    t = VisionTracker(VisionSettings(), source_factory=make_source_factory("does_not_exist.mp4"))
    t.start()
    assert wait_for(t, lambda s: s.status == TrackerStatus.NO_CAMERA).status == TrackerStatus.NO_CAMERA
    t.stop()


def test_synthetic_source_is_tracked_by_thread():
    t = VisionTracker(VisionSettings(hsv_range=HSVRange.preset("green"), extras=True),
                      source_factory=lambda: SyntheticSource(realtime=True))
    t.start()
    s = wait_for(t, lambda s: s.status == TrackerStatus.TRACKING and s.frame_id > 5)
    assert s.status == TrackerStatus.TRACKING
    assert s.position is not None and 0 <= s.position[0] <= 1
    assert s.result.edges is not None
    t.stop()


def test_wrong_preset_means_searching_and_sampling_recovers():
    t = VisionTracker(VisionSettings(hsv_range=HSVRange.preset("pink")),  # nothing pink in scene
                      source_factory=lambda: SyntheticSource(realtime=True))
    t.start()
    assert wait_for(t, lambda s: s.status == TrackerStatus.SEARCHING).status == TrackerStatus.SEARCHING
    # move the synthetic disc under the centre sampling box, then calibrate from it
    t.stop()
    src = SyntheticSource(realtime=True)
    src.position = lambda i: (0.5, 0.5)
    t.source_factory = lambda: src
    t.start()
    wait_for(t, lambda s: s.frame_id > 2)
    t.request_sample()
    s = wait_for(t, lambda s: s.status == TrackerStatus.TRACKING)
    assert s.status == TrackerStatus.TRACKING
    assert t.settings.hsv_range.name == "sampled"
    t.stop()
