#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Collect synchronized robot fault-diagnosis rows into a fixed CSV schema.

The node keeps the existing low-risk strategy: /odom triggers one CSV row, and
all other topics contribute their latest cached value.  Each row records source
timestamps and ages so bad synchronization can be found before training.
"""

from __future__ import print_function

import json
import rospy
from geometry_msgs.msg import Twist, Vector3
from nav_msgs.msg import Odometry
from sensor_msgs.msg import Imu
from std_msgs.msg import Bool, Float32, Float32MultiArray, String

from core.csv_utils import CsvRowWriter, default_run_id, unique_csv_path
from core.ros_params import get_bool, get_float, get_int, get_str
from core.time_utils import age, fmt_float, now_sec, stamp_to_sec, time_delta


class DataCollector(object):
    FAULT_NAMES = {
        0: "normal",
        1: "drive_fault",
        2: "wheel_slip",
        3: "shaft_eccentric",
        4: "encoder_fault",
    }

    CSV_FIELDS = [
        "timestamp",
        "run_id",
        "sample_id",
        "fault_label",
        "fault_name",
        "fault_mode",
        "motion_mode",
        "cmd_vx",
        "cmd_vy",
        "cmd_wz",
        "odom_vx",
        "odom_vy",
        "odom_wz",
        "wheel_speed0",
        "wheel_speed1",
        "wheel_speed2",
        "imu_ax",
        "imu_ay",
        "imu_az",
        "imu_gx",
        "imu_gy",
        "imu_gz",
        "voltage",
        "current_seq",
        "current0",
        "current1",
        "current2",
        "odom_time",
        "imu_time",
        "voltage_time",
        "current_time",
        "current_dt",
        "cmd_time",
        "odom_age",
        "imu_age",
        "voltage_age",
        "current_age",
        "cmd_age",
        "record_rate",
        "current_valid",
        "current_reused_count",
    ]

    def __init__(self):
        self.output_dir = get_str("~output_dir", "/home/wheeltec/R550PLUS_data_collect/log")
        self.run_id = get_str("~run_id", "")
        self.fault_label = get_int("~fault_label", 0)
        fault_name_param = get_str("~fault_name", "")
        self.fault_name = fault_name_param or self.FAULT_NAMES.get(
            self.fault_label, "unknown"
        )
        self.fault_mode = get_int("~fault_mode", 0)
        self.motion_mode = get_str("~motion_mode", "straight_0.25ms")
        self.odom_topic = get_str("~odom_topic", "/odom")
        self.imu_topic = get_str("~imu_topic", "/imu")
        self.voltage_topic = get_str("~voltage_topic", "/PowerVoltage")
        self.current_topic = get_str("~current_topic", "/current_data")
        self.cmd_topic = get_str("~cmd_topic", "/cmd_vel")
        self.wheel_speed_topic = get_str("~wheel_speed_topic", "")
        self.expected_rate = get_float("~expected_rate", 20.0)
        self.require_current_before_record = get_bool("~require_current_before_record", True)
        self.current_wait_timeout = get_float("~current_wait_timeout", 20.0)
        self.auto_start = get_bool("~auto_start", True)
        self.enable_topic = get_str("~enable_topic", "/web/collection_enable")
        self.config_topic = get_str("~config_topic", "/web/collection_config")
        self.status_topic = get_str("~status_topic", "/web/collection_status")

        if not self.run_id:
            self.run_id = default_run_id(self.fault_name)

        self.sample_id = 0
        self.current_seq = -1
        self.current_rx_seq = -1
        self.last_recorded_current_seq = -1
        self.current_reused_count = 0
        self.last_record_wall_time = None
        self.last_flush_wall_time = None
        self.csv_file = None
        self.csv_writer = None
        self.is_shutting_down = False
        self.collecting = False
        self.state = "idle"
        self.current_filepath = ""
        self.last_error = ""
        self.flush_every_rows = get_int("~flush_every_rows", 20)
        self.flush_interval = get_float("~flush_interval", 1.0)
        self.status_pub = rospy.Publisher(self.status_topic, String, queue_size=1, latch=True)

        self.latest = {
            "odom": None,
            "imu": None,
            "voltage": None,
            "current": None,
            "cmd": None,
            "wheel_speed": None,
            "odom_time": None,
            "imu_time": None,
            "voltage_time": None,
            "current_time": None,
            "cmd_time": None,
            "wheel_speed_time": None,
        }

        self._setup_subscribers()
        rospy.Subscriber(self.enable_topic, Bool, self._enable_callback, queue_size=5)
        rospy.Subscriber(self.config_topic, String, self._config_callback, queue_size=5)
        if self.auto_start:
            self.start_collection()
        else:
            self._publish_status()

        rospy.loginfo(
            "data_collector ready: run_id=%s label=%d/%s mode=%s expected_rate=%.1fHz auto_start=%s",
            self.run_id,
            self.fault_label,
            self.fault_name,
            self.motion_mode,
            self.expected_rate,
            self.auto_start,
        )

    def _wait_for_initial_current(self):
        rospy.loginfo(
            "Waiting for first valid current frame on %s before writing CSV (timeout %.1fs)",
            self.current_topic,
            self.current_wait_timeout,
        )
        deadline = now_sec() + self.current_wait_timeout
        rate = rospy.Rate(20)
        while not rospy.is_shutdown() and self.latest["current"] is None:
            if now_sec() >= deadline:
                raise rospy.ROSException(
                    "No current frame received on %s within %.1fs; aborting CSV collection"
                    % (self.current_topic, self.current_wait_timeout)
                )
            rate.sleep()
        if self.latest["current"] is not None:
            rospy.loginfo("First valid current frame received; CSV recording can start")

    def _setup_subscribers(self):
        rospy.Subscriber(self.odom_topic, Odometry, self._odom_callback, queue_size=50)
        rospy.Subscriber(self.imu_topic, Imu, self._imu_callback, queue_size=50)
        rospy.Subscriber(self.voltage_topic, Float32, self._voltage_callback, queue_size=20)
        rospy.Subscriber(
            self.current_topic, Float32MultiArray, self._current_callback, queue_size=50
        )
        rospy.Subscriber(self.cmd_topic, Twist, self._cmd_callback, queue_size=50)
        if self.wheel_speed_topic:
            rospy.Subscriber(
                self.wheel_speed_topic,
                Float32MultiArray,
                self._wheel_speed_callback,
                queue_size=50,
            )

    def _enable_callback(self, msg):
        if msg.data:
            self.start_collection()
        else:
            self.stop_collection("stopped")

    def _config_callback(self, msg):
        try:
            payload = json.loads(msg.data or "{}")
        except ValueError as e:
            self.last_error = "bad config json: %s" % e
            self._publish_status()
            return
        self.apply_config(payload)

    def apply_config(self, payload):
        was_collecting = self.collecting
        if was_collecting:
            self.stop_collection("stopped")

        self.output_dir = str(payload.get("output_dir", self.output_dir)).strip() or self.output_dir
        self.run_id = str(payload.get("run_id", self.run_id)).strip()
        self.fault_label = int(payload.get("fault_label", self.fault_label))
        self.fault_name = str(
            payload.get("fault_name", self.fault_name or self.FAULT_NAMES.get(self.fault_label, "unknown"))
        ).strip() or self.FAULT_NAMES.get(self.fault_label, "unknown")
        self.fault_mode = int(payload.get("fault_mode", self.fault_mode))
        self.motion_mode = str(payload.get("motion_mode", self.motion_mode)).strip() or self.motion_mode
        self.expected_rate = float(payload.get("expected_rate", self.expected_rate))
        self.require_current_before_record = bool(
            payload.get("require_current_before_record", self.require_current_before_record)
        )
        self.current_wait_timeout = float(payload.get("current_wait_timeout", self.current_wait_timeout))
        if not self.run_id:
            self.run_id = default_run_id(self.fault_name)

        self.last_error = ""
        self._publish_status()
        if payload.get("start", False) or was_collecting:
            self.start_collection()

    def start_collection(self):
        if self.collecting:
            self._publish_status()
            return
        try:
            if self.require_current_before_record:
                self._wait_for_initial_current()
            self.sample_id = 0
            self.current_reused_count = 0
            self.last_recorded_current_seq = -1
            self.last_record_wall_time = None
            self._open_csv_file()
            self.collecting = True
            self.state = "collecting"
            self.last_error = ""
            rospy.loginfo("CSV collection started: %s", self.current_filepath)
        except Exception as e:
            self.collecting = False
            self.state = "error"
            self.last_error = str(e)
            rospy.logerr("CSV collection start failed: %s", e)
        self._publish_status()

    def stop_collection(self, state="stopped"):
        if self.csv_writer:
            self.csv_writer.close()
            self.csv_file = None
            self.csv_writer = None
        self.collecting = False
        self.state = state
        rospy.loginfo("CSV collection %s: rows=%d", state, self.sample_id)
        self._publish_status()

    def _open_csv_file(self):
        filepath = unique_csv_path(self.output_dir, self.run_id)
        if not filepath.endswith("%s.csv" % self.run_id):
            rospy.logwarn("CSV exists, writing to new file: %s", filepath)
        self.csv_writer = CsvRowWriter(filepath, self.CSV_FIELDS)
        self.csv_file = self.csv_writer.fileobj
        self.current_filepath = filepath
        self.last_flush_wall_time = now_sec()
        rospy.loginfo("CSV output: %s", filepath)

    def _publish_status(self):
        msg = String()
        msg.data = json.dumps({
            "state": self.state,
            "collecting": bool(self.collecting),
            "run_id": self.run_id,
            "output_dir": self.output_dir,
            "fault_label": self.fault_label,
            "fault_name": self.fault_name,
            "fault_mode": self.fault_mode,
            "motion_mode": self.motion_mode,
            "expected_rate": self.expected_rate,
            "sample_id": self.sample_id,
            "filepath": self.current_filepath,
            "error": self.last_error,
        })
        self.status_pub.publish(msg)

    def _odom_callback(self, msg):
        if self.is_shutting_down:
            return
        self.latest["odom"] = msg
        self.latest["odom_time"] = stamp_to_sec(msg.header.stamp)
        self._record_row()

    def _imu_callback(self, msg):
        self.latest["imu"] = msg
        self.latest["imu_time"] = stamp_to_sec(msg.header.stamp)

    def _voltage_callback(self, msg):
        self.latest["voltage"] = msg
        self.latest["voltage_time"] = now_sec()

    def _current_callback(self, msg):
        self.latest["current"] = msg
        self.latest["current_time"] = now_sec()
        self.current_seq += 1
        if len(msg.data) >= 4:
            try:
                self.current_rx_seq = int(msg.data[3])
            except (TypeError, ValueError):
                self.current_rx_seq = self.current_seq
        else:
            self.current_rx_seq = self.current_seq

    def _cmd_callback(self, msg):
        self.latest["cmd"] = msg
        self.latest["cmd_time"] = now_sec()

    def _wheel_speed_callback(self, msg):
        self.latest["wheel_speed"] = msg
        self.latest["wheel_speed_time"] = now_sec()

    def _record_row(self):
        if (
            self.is_shutting_down
            or not self.collecting
            or self.csv_file is None
            or self.csv_writer is None
        ):
            return

        odom = self.latest["odom"]
        if odom is None:
            return

        timestamp = self.latest["odom_time"]
        wall_now = now_sec()
        if self.last_record_wall_time is None:
            record_rate = 0.0
        else:
            dt = max(1e-6, wall_now - self.last_record_wall_time)
            record_rate = 1.0 / dt
        self.last_record_wall_time = wall_now

        imu = self.latest["imu"]
        voltage = self.latest["voltage"]
        current = self.latest["current"]
        cmd = self.latest["cmd"]
        wheel_speed = self.latest["wheel_speed"]

        current_values = list(current.data) if current is not None else []
        wheel_values = list(wheel_speed.data) if wheel_speed is not None else []
        current_valid = len(current_values) >= 3

        if current_valid:
            if self.current_rx_seq == self.last_recorded_current_seq:
                self.current_reused_count += 1
            else:
                self.current_reused_count = 0
                self.last_recorded_current_seq = self.current_rx_seq
        else:
            self.current_reused_count = 0

        row = {
            "timestamp": fmt_float(timestamp),
            "run_id": self.run_id,
            "sample_id": self.sample_id,
            "fault_label": self.fault_label,
            "fault_name": self.fault_name,
            "fault_mode": self.fault_mode,
            "motion_mode": self.motion_mode,
            "cmd_vx": fmt_float(cmd.linear.x if cmd else 0.0),
            "cmd_vy": fmt_float(cmd.linear.y if cmd else 0.0),
            "cmd_wz": fmt_float(cmd.angular.z if cmd else 0.0),
            "odom_vx": fmt_float(odom.twist.twist.linear.x),
            "odom_vy": fmt_float(odom.twist.twist.linear.y),
            "odom_wz": fmt_float(odom.twist.twist.angular.z),
            "wheel_speed0": fmt_float(wheel_values[0] if len(wheel_values) > 0 else 0.0),
            "wheel_speed1": fmt_float(wheel_values[1] if len(wheel_values) > 1 else 0.0),
            "wheel_speed2": fmt_float(wheel_values[2] if len(wheel_values) > 2 else 0.0),
            "imu_ax": fmt_float(imu.linear_acceleration.x if imu else 0.0),
            "imu_ay": fmt_float(imu.linear_acceleration.y if imu else 0.0),
            "imu_az": fmt_float(imu.linear_acceleration.z if imu else 0.0),
            "imu_gx": fmt_float(imu.angular_velocity.x if imu else 0.0),
            "imu_gy": fmt_float(imu.angular_velocity.y if imu else 0.0),
            "imu_gz": fmt_float(imu.angular_velocity.z if imu else 0.0),
            "voltage": fmt_float(voltage.data if voltage else 0.0, 4),
            "current_seq": self.current_rx_seq,
            "current0": fmt_float(current_values[0] if len(current_values) > 0 else 0.0, 4),
            "current1": fmt_float(current_values[1] if len(current_values) > 1 else 0.0, 4),
            "current2": fmt_float(current_values[2] if len(current_values) > 2 else 0.0, 4),
            "odom_time": fmt_float(self.latest["odom_time"] or timestamp),
            "imu_time": fmt_float(self.latest["imu_time"] or timestamp),
            "voltage_time": fmt_float(self.latest["voltage_time"] or timestamp),
            "current_time": fmt_float(self.latest["current_time"] or timestamp),
            "current_dt": time_delta(timestamp, self.latest["current_time"]),
            "cmd_time": fmt_float(self.latest["cmd_time"] or timestamp),
            "odom_age": age(wall_now, self.latest["odom_time"]),
            "imu_age": age(wall_now, self.latest["imu_time"]),
            "voltage_age": age(wall_now, self.latest["voltage_time"]),
            "current_age": age(wall_now, self.latest["current_time"]),
            "cmd_age": age(wall_now, self.latest["cmd_time"]),
            "record_rate": fmt_float(record_rate, 3),
            "current_valid": 1 if current_valid else 0,
            "current_reused_count": self.current_reused_count,
        }

        self.csv_writer.writerow(row)
        self.sample_id += 1
        self._flush_if_needed(wall_now)

        if self.sample_id % 500 == 0:
            rospy.loginfo(
                "recorded %d rows, rate=%.1f Hz, current_age=%s, current_dt=%s, current_reused=%d",
                self.sample_id,
                record_rate,
                row["current_age"],
                row["current_dt"],
                self.current_reused_count,
            )
            self._publish_status()

    def _flush_if_needed(self, wall_now):
        if self.csv_file is None:
            return
        rows_due = self.flush_every_rows > 0 and self.sample_id % self.flush_every_rows == 0
        time_due = (
            self.flush_interval > 0.0
            and self.last_flush_wall_time is not None
            and wall_now - self.last_flush_wall_time >= self.flush_interval
        )
        if rows_due or time_due:
            self.csv_file.flush()
            self.last_flush_wall_time = wall_now

    def shutdown(self):
        self.is_shutting_down = True
        self.stop_collection("stopped")
        rospy.loginfo("data_collector stopped: %d rows", self.sample_id)


def main():
    rospy.init_node("data_collector", anonymous=False)
    collector = DataCollector()
    rospy.on_shutdown(collector.shutdown)
    rospy.spin()


if __name__ == "__main__":
    main()
