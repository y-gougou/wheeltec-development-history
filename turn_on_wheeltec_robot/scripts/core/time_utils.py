#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Time and formatting helpers shared by ROS scripts."""

from __future__ import print_function

from datetime import datetime

import rospy


def now_sec():
    return rospy.Time.now().to_sec()


def datestamp(fmt="%Y%m%d_%H%M%S"):
    return datetime.now().strftime(fmt)


def stamp_to_sec(stamp):
    value = stamp.to_sec()
    if value > 0:
        return value
    return now_sec()


def fmt_float(value, precision=6):
    return ("%%.%df" % precision) % float(value)


def age(now, topic_time):
    if topic_time is None:
        return ""
    return fmt_float(max(0.0, now - topic_time))


def time_delta(base_time, topic_time):
    if topic_time is None:
        return ""
    return fmt_float(max(0.0, base_time - topic_time))
