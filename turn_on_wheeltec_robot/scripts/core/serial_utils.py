#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Serial-port helpers shared by hardware reader scripts."""

from __future__ import print_function

import rospy
import serial


def open_serial_with_retries(port, baud, timeout, retries=3, retry_delay=1.0, label="serial"):
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            rospy.loginfo(
                "Opening %s port %s @ %d (%d/%d)",
                label,
                port,
                baud,
                attempt,
                retries,
            )
            ser = serial.Serial(port=port, baudrate=baud, timeout=timeout)
            rospy.loginfo("%s port opened: %s", label, ser.name)
            return ser
        except serial.SerialException as e:
            last_error = e
            if attempt < retries and not rospy.is_shutdown():
                rospy.logwarn(
                    "Open %s failed: %s; retry in %.1fs",
                    port,
                    e,
                    retry_delay,
                )
                rospy.sleep(retry_delay)
    raise last_error


def close_serial(ser, label="serial"):
    if ser and getattr(ser, "is_open", False):
        ser.close()
        rospy.loginfo("%s port closed", label)


def xor_ascii(payload):
    checksum = 0
    for ch in payload:
        checksum ^= ord(ch)
    return checksum
