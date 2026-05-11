#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Filesystem helpers for web file listing and downloads."""

from __future__ import print_function

import os


def list_csv_files(data_dir):
    if not data_dir or not os.path.isdir(data_dir):
        return []
    entries = []
    for name in sorted(os.listdir(data_dir), reverse=True):
        fp = os.path.join(data_dir, name)
        if os.path.isfile(fp) and name.endswith(".csv"):
            entries.append({
                "name": name,
                "size": os.path.getsize(fp),
                "mtime": os.path.getmtime(fp),
            })
    return entries


def safe_child_file(data_dir, name):
    if not data_dir or not name or ".." in name or "/" in name or "\\" in name:
        return None
    fp = os.path.join(data_dir, name)
    if not os.path.isfile(fp):
        return None
    return fp
