#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build windowed fault-diagnosis dataset from raw CSV logs.

Converts raw CSV files produced by data_collector.py into sliding-window
numpy arrays suitable for CWCNN-FA training.

Output: X_train.npy, y_train.npy, X_test.npy, y_test.npy,
        meta_train.csv, meta_test.csv, scaler.pkl, feature_config.json
"""

from __future__ import print_function, unicode_literals

import argparse
import glob
import json
import os
import sys
from collections import OrderedDict
from datetime import datetime

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

# ---------------------------------------------------------------------------
# Feature definitions
# ---------------------------------------------------------------------------

MODEL_FEATURES_15 = [
    "odom_vx", "odom_vy", "odom_wz",
    "wheel_speed0", "wheel_speed1", "wheel_speed2",
    "imu_ax", "imu_ay", "imu_az",
    "imu_gx", "imu_gy", "imu_gz",
    "current0", "current1", "current2",
]

MODEL_FEATURES_12 = [
    "odom_vx", "odom_vy", "odom_wz",
    "imu_ax", "imu_ay", "imu_az",
    "imu_gx", "imu_gy", "imu_gz",
    "current0", "current1", "current2",
]

LABEL_MAP = OrderedDict([
    ("normal", 0),
    ("drive_abnormal", 1),
    ("drive_fault", 1),
    ("wheel_slip", 2),
    ("shaft_eccentric", 3),
])

REQUIRED_META_COLS = ["run_id", "fault_label", "fault_name", "timestamp"]

# Fields that must NOT enter model input
EXCLUDED_FIELDS = [
    "timestamp", "run_id", "sample_id", "fault_label", "fault_name",
    "fault_mode", "motion_mode",
    "cmd_vx", "cmd_vy", "cmd_wz",
    "voltage",
    "current_seq", "current_valid", "current_reused_count", "current_dt",
    "odom_time", "imu_time", "voltage_time", "current_time", "cmd_time",
    "odom_age", "imu_age", "voltage_age", "current_age", "cmd_age",
    "record_rate",
    "x", "y", "z", "yaw", "roll", "pitch",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def log(msg):
    print("[build_dataset] %s" % msg)


def warn(msg):
    print("[WARNING] %s" % msg)


def err(msg):
    print("[ERROR] %s" % msg, file=sys.stderr)


def parse_run_number(run_id):
    """Extract trailing number from run_id, e.g. 'normal_003' -> 3."""
    parts = run_id.rsplit("_", 1)
    if len(parts) == 2:
        try:
            return int(parts[1])
        except ValueError:
            pass
    return -1


# ---------------------------------------------------------------------------
# Core pipeline
# ---------------------------------------------------------------------------

def discover_csvs(input_dir, pattern):
    path = os.path.join(input_dir, pattern)
    files = sorted(glob.glob(path))
    log("Discovered %d CSV files in %s" % (len(files), input_dir))
    for f in files:
        log("  %s" % os.path.basename(f))
    return files


def load_and_validate_csv(filepath):
    try:
        df = pd.read_csv(filepath)
    except Exception as e:
        warn("Failed to read %s: %s" % (filepath, e))
        return None

    missing = [c for c in REQUIRED_META_COLS if c not in df.columns]
    if missing:
        warn("Skipping %s: missing columns %s" % (os.path.basename(filepath), missing))
        return None

    if len(df) == 0:
        warn("Skipping %s: empty file" % os.path.basename(filepath))
        return None

    run_ids = df["run_id"].unique()
    if len(run_ids) > 1:
        warn("File %s contains %d run_ids: %s - using first" % (
            os.path.basename(filepath), len(run_ids), list(run_ids)))
        df = df[df["run_id"] == run_ids[0]].reset_index(drop=True)

    return df


def check_wheel_speed(df, feature_set):
    """Return True if wheel_speed columns are usable for 15ch."""
    if feature_set != "15ch":
        return True
    ws_cols = ["wheel_speed0", "wheel_speed1", "wheel_speed2"]
    for c in ws_cols:
        if c not in df.columns:
            warn("Column %s not found - cannot use 15ch" % c)
            return False
    all_zero = all(df[c].abs().sum() == 0 for c in ws_cols)
    if all_zero:
        warn("wheel_speed0/1/2 are all zero - consider --feature_set 12ch")
        return False
    return True


def trim_run(df, run_id, trim_start, trim_end, window_size):
    """Trim start/end seconds from a single run's data."""
    before = len(df)
    if "timestamp" not in df.columns:
        warn("No timestamp column, skipping trim for run %s" % run_id)
        return df if len(df) >= window_size else None

    ts = df["timestamp"].astype(float)
    t0, t1 = ts.iloc[0], ts.iloc[-1]
    duration = t1 - t0

    if duration <= 0:
        warn("Run %s has zero duration, skipping" % run_id)
        return None

    start_t = t0 + trim_start
    end_t = t1 - trim_end

    if start_t >= end_t:
        warn("Run %s: trim too aggressive (duration=%.1fs), skipping" % (run_id, duration))
        return None

    mask = (ts >= start_t) & (ts <= end_t)
    trimmed = df[mask].reset_index(drop=True)
    after = len(trimmed)

    log("  Run %s: %d -> %d rows (trimmed %.1fs from start, %.1fs from end)" % (
        run_id, before, after, trim_start, trim_end))

    if after < window_size:
        warn("Run %s: only %d rows after trim (< window_size %d), skipping" % (
            run_id, after, window_size))
        return None

    return trimmed


