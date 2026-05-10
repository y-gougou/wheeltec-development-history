#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Inspect one fault-diagnosis CSV log for collection quality."""

from __future__ import print_function

import argparse
import os

import numpy as np
import pandas as pd


EXPECTED_FIELDS = [
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
    "cmd_time",
    "odom_age",
    "imu_age",
    "voltage_age",
    "current_age",
    "cmd_age",
    "record_rate",
    "current_valid",
]

NUMERIC_COLUMNS = [
    "timestamp",
    "sample_id",
    "fault_label",
    "fault_mode",
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
    "cmd_time",
    "odom_age",
    "imu_age",
    "voltage_age",
    "current_age",
    "cmd_age",
    "record_rate",
    "current_valid",
]


def warn(warnings, message):
    warnings.append(message)


def numeric_series(df, column):
    if column not in df.columns:
        return pd.Series(dtype=np.float64)
    return pd.to_numeric(df[column], errors="coerce")


def finite_values(df, column):
    s = numeric_series(df, column)
    return s[np.isfinite(s)]


def print_stats(name, values):
    values = pd.Series(values).dropna()
    values = values[np.isfinite(values)]
    if len(values) == 0:
        print("%s: no valid values" % name)
        return
    print(
        "%s: min=%.6f mean=%.6f max=%.6f std=%.6f"
        % (name, values.min(), values.mean(), values.max(), values.std(ddof=0))
    )


def print_describe(df, columns):
    existing = [c for c in columns if c in df.columns]
    if not existing:
        print("describe: missing columns %s" % ", ".join(columns))
        return
    desc = df[existing].apply(pd.to_numeric, errors="coerce").describe().T
    cols = ["count", "mean", "std", "min", "25%", "50%", "75%", "max"]
    print(desc[cols].to_string(float_format=lambda x: "%.6f" % x))


def unique_report(df, column, expected, warnings):
    if column not in df.columns:
        warn(warnings, "missing column: %s" % column)
        print("%s: MISSING" % column)
        return
    values = sorted([str(v) for v in df[column].dropna().unique()])
    print("%s unique: %s" % (column, values))
    if expected is not None and values != [str(expected)]:
        warn(warnings, "%s expected %s, got %s" % (column, expected, values))


