#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Control and message helpers shared by teleop scripts."""

from __future__ import print_function

from geometry_msgs.msg import Twist


def clamp(value, limit):
    if value > limit:
        return limit
    if value < -limit:
        return -limit
    return value


def zero_twist():
    return Twist()


class PIDController(object):
    def __init__(self, kp=0.8, ki=0.1, kd=0.3, output_limit=1.0):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.output_limit = output_limit
        self.integral = 0.0
        self.prev_error = 0.0

    def compute(self, target, current, dt=None):
        error = target - current
        if dt is not None and dt > 0:
            derivative = (error - self.prev_error) / dt
        else:
            derivative = 0.0

        self.integral += error * (dt or 0.1)
        self.integral = clamp(self.integral, 0.5)

        output = self.kp * error + self.ki * self.integral + self.kd * derivative
        output = clamp(output, self.output_limit)
        self.prev_error = error
        return output

    def reset(self):
        self.integral = 0.0
        self.prev_error = 0.0