def make_windows(df, features, window_size, step_size, fault_label, run_id,
                 fault_name, fault_mode, motion_mode, csv_file):
    """Create sliding windows from a single run's data."""
    # Extract feature matrix
    missing = [c for c in features if c not in df.columns]
    if missing:
        warn("Run %s: missing feature columns %s, filling with 0" % (run_id, missing))
        for c in missing:
            df[c] = 0.0

    mat = df[features].values.astype(np.float32)
    timestamps = df["timestamp"].values if "timestamp" in df.columns else np.arange(len(df))

    windows = []
    metas = []
    n = len(mat)

    for start in range(0, n - window_size + 1, step_size):
        end = start + window_size
        window = mat[start:end].T  # shape [C, T]
        windows.append(window)
        metas.append({
            "run_id": run_id,
            "fault_label": fault_label,
            "fault_name": fault_name,
            "fault_mode": fault_mode,
            "motion_mode": motion_mode,
            "window_start_index": start,
            "window_end_index": end - 1,
            "window_start_time": float(timestamps[start]),
            "window_end_time": float(timestamps[end - 1]),
            "csv_file": csv_file,
        })

    log("  Run %s: %d windows (size=%d, step=%d)" % (run_id, len(windows), window_size, step_size))
    return windows, metas


def split_by_run_id(runs_by_class, allow_same_run):
    """Split runs into train/test by run_id numbering."""
    train_runs = {}
    test_runs = {}
    insufficient = False

    for label, run_ids in sorted(runs_by_class.items()):
        if len(run_ids) < 2:
            insufficient = True
            continue
        # Sort by run number
        sorted_runs = sorted(run_ids, key=parse_run_number)
        # Last run goes to test, rest to train
        train_runs[label] = sorted_runs[:-1]
        test_runs[label] = [sorted_runs[-1]]

    if insufficient and not allow_same_run:
        err("Some classes have < 2 runs. Use --allow_same_run_split for flow validation.")
        return None, None

    if insufficient and allow_same_run:
        warn("=" * 60)
        warn("Some classes have < 2 independent runs.")
        warn("Using same-run time split - ONLY for flow validation!")
        warn("NOT reliable for final results.")
        warn("=" * 60)

    return train_runs, test_runs


def split_windows_same_run(all_windows, all_metas, train_ratio=0.8):
    """Split within each run by time order (first 80% train, last 20% test)."""
    # Group by run_id
    run_windows = {}
    run_metas = {}
    for w, m in zip(all_windows, all_metas):
        rid = m["run_id"]
        if rid not in run_windows:
            run_windows[rid] = []
            run_metas[rid] = []
        run_windows[rid].append(w)
        run_metas[rid].append(m)

    train_w, train_m, test_w, test_m = [], [], [], []
    for rid in sorted(run_windows.keys()):
        ws = run_windows[rid]
        ms = run_metas[rid]
        n = len(ws)
        n_train = max(1, int(n * train_ratio))
        train_w.extend(ws[:n_train])
        train_m.extend(ms[:n_train])
        test_w.extend(ws[n_train:])
        test_m.extend(ms[n_train:])

    return train_w, train_m, test_w, test_m