def inspect(path, args):
    warnings = []
    df = pd.read_csv(path)

    print("file:", os.path.abspath(path))
    print("rows:", len(df))
    print("cols:", len(df.columns))
    print("fields:", ", ".join(df.columns))

    missing_fields = [c for c in EXPECTED_FIELDS if c not in df.columns]
    extra_fields = [c for c in df.columns if c not in EXPECTED_FIELDS]
    if missing_fields:
        warn(warnings, "missing expected fields: %s" % ", ".join(missing_fields))
    if extra_fields:
        print("extra fields:", ", ".join(extra_fields))

    for col in NUMERIC_COLUMNS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    numeric_df = df[[c for c in NUMERIC_COLUMNS if c in df.columns]]
    nan_count = int(numeric_df.isna().sum().sum())
    numeric_cells = int(numeric_df.shape[0] * numeric_df.shape[1])
    nan_ratio = float(nan_count) / numeric_cells if numeric_cells else 0.0
    inf_count = int(np.isinf(numeric_df.values.astype(np.float64)).sum()) if not numeric_df.empty else 0
    print("NaN count:", nan_count)
    print("NaN ratio: %.6f" % nan_ratio)
    print("Inf count:", inf_count)
    if nan_ratio > 0.01:
        warn(warnings, "NaN ratio %.4f is high" % nan_ratio)
    if inf_count > 0:
        warn(warnings, "Inf values found in numeric columns")

    ts = finite_values(df, "timestamp")
    if len(ts) >= 2:
        dt = ts.diff().dropna()
        duration = ts.iloc[-1] - ts.iloc[0]
        avg_rate = (len(ts) - 1) / duration if duration > 0 else 0.0
        print("duration: %.3fs" % duration)
        print_stats("timestamp dt", dt)
        print("average sample rate: %.3f Hz" % avg_rate)
        duplicate_count = int(ts.duplicated().sum())
        print("duplicate timestamp count:", duplicate_count)
        if duplicate_count > 0:
            warn(warnings, "duplicate timestamps found: %d" % duplicate_count)
        expected_dt = 1.0 / args.expected_rate
        if abs(dt.mean() - expected_dt) > args.dt_tolerance:
            warn(warnings, "timestamp mean dt %.4f not close to %.4f" % (dt.mean(), expected_dt))
        if abs(avg_rate - args.expected_rate) > args.rate_tolerance:
            warn(warnings, "average sample rate %.2fHz not close to %.2fHz" % (avg_rate, args.expected_rate))
    else:
        warn(warnings, "not enough timestamps")

    print_stats("record_rate", finite_values(df, "record_rate"))
    rr = finite_values(df, "record_rate")
    if len(rr) > 5:
        rr2 = rr.iloc[1:]
        if abs(rr2.mean() - args.expected_rate) > args.rate_tolerance:
            warn(warnings, "record_rate mean %.2fHz not close to %.2fHz" % (rr2.mean(), args.expected_rate))

    print("")
    unique_report(df, "run_id", args.expected_run_id, warnings)
    unique_report(df, "fault_label", args.expected_fault_label, warnings)
    unique_report(df, "fault_name", args.expected_fault_name, warnings)
    unique_report(df, "fault_mode", args.expected_fault_mode, warnings)
    unique_report(df, "motion_mode", args.expected_motion_mode, warnings)

    print("")
    for col in ["cmd_age", "odom_age", "imu_age", "voltage_age", "current_age"]:
        values = finite_values(df, col)
        print_stats(col, values)
        if col == "cmd_age" and len(values) > 0 and values.mean() > args.max_cmd_age:
            warn(warnings, "cmd_age mean %.3fs is high" % values.mean())
        if col == "current_age" and len(values) > 0 and values.mean() > args.max_current_age:
            warn(warnings, "current_age mean %.3fs is high" % values.mean())

    print("")
    print("cmd describe:")
    print_describe(df, ["cmd_vx", "cmd_vy", "cmd_wz"])
    print("")
    print("odom describe:")
    print_describe(df, ["odom_vx", "odom_vy", "odom_wz"])
    print("")
    print("imu describe:")
    print_describe(df, ["imu_ax", "imu_ay", "imu_az", "imu_gx", "imu_gy", "imu_gz"])
    print("")
    print("voltage describe:")
    print_describe(df, ["voltage"])
    print("")
    print("current describe:")
    print_describe(df, ["current0", "current1", "current2"])

    current_valid = finite_values(df, "current_valid")
    if len(current_valid) > 0:
        valid_ratio = (current_valid > 0).mean()
        print("current_valid ratio: %.3f" % valid_ratio)
        if valid_ratio < 0.95:
            warn(warnings, "current_valid ratio %.3f is low" % valid_ratio)

    cmd_vx = finite_values(df, "cmd_vx")
    if len(cmd_vx) > 0 and (cmd_vx.abs() > 0.1).sum() == 0:
        warn(warnings, "cmd_vx never enters motion stage")
    if len(cmd_vx) > 0 and cmd_vx.abs().max() > args.expected_cmd_abs + args.cmd_tolerance:
        warn(
            warnings,
            "cmd_vx abs max %.3f exceeds expected %.3f by more than %.3f"
            % (cmd_vx.abs().max(), args.expected_cmd_abs, args.cmd_tolerance),
        )

    cmd_wz = finite_values(df, "cmd_wz")
    motion_modes = [str(v) for v in df.get("motion_mode", pd.Series(dtype=str)).dropna().unique()]
    is_straight_mode = any("straight" in mode for mode in motion_modes)
    if is_straight_mode and len(cmd_wz) > 0 and cmd_wz.abs().max() > args.max_straight_cmd_wz:
        warn(
            warnings,
            "straight motion contains large cmd_wz abs max %.3f; use forward/backward translation without turning"
            % cmd_wz.abs().max(),
        )

    currents = [finite_values(df, c) for c in ["current0", "current1", "current2"]]
    if all(len(s) > 0 and s.abs().max() < 1e-6 for s in currents):
        warn(warnings, "all current channels are near zero")

    print("")
    if warnings:
        print("WARNINGS:")
        for item in warnings:
            print("WARNING:", item)
    else:
        print("PASS: no obvious CSV quality issues")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path")
    parser.add_argument("--expected_rate", type=float, default=20.0)
    parser.add_argument("--rate_tolerance", type=float, default=2.0)
    parser.add_argument("--dt_tolerance", type=float, default=0.01)
    parser.add_argument("--max_cmd_age", type=float, default=0.20)
    parser.add_argument("--max_current_age", type=float, default=0.35)
    parser.add_argument("--expected_cmd_abs", type=float, default=0.25)
    parser.add_argument("--cmd_tolerance", type=float, default=0.20)
    parser.add_argument("--max_straight_cmd_wz", type=float, default=0.10)
    parser.add_argument("--expected_run_id", default=None)
    parser.add_argument("--expected_fault_label", default=None)
    parser.add_argument("--expected_fault_name", default=None)
    parser.add_argument("--expected_fault_mode", default=None)
    parser.add_argument("--expected_motion_mode", default=None)
    args = parser.parse_args()
    inspect(args.csv_path, args)


if __name__ == "__main__":
    main()
