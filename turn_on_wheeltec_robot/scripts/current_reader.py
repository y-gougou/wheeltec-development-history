#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Read the 3-channel current board and publish /current_data.

Expected frame:
    $CURRENT,ch0,ch1,ch2*XX
or:
    $CURRENT,seq,ch0,ch1,ch2*XX

XX is the XOR checksum of bytes from '$' to before '*'.
"""

from __future__ import print_function

import json
import sys

import rospy
from std_msgs.msg import Float32MultiArray, String

from core.ros_params import get_float, get_int, get_str
from core.serial_utils import close_serial, open_serial_with_retries, xor_ascii

FRAME_HEADER = "$CURRENT,"
FRAME_TAIL = "*"


class CurrentReader(object):
    def __init__(self):
        rospy.init_node("current_reader", anonymous=True)

        self.port = get_str("~port", "/dev/ttyUSB0")
        self.baud = get_int("~baud", 115200)
        self.timeout = get_float("~timeout", 0.05)
        self.open_retries = get_int("~open_retries", 3)
        self.open_retry_delay = get_float("~open_retry_delay", 1.0)
        self.loop_rate = get_float("~loop_rate", 200.0)
        self.report_interval = get_float("~report_interval", 5.0)
        self.max_frames_per_cycle = get_int("~max_frames_per_cycle", 20)
        self.config_topic = get_str("~config_topic", "/web/current_reader_config")
        self.status_topic = get_str("~status_topic", "/web/current_reader_status")

        self.pub = rospy.Publisher("/current_data", Float32MultiArray, queue_size=10)
        self.status_pub = rospy.Publisher(self.status_topic, String, queue_size=1, latch=True)
        rospy.Subscriber(self.config_topic, String, self._config_callback, queue_size=5)

        self.read_count = 0
        self.valid_count = 0
        self.total_valid_count = 0
        self.timeout_count = 0
        self.parse_error_count = 0
        self.checksum_error_count = 0
        self.seq_gap_count = 0
        self.last_seq = -1
        self.last_current_time = 0.0
        self.last_report_time = rospy.Time.now().to_sec()
        self.last_error = ""
        self.connected = False
        self.pending_config = None

        self.serial_port = None
        self._connect()

    def _open_serial(self):
        return open_serial_with_retries(
            self.port,
            self.baud,
            self.timeout,
            self.open_retries,
            self.open_retry_delay,
            "current serial",
        )

    def _connect(self):
        self.connected = False
        close_serial(getattr(self, "serial_port", None), "current serial")
        self.serial_port = None
        try:
            self.serial_port = self._open_serial()
            self.serial_port.reset_input_buffer()
            self.connected = True
            self.last_error = ""
        except Exception as e:
            self.last_error = str(e)
            rospy.logerr("current_reader open failed: %s", e)
        self._publish_status()

    def _config_callback(self, msg):
        try:
            payload = json.loads(msg.data or "{}")
        except ValueError as e:
            self.last_error = "bad config json: %s" % e
            self._publish_status()
            return
        self.pending_config = payload

    def _apply_pending_config(self):
        if not self.pending_config:
            return
        payload = self.pending_config
        self.pending_config = None

        new_port = str(payload.get("port", self.port)).strip() or self.port
        new_baud = int(payload.get("baud", self.baud))
        new_timeout = float(payload.get("timeout", self.timeout))
        changed = (
            new_port != self.port
            or new_baud != self.baud
            or abs(new_timeout - self.timeout) > 1e-6
        )
        self.port = new_port
        self.baud = new_baud
        self.timeout = new_timeout
        if changed or payload.get("reconnect", False):
            rospy.loginfo("current_reader reconnect requested: port=%s baud=%d", self.port, self.baud)
            self._connect()
        else:
            self._publish_status()

    def _publish_status(self):
        msg = String()
        now = rospy.Time.now().to_sec()
        msg.data = json.dumps({
            "connected": bool(self.connected),
            "port": self.port,
            "baud": self.baud,
            "timeout": self.timeout,
            "valid_total": self.total_valid_count,
            "last_current_age": now - self.last_current_time if self.last_current_time > 0 else None,
            "last_seq": self.last_seq,
            "error": self.last_error,
        })
        self.status_pub.publish(msg)

    def parse_frame(self, line):
        line = line.strip()
        header_pos = line.find(FRAME_HEADER)
        if header_pos < 0:
            self.parse_error_count += 1
            return None
        if header_pos > 0:
            line = line[header_pos:]

        if FRAME_TAIL not in line:
            self.parse_error_count += 1
            return None

        data_end = line.index(FRAME_TAIL)
        data_str = line[len(FRAME_HEADER):data_end]
        checksum_start = data_end + 1
        recv_checksum_str = line[checksum_start:checksum_start + 2]
        if len(recv_checksum_str) != 2:
            self.parse_error_count += 1
            return None

        calc_checksum = xor_ascii(line[:data_end])

        try:
            recv_checksum = int(recv_checksum_str, 16)
        except ValueError:
            self.parse_error_count += 1
            return None

        if calc_checksum != recv_checksum:
            self.checksum_error_count += 1
            rospy.logwarn_throttle(
                5,
                "Current checksum mismatch: calc=0x%02X recv=0x%02X",
                calc_checksum,
                recv_checksum,
            )
            return None

        parts = data_str.split(",")
        seq = None
        if len(parts) == 4:
            try:
                seq = int(float(parts[0]))
            except ValueError:
                self.parse_error_count += 1
                return None
            parts = parts[1:]

        if len(parts) != 3:
            self.parse_error_count += 1
            return None

        try:
            values = [float(parts[0]), float(parts[1]), float(parts[2])]
        except ValueError:
            self.parse_error_count += 1
            return None

        if seq is not None:
            if self.last_seq >= 0 and seq != self.last_seq + 1:
                self.seq_gap_count += 1
            self.last_seq = seq
            values.append(float(seq))
        return values

    def read_frame(self):
        line = self.serial_port.readline()
        if not line:
            self.timeout_count += 1
            return None
        self.read_count += 1
        try:
            line = line.decode("ascii", errors="ignore")
        except Exception:
            self.parse_error_count += 1
            return None
        return self.parse_frame(line)

    def publish_frame(self, data):
        msg = Float32MultiArray()
        msg.data = data
        self.pub.publish(msg)
        self.valid_count += 1
        self.total_valid_count += 1
        self.last_current_time = rospy.Time.now().to_sec()

    def report(self):
        now = rospy.Time.now().to_sec()
        if now - self.last_report_time < self.report_interval:
            return

        dt = max(1e-6, now - self.last_report_time)
        current_age = now - self.last_current_time if self.last_current_time > 0 else -1.0
        rospy.loginfo(
            "Current reader: read_rate=%.1f Hz valid_rate=%.1f Hz read=%d valid=%d timeout=%d parse_error=%d checksum_error=%d seq_gap=%d last_seq=%d last_current_age=%.3fs",
            self.read_count / dt,
            self.valid_count / dt,
            self.read_count,
            self.valid_count,
            self.timeout_count,
            self.parse_error_count,
            self.checksum_error_count,
            self.seq_gap_count,
            self.last_seq,
            current_age,
        )
        self.read_count = 0
        self.valid_count = 0
        self.timeout_count = 0
        self.parse_error_count = 0
        self.checksum_error_count = 0
        self.seq_gap_count = 0
        self.last_report_time = now
        self._publish_status()

    def run(self):
        rospy.loginfo(
            "Start reading current data from %s timeout=%.3fs loop_rate=%.1fHz",
            self.port,
            self.timeout,
            self.loop_rate,
        )
        rate = rospy.Rate(self.loop_rate)
        while not rospy.is_shutdown():
            self._apply_pending_config()
            if not self.connected or self.serial_port is None:
                self._publish_status()
                rate.sleep()
                continue
            frames_read = 0
            while not rospy.is_shutdown() and frames_read < self.max_frames_per_cycle:
                try:
                    data = self.read_frame()
                except Exception as e:
                    self.last_error = str(e)
                    rospy.logerr("current_reader read failed: %s", e)
                    self.connected = False
                    close_serial(self.serial_port, "current serial")
                    self.serial_port = None
                    self._publish_status()
                    break
                if data:
                    self.publish_frame(data)
                frames_read += 1
                if self.serial_port.in_waiting <= 0:
                    break
            self.report()
            rate.sleep()

    def close(self):
        close_serial(getattr(self, "serial_port", None), "current serial")
        self.connected = False
        self._publish_status()


if __name__ == "__main__":
    reader = None
    try:
        reader = CurrentReader()
        reader.run()
    except rospy.ROSInterruptException:
        pass
    except Exception as e:
        rospy.logerr("current_reader failed: %s", e)
        sys.exit(1)
    finally:
        if reader:
            reader.close()
