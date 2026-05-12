#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Convert /n100/imu into a normalized heading topic."""

from __future__ import print_function

import json
import math

import rospy
from sensor_msgs.msg import Imu
from std_msgs.msg import Empty, Float32, String

from core.ros_params import get_float, get_str


def quat_to_yaw_deg(q):
    siny_cosp = 2.0 * (q.w * q.z + q.x * q.y)
    cosy_cosp = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
    return math.degrees(math.atan2(siny_cosp, cosy_cosp))


def normalize_angle_deg(angle):
    while angle >= 180.0:
        angle -= 360.0
    while angle < -180.0:
        angle += 360.0
    return angle


class HeadingBridge(object):
    def __init__(self):
        rospy.init_node("heading_bridge", anonymous=False)
        self.imu_topic = get_str("~imu_topic", "/n100/imu")
        self.heading_topic = get_str("~heading_topic", "/chassis/heading_deg")
        self.status_topic = get_str("~status_topic", "/web/heading_status")
        self.heading_zero_offset = get_float("~heading_zero_offset", 0.0)
        self.publish_rate = max(1.0, get_float("~publish_rate", 30.0))
        self.min_publish_period = 1.0 / self.publish_rate

        self.last_raw = 0.0
        self.last_unwrapped = 0.0
        self.last_heading = 0.0
        self.valid = False
        self.last_error = ""
        self.unwrap_turns = 0.0
        self.prev_raw = None
        self.last_publish_time = 0.0

        self.pub = rospy.Publisher(self.heading_topic, Float32, queue_size=10)
        self.status_pub = rospy.Publisher(self.status_topic, String, queue_size=1, latch=True)
        rospy.Subscriber(self.imu_topic, Imu, self.imu_callback, queue_size=50)
        rospy.Subscriber("/web/heading_zero", Empty, self.zero_callback, queue_size=5)
        rospy.Subscriber("/web/heading_offset", Float32, self.offset_callback, queue_size=5)

        rospy.on_shutdown(self.shutdown)
        self._publish_status()
        rospy.loginfo("heading_bridge ready: %s -> %s", self.imu_topic, self.heading_topic)

    def zero_callback(self, _msg):
        self.heading_zero_offset = self.last_unwrapped
        self._publish_status()

    def offset_callback(self, msg):
        self.heading_zero_offset = msg.data
        self._publish_status()

    def imu_callback(self, msg):
        raw = quat_to_yaw_deg(msg.orientation)
        if self.prev_raw is None:
            unwrapped = raw
        else:
            delta = raw - self.prev_raw
            if delta > 180.0:
                self.unwrap_turns -= 1.0
            elif delta < -180.0:
                self.unwrap_turns += 1.0
            unwrapped = raw + 360.0 * self.unwrap_turns
        self.prev_raw = raw
        self.last_raw = raw
        self.last_unwrapped = unwrapped
        self.last_heading = normalize_angle_deg(unwrapped - self.heading_zero_offset)
        self.valid = True

        now = rospy.get_time()
        if now - self.last_publish_time < self.min_publish_period:
            return
        self.last_publish_time = now

        self.pub.publish(Float32(data=self.last_heading))
        self._publish_status()

    def _publish_status(self):
        payload = {
            "valid": self.valid,
            "heading": round(self.last_heading, 3),
            "raw": round(self.last_raw, 3),
            "unwrapped": round(self.last_unwrapped, 3),
            "zero_offset": round(self.heading_zero_offset, 3),
            "error": self.last_error,
        }
        self.status_pub.publish(String(data=json.dumps(payload, ensure_ascii=False)))

    def shutdown(self):
        self._publish_status()


if __name__ == "__main__":
    HeadingBridge()
    rospy.spin()
