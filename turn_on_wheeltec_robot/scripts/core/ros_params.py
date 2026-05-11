#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Small typed wrappers around rospy private parameters."""

from __future__ import print_function

import rospy


def get_param(name, default=None):
    return rospy.get_param(name, default)


def get_str(name, default=""):
    return str(rospy.get_param(name, default))


def get_int(name, default=0):
    return int(rospy.get_param(name, default))


def get_float(name, default=0.0):
    return float(rospy.get_param(name, default))


def get_bool(name, default=False):
    value = rospy.get_param(name, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in ("1", "true", "yes", "on")
