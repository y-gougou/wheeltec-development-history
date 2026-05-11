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

import sys

import rospy
import serial
from std_msgs.msg import Float32MultiArray


FRAME_HEADER = "$CURRENT,"
FRAME_TAIL = "*"
FRAME_END = "\r\n"


class CurrentReader(object):
    def __init__(self):
        rospy.init_node("current_reader", anonymous=True)

        self.port = rospy.get_param("~port", "/dev/ttyUSB1")
        self.baud = int(rospy.get_param("~baud", 115200))
        self.timeout = float(rospy.get_param("~timeout", 0.05))
        self.open_retries = int(rospy.get_param("~open_retries", 3))
        self.open_retry_delay = float(rospy.get_param("~open_retry_delay", 1.0))
        self.loop_rate = float(rospy.get_param("~loop_rate", 200.0))
        self.report_interval = float(rospy.get_param("~report_interval", 5.0))
        self.max_frames_per_cycle = int(rospy.get_param("~max_frames_per_cycle", 20))

        self.pub = rospy.Publisher("/current_data", Float32MultiArray, queue_size=10)

        self.read_count = 0
        self.valid_count = 0
        self.timeout_count = 0
        self.parse_error_count = 0
        self.checksum_error_count = 0
        self.seq_gap_count = 0
        self.last_seq = -1
        self.last_current_time = 0.0
        self.last_report_time = rospy.Time.now().to_sec()

        self.serial_port = self._open_serial()
        self.serial_port.reset_input_buffer()

    def _open_serial(self):
        last_error = None
        for attempt in range(1, self.open_retries + 1):
            try:
                rospy.loginfo(
                    "Opening current serial port %s @ %d (%d/%d)",
                    self.port,
                    self.baud,
                    attempt,
                    self.open_retries,
                )
                ser = serial.Serial(
                    port=self.port,
                    baudrate=self.baud,
                    timeout=self.timeout,
                )
                rospy.loginfo("Current serial opened: %s", ser.name)
                return ser
            except serial.SerialException as e:
                last_error = e
                if attempt < self.open_retries and not rospy.is_shutdown():
                    rospy.logwarn(
                        "Open %s failed: %s; retry in %.1fs",
                        self.port,
                        e,
                        self.open_retry_delay,
                    )
                    rospy.sleep(self.open_retry_delay)
        raise last_error

    @staticmethod
    def _xor_ascii(payload):
        checksum = 0
        for ch in payload:
            checksum ^= ord(ch)
        return checksum

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

        calc_checksum = self._xor_ascii(line[:data_end])

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

    def run(self):
        rospy.loginfo(
            "Start reading current data from %s timeout=%.3fs loop_rate=%.1fHz",
            self.port,
            self.timeout,
            self.loop_rate,
        )
        rate = rospy.Rate(self.loop_rate)
        while not rospy.is_shutdown():
            frames_read = 0
            while not rospy.is_shutdown() and frames_read < self.max_frames_per_cycle:
                data = self.read_frame()
                if data:
                    self.publish_frame(data)
                frames_read += 1
                if self.serial_port.in_waiting <= 0:
                    break
            self.report()
            rate.sleep()

    def close(self):
        if hasattr(self, "serial_port") and self.serial_port and self.serial_port.is_open:
            self.serial_port.close()
            rospy.loginfo("Current serial closed")


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
