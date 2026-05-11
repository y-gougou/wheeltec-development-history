#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""CSV output helpers for data collection scripts."""

from __future__ import print_function

import csv
import os

from core.time_utils import datestamp


def ensure_dir(path):
    if path and not os.path.exists(path):
        os.makedirs(path)


def default_run_id(prefix):
    return "%s_%s" % (prefix, datestamp())


def unique_csv_path(output_dir, run_id):
    ensure_dir(output_dir)
    filename = "%s.csv" % run_id
    filepath = os.path.join(output_dir, filename)
    if os.path.exists(filepath):
        filename = "%s_%s.csv" % (run_id, datestamp())
        filepath = os.path.join(output_dir, filename)
    return filepath


class CsvRowWriter(object):
    def __init__(self, filepath, fields):
        self.filepath = filepath
        self.fileobj = open(filepath, "w")
        self.writer = csv.DictWriter(self.fileobj, fieldnames=fields)
        self.writer.writeheader()
        self.fileobj.flush()

    def writerow(self, row):
        self.writer.writerow(row)

    def flush(self):
        if self.fileobj:
            self.fileobj.flush()

    def close(self):
        if self.fileobj:
            self.fileobj.flush()
            self.fileobj.close()
            self.fileobj = None
            self.writer = None
