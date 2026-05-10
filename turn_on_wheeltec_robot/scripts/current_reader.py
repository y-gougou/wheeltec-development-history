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
        self.timeout = float(rospy.get_param("~timeout", 1.0))
        self.open_retries = int(rospy.get_param("~open_retries", 3))
        self.open_retry_delay = float(rospy.get_param("~open_retry_delay", 1.0))

        self.pub = rospy.Publisher("/current_data", Float32MultiArray, queue_size=10)

        self.ok_count = 0
        self.timeout_count = 0
        self.parse_error_count = 0
        self.checksum_error_count = 0
        self.last_seq = -1
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

    def parse_frame(self, line):
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
        checksum_end = line.find(FRAME_END, checksum_start)
        recv_checksum_str = line[checksum_start:] if checksum_end < 0 else line[checksum_start:checksum_end]

        calc_checksum = 0
        for i in range(data_end):
            calc_checksum ^= ord(line[i])

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
            self.last_seq = seq
            values.append(float(seq))
        return values

    def read_frame(self):
        line = self.serial_port.readline()
        if not line:
            self.timeout_count += 1
            return None
        try:
            line = line.decode("ascii", errors="ignore")
        except Exception:
            self.parse_error_count += 1
            return None
        return self.parse_frame(line)

    def report(self):
        now = rospy.Time.now().to_sec()
        if now - self.last_report_time < 10.0:
            return

        dt = max(1e-6, now - self.last_report_time)
        rospy.loginfo(
            "Current reader: %.1f Hz, ok=%d, timeout=%d, parse_error=%d, checksum_error=%d, last_seq=%d",
            self.ok_count / dt,
            self.ok_count,
            self.timeout_count,
            self.parse_error_count,
            self.checksum_error_count,
            self.last_seq,
        )
        self.ok_count = 0
        self.timeout_count = 0
        self.parse_error_count = 0
        self.checksum_error_count = 0
        self.last_report_time = now

    def run(self):
        rospy.loginfo("Start reading current data from %s", self.port)
        rate = rospy.Rate(100)
        while not rospy.is_shutdown():
            data = self.read_frame()
            if data:
                msg = Float32MultiArray()
                msg.data = data
                self.pub.publish(msg)
                self.ok_count += 1
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
