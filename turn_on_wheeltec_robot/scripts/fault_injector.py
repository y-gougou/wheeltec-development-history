#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Bridge Web fault-injection settings to the chassis serial protocol.

This node does not modify /cmd_vel.  It receives JSON configuration from the
Web UI, normalizes it into [enable, wheel_mask, alpha_a, alpha_b, alpha_c], and
publishes that array on /chassis/fault_config.  wheeltec_robot_node converts the
array into the 13-byte fault config frame consumed by the STM32 firmware.
"""

from __future__ import print_function

import json

import rospy
from std_msgs.msg import Float32MultiArray, String

from core.ros_params import get_bool, get_float, get_str

WHEEL_BITS = {"A": 0x01, "B": 0x02, "C": 0x04}
WHEELS = ("A", "B", "C")


def clamp_alpha(value):
    try:
        alpha = float(value)
    except (TypeError, ValueError):
        return 1.0
    return max(0.0, min(1.0, alpha))


def boolish(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in ("1", "true", "yes", "on")


class FaultInjector(object):
    def __init__(self):
        self.enable_fault = get_bool("~enable_fault", False)
        self.fault_type = get_str("~fault_type", "normal")
        self.fault_wheel = get_str("~fault_wheel", "B").upper()
        initial_alpha = clamp_alpha(get_float("~fault_alpha", 0.5))
        self.alpha = {"A": 1.0, "B": initial_alpha, "C": 1.0}
        self.wheels = {"A": False, "B": self.fault_wheel == "B", "C": False}
        if self.fault_wheel in WHEEL_BITS:
            self.wheels[self.fault_wheel] = True

        self.config_topic = get_str("~config_topic", "/web/fault_injection_config")
        self.status_topic = get_str("~status_topic", "/web/fault_injection_status")
        self.output_topic = get_str("~output_topic", "/chassis/fault_config")

        self._pub = rospy.Publisher(self.output_topic, Float32MultiArray, queue_size=1, latch=True)
        self._status_pub = rospy.Publisher(self.status_topic, String, queue_size=1, latch=True)
        rospy.Subscriber(self.config_topic, String, self._config_callback, queue_size=1)

        self._publish_config()
        rospy.loginfo(
            "fault_config_bridge started: enable_fault=%s, fault_type=%s, mask=0x%02X, "
            "alpha_a=%.3f, alpha_b=%.3f, alpha_c=%.3f",
            self.enable_fault,
            self.fault_type,
            self._wheel_mask(),
            self.alpha["A"],
            self.alpha["B"],
            self.alpha["C"],
        )

    def _wheel_mask(self):
        if not self.enable_fault or self.fault_type != "drive_abnormal":
            return 0
        mask = 0
        for wheel in WHEELS:
            if self.wheels.get(wheel, False):
                mask |= WHEEL_BITS[wheel]
        return mask

    def _fault_wheel_label(self):
        enabled = [wheel for wheel in WHEELS if self.wheels.get(wheel, False)]
        return "+".join(enabled) if enabled else "none"

    def _active_alpha_label(self):
        enabled = [self.alpha[wheel] for wheel in WHEELS if self.wheels.get(wheel, False)]
        if not enabled:
            return 1.0
        if len(enabled) == 1:
            return enabled[0]
        return min(enabled)

    def _publish_config(self):
        msg = Float32MultiArray()
        msg.data = [
            1.0 if self.enable_fault and self.fault_type == "drive_abnormal" else 0.0,
            float(self._wheel_mask()),
            self.alpha["A"],
            self.alpha["B"],
            self.alpha["C"],
        ]
        self._pub.publish(msg)
        self._publish_status()

    def _publish_status(self):
        injecting = self.enable_fault and self.fault_type == "drive_abnormal" and self._wheel_mask() != 0
        status = {
            "enable_fault": self.enable_fault,
            "fault_type": self.fault_type if injecting else "normal",
            "fault_wheel": self._fault_wheel_label() if injecting else "none",
            "fault_alpha": self._active_alpha_label() if injecting else 1.0,
            "wheel_mask": self._wheel_mask(),
            "wheels": dict(self.wheels),
            "alpha": dict(self.alpha),
            "injecting": injecting,
        }
        self._status_pub.publish(String(data=json.dumps(status, sort_keys=True)))

    def _apply_legacy_payload(self, payload):
        if "fault_wheel" in payload:
            wheel = str(payload.get("fault_wheel", "")).strip().upper()
            self.wheels = {"A": False, "B": False, "C": False}
            if wheel in WHEEL_BITS:
                self.wheels[wheel] = True
        if "fault_alpha" in payload:
            alpha = clamp_alpha(payload["fault_alpha"])
            for wheel in WHEELS:
                if self.wheels.get(wheel, False):
                    self.alpha[wheel] = alpha

    def _apply_payload(self, payload):
        if "enable_fault" in payload:
            self.enable_fault = boolish(payload["enable_fault"])
        if "fault_type" in payload:
            self.fault_type = str(payload["fault_type"]).strip() or "normal"

        wheels = payload.get("wheels")
        if isinstance(wheels, dict):
            self.wheels = {
                wheel: boolish(wheels.get(wheel, False))
                for wheel in WHEELS
            }
        else:
            self._apply_legacy_payload(payload)

        alpha = payload.get("alpha")
        if isinstance(alpha, dict):
            for wheel in WHEELS:
                if wheel in alpha:
                    self.alpha[wheel] = clamp_alpha(alpha[wheel])
        else:
            self._apply_legacy_payload(payload)

    def _config_callback(self, msg):
        try:
            payload = json.loads(msg.data or "{}")
        except ValueError as e:
            rospy.logwarn("fault_config_bridge: bad config JSON: %s", e)
            return

        self._apply_payload(payload)
        self._publish_config()
        rospy.loginfo(
            "fault config published: enable=%s type=%s mask=0x%02X alpha=[%.3f, %.3f, %.3f]",
            self.enable_fault,
            self.fault_type,
            self._wheel_mask(),
            self.alpha["A"],
            self.alpha["B"],
            self.alpha["C"],
        )


def main():
    rospy.init_node("fault_injector", anonymous=False)
    FaultInjector()
    rospy.spin()


if __name__ == "__main__":
    main()