def scale_data(train_X, test_X, scaler_type):
    """Fit scaler on train, transform both. Input shape [N, C, T]."""
    N_train, C, T = train_X.shape
    N_test = test_X.shape[0]

    # Reshape to [N*T, C] for fitting
    train_flat = train_X.transpose(0, 2, 1).reshape(-1, C)
    test_flat = test_X.transpose(0, 2, 1).reshape(-1, C)

    scaler = StandardScaler()
    train_scaled = scaler.fit_transform(train_flat).reshape(N_train, T, C).transpose(0, 2, 1)
    test_scaled = scaler.transform(test_flat).reshape(N_test, T, C).transpose(0, 2, 1)

    return train_scaled.astype(np.float32), test_scaled.astype(np.float32), scaler


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Build fault diagnosis dataset from CSV logs")
    parser.add_argument("--input_dir", required=True, help="Directory containing raw CSV files")
    parser.add_argument("--output_dir", required=True, help="Output directory for dataset")
    parser.add_argument("--feature_set", default="15ch", choices=["15ch", "12ch"],
                        help="Feature set: 15ch (with wheel_speed) or 12ch (without)")
    parser.add_argument("--window_size", type=int, default=50, help="Sliding window size (default 50)")
    parser.add_argument("--step_size", type=int, default=10, help="Sliding window step (default 10)")
    parser.add_argument("--scaler", default="standard", choices=["standard"],
                        help="Scaler type (default standard)")
    parser.add_argument("--trim_start_sec", type=float, default=5.0,
                        help="Seconds to trim from start of each run (default 5)")
    parser.add_argument("--trim_end_sec", type=float, default=5.0,
                        help="Seconds to trim from end of each run (default 5)")
    parser.add_argument("--allow_same_run_split", action="store_true",
                        help="Allow time-based split within a single run (flow validation only)")
    parser.add_argument("--pattern", default="*.csv", help="Glob pattern for CSV files (default *.csv)")
    args = parser.parse_args()

    # Select features
    features = MODEL_FEATURES_15 if args.feature_set == "15ch" else MODEL_FEATURES_12
    log("=" * 60)
    log("Build Fault Dataset")
    log("=" * 60)
    log("Input dir:    %s" % args.input_dir)
    log("Output dir:   %s" % args.output_dir)
    log("Feature set:  %s (%d features)" % (args.feature_set, len(features)))
    log("Window size:  %d" % args.window_size)
    log("Step size:    %d" % args.step_size)
    log("Scaler:       %s" % args.scaler)
    log("Trim start:   %.1f sec" % args.trim_start_sec)
    log("Trim end:     %.1f sec" % args.trim_end_sec)
    log("Same-run split: %s" % args.allow_same_run_split)
    log("")

    # Validate input dir
    if not os.path.isdir(args.input_dir):
        err("Input directory does not exist: %s" % args.input_dir)
        sys.exit(1)

    # Discover CSVs
    csv_files = discover_csvs(args.input_dir, args.pattern)
    if not csv_files:
        err("No CSV files found in %s" % args.input_dir)
        sys.exit(1)

    # Process each file
    all_dfs = []
    run_info = []  # (run_id, fault_label, fault_name, filepath)
    wheel_speed_ok = True

    for filepath in csv_files:
        df = load_and_validate_csv(filepath)
        if df is None:
            continue

        run_id = str(df["run_id"].iloc[0])
        fault_label = int(df["fault_label"].iloc[0])
        fault_name = str(df["fault_name"].iloc[0])

        # Validate label/name consistency
        if fault_name not in LABEL_MAP:
            warn("Unknown fault_name '%s' in %s, skipping" % (fault_name, os.path.basename(filepath)))
            continue
        expected_label = LABEL_MAP[fault_name]
        if fault_label != expected_label:
            warn("Label mismatch in %s: fault_name=%s expects %d, got %d - using %d" % (
                os.path.basename(filepath), fault_name, expected_label, fault_label, expected_label))
            fault_label = expected_label

        log("Loaded %s: run_id=%s label=%d/%s rows=%d" % (
            os.path.basename(filepath), run_id, fault_label, fault_name, len(df)))

        # Check wheel_speed for first file
        if wheel_speed_ok and args.feature_set == "15ch":
            wheel_speed_ok = check_wheel_speed(df, args.feature_set)

        all_dfs.append((df, filepath, run_id, fault_label, fault_name))

    if not all_dfs:
        err("No valid CSV files loaded")
        sys.exit(1)

    if args.feature_set == "15ch" and not wheel_speed_ok:
        warn("=" * 60)
        warn("wheel_speed data appears unusable for 15ch.")
        warn("Consider re-running with --feature_set 12ch")
        warn("Continuing with 15ch (wheel_speed will be zero-filled)...")
        warn("=" * 60)

    # Trim and window each run
    all_windows = []
    all_metas = []
    runs_by_class = {}  # fault_label -> [run_ids]

    log("")
    log("--- Trimming and windowing ---")

    for df, filepath, run_id, fault_label, fault_name in all_dfs:
        # Track runs per class
        if fault_label not in runs_by_class:
            runs_by_class[fault_label] = []
        if run_id not in runs_by_class[fault_label]:
            runs_by_class[fault_label].append(run_id)

        fault_mode = int(df["fault_mode"].iloc[0]) if "fault_mode" in df.columns else 0
        motion_mode = str(df["motion_mode"].iloc[0]) if "motion_mode" in df.columns else ""

        # Trim
        trimmed = trim_run(df, run_id, args.trim_start_sec, args.trim_end_sec, args.window_size)
        if trimmed is None:
            continue

        # Window
        windows, metas = make_windows(
            trimmed, features, args.window_size, args.step_size,
            fault_label, run_id, fault_name, fault_mode, motion_mode,
            os.path.basename(filepath),
        )
        all_windows.extend(windows)
        all_metas.extend(metas)

    if not all_windows:
        err("No windows generated - check your data")
        sys.exit(1)

    # Split train/test
    log("")
    log("--- Train/test split ---")
    log("Runs per class:")
    for label in sorted(runs_by_class.keys()):
        name = [k for k, v in LABEL_MAP.items() if v == label][0]
        log("  %d (%s): %s" % (label, name, runs_by_class[label]))

    # Check if we need same-run split
    min_runs = min(len(v) for v in runs_by_class.values())
    use_same_run = min_runs < 2

    if use_same_run and not args.allow_same_run_split:
        err("Insufficient runs (min %d per class). Use --allow_same_run_split." % min_runs)
        sys.exit(1)

    if use_same_run:
        train_w, train_m, test_w, test_m = split_windows_same_run(all_windows, all_metas)
        split_method = "same_run_time"
    else:
        train_runs, test_runs = split_by_run_id(runs_by_class, args.allow_same_run_split)
        if train_runs is None:
            sys.exit(1)

        train_w, train_m, test_w, test_m = [], [], [], []
        for w, m in zip(all_windows, all_metas):
            rid = m["run_id"]
            label = m["fault_label"]
            if label in train_runs and rid in train_runs[label]:
                train_w.append(w)
                train_m.append(m)
            elif label in test_runs and rid in test_runs[label]:
                test_w.append(w)
                test_m.append(m)
            else:
                # Shouldn't happen, but default to train
                train_w.append(w)
                train_m.append(m)
        split_method = "by_run_id"

    if not train_w:
        err("No training windows generated")
        sys.exit(1)
    if not test_w:
        warn("No test windows generated - using empty test set")

    log("Split method: %s" % split_method)
    log("Train windows: %d" % len(train_w))
    log("Test windows:  %d" % len(test_w))

    # Stack into arrays
    X_train = np.stack(train_w, axis=0)
    y_train = np.array([m["fault_label"] for m in train_m], dtype=np.int64)
    X_test = np.stack(test_w, axis=0) if test_w else np.empty((0, len(features), args.window_size), dtype=np.float32)
    y_test = np.array([m["fault_label"] for m in test_m], dtype=np.int64) if test_m else np.array([], dtype=np.int64)

    log("")
    log("--- Scaling ---")
    X_train, X_test, scaler = scale_data(X_train, X_test, args.scaler)
    log("Scaler fitted on train: mean shape=%s, scale shape=%s" % (
        scaler.mean_.shape, scaler.scale_.shape))

    # Quality checks
    log("")
    log("--- Quality checks ---")
    log("X_train.shape = %s" % str(X_train.shape))
    log("X_test.shape  = %s" % str(X_test.shape))
    log("y_train.shape = %s, values=%s" % (y_train.shape, np.unique(y_train)))
    log("y_test.shape  = %s, values=%s" % (y_test.shape, np.unique(y_test) if len(y_test) > 0 else "[]"))

    has_nan = np.isnan(X_train).any() or np.isnan(X_test).any() if len(X_test) > 0 else np.isnan(X_train).any()
    has_inf = np.isinf(X_train).any() or np.isinf(X_test).any() if len(X_test) > 0 else np.isinf(X_train).any()
    log("NaN present: %s" % has_nan)
    log("Inf present: %s" % has_inf)
    if has_nan or has_inf:
        warn("NaN or Inf detected in data!")

    # Per-class counts
    log("")
    log("--- Per-class sample counts ---")
    for label in sorted(LABEL_MAP.values()):
        name = [k for k, v in LABEL_MAP.items() if v == label][0]
        n_train = int((y_train == label).sum())
        n_test = int((y_test == label).sum()) if len(y_test) > 0 else 0
        log("  %d (%s): train=%d, test=%d" % (label, name, n_train, n_test))

    log("")
    log("Features used: %s" % features)
    log("Excluded fields: %s" % EXCLUDED_FIELDS[:10])

    # Save output
    os.makedirs(args.output_dir, exist_ok=True)

    np.save(os.path.join(args.output_dir, "X_train.npy"), X_train)
    np.save(os.path.join(args.output_dir, "y_train.npy"), y_train)
    np.save(os.path.join(args.output_dir, "X_test.npy"), X_test)
    np.save(os.path.join(args.output_dir, "y_test.npy"), y_test)

    # Meta CSVs
    meta_train_df = pd.DataFrame(train_m)
    meta_train_df["split"] = "train"
    meta_train_df.to_csv(os.path.join(args.output_dir, "meta_train.csv"), index=False)

    if test_m:
        meta_test_df = pd.DataFrame(test_m)
        meta_test_df["split"] = "test"
        meta_test_df.to_csv(os.path.join(args.output_dir, "meta_test.csv"), index=False)
    else:
        pd.DataFrame(columns=list(train_m[0].keys()) + ["split"]).to_csv(
            os.path.join(args.output_dir, "meta_test.csv"), index=False)

    # Scaler
    import pickle
    with open(os.path.join(args.output_dir, "scaler.pkl"), "wb") as f:
        pickle.dump(scaler, f)

    # Feature config
    feature_config = {
        "features": features,
        "feature_set": args.feature_set,
        "num_features": len(features),
        "window_size": args.window_size,
        "step_size": args.step_size,
        "scaler": args.scaler,
        "trim_start_sec": args.trim_start_sec,
        "trim_end_sec": args.trim_end_sec,
        "num_classes": len(LABEL_MAP),
        "label_map": dict(LABEL_MAP),
        "input_shape": [len(features), args.window_size],
        "train_samples": int(X_train.shape[0]),
        "test_samples": int(X_test.shape[0]),
        "split_method": split_method,
        "created_time": datetime.now().isoformat(timespec="seconds"),
    }
    with open(os.path.join(args.output_dir, "feature_config.json"), "w") as f:
        json.dump(feature_config, f, indent=2, ensure_ascii=False)

    log("")
    log("=" * 60)
    log("Dataset saved to: %s" % args.output_dir)
    log("  X_train.npy  shape=%s dtype=%s" % (X_train.shape, X_train.dtype))
    log("  y_train.npy  shape=%s dtype=%s" % (y_train.shape, y_train.dtype))
    log("  X_test.npy   shape=%s dtype=%s" % (X_test.shape, X_test.dtype))
    log("  y_test.npy   shape=%s dtype=%s" % (y_test.shape, y_test.dtype))
    log("  meta_train.csv  rows=%d" % len(train_m))
    log("  meta_test.csv   rows=%d" % len(test_m))
    log("  scaler.pkl")
    log("  feature_config.json")
    log("=" * 60)


if __name__ == "__main__":
    main()
