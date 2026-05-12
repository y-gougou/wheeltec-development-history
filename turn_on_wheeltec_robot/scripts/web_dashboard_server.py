#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Static file server for the web teleop dashboard, plus a lightweight
/api/data/ endpoint for listing and downloading recorded CSV files.
"""

import json
import os
import subprocess
import threading
import time
import uuid

import rospy

from core.file_api import list_csv_files, safe_child_file
from core.ros_params import get_int, get_str

try:
    from http.server import SimpleHTTPRequestHandler
except ImportError:
    from SimpleHTTPServer import SimpleHTTPRequestHandler

try:
    from socketserver import TCPServer
except ImportError:
    from SocketServer import TCPServer

try:
    from urllib.parse import parse_qs, unquote, urlparse
except ImportError:
    from urlparse import parse_qs, urlparse
    from urllib import unquote


class ReusableTCPServer(TCPServer):
    allow_reuse_address = True


class DashboardHandler(SimpleHTTPRequestHandler):

    def log_message(self, _format, *_args):
        return

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/data/list":
            self._handle_list(parsed)
        elif parsed.path.startswith("/api/data/download/"):
            self._handle_download(parsed)
        elif parsed.path == "/api/dataset/status":
            self._handle_dataset_status(parsed)
        elif parsed.path == "/api/dataset/list":
            self._handle_dataset_list(parsed)
        else:
            SimpleHTTPRequestHandler.do_GET(self)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/dataset/build":
            self._handle_dataset_build()
        else:
            self._error_response(404, "not found")

    def _data_dir_from_query(self, parsed):
        params = parse_qs(parsed.query or "")
        values = params.get("dir") or []
        if values and values[0]:
            return values[0]
        return self.server.data_dir

    def _handle_list(self, parsed):
        d = self._data_dir_from_query(parsed)
        if not d or not os.path.isdir(d):
            self._json_response({"files": [], "error": "data dir not found"})
            return
        self._json_response({"files": list_csv_files(d), "dir": d})

    def _handle_download(self, parsed):
        name = unquote(parsed.path[len("/api/data/download/"):])
        if not name or ".." in name or "/" in name or "\\" in name:
            self._error_response(400, "invalid filename")
            return
        d = self._data_dir_from_query(parsed)
        if not d:
            self._error_response(404, "data dir not configured")
            return
        fp = safe_child_file(d, name)
        if not fp:
            self._error_response(404, "file not found")
            return
        size = os.path.getsize(fp)
        self.send_response(200)
        self.send_header("Content-Type", "text/csv")
        self.send_header("Content-Disposition", "attachment; filename=\"%s\"" % name)
        self.send_header("Content-Length", str(size))
        self.end_headers()
        with open(fp, "rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                self.wfile.write(chunk)

    # --- Dataset build API ---

    def _read_post_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0:
            return b""
        return self.rfile.read(length)

    def _handle_dataset_build(self):
        body = self._read_post_body()
        try:
            params = json.loads(body) if body else {}
        except (ValueError, TypeError):
            self._error_response(400, "invalid JSON body")
            return

        input_dir = params.get("input_dir", "")
        output_dir = params.get("output_dir", "")
        if not input_dir or not output_dir:
            self._error_response(400, "input_dir and output_dir required")
            return

        feature_set = params.get("feature_set", "15ch")
        window_size = int(params.get("window_size", 50))
        step_size = int(params.get("step_size", 10))
        scaler = params.get("scaler", "standard")
        trim_start = float(params.get("trim_start_sec", 5.0))
        trim_end = float(params.get("trim_end_sec", 5.0))
        allow_same_run = bool(params.get("allow_same_run_split", False))
        pattern = params.get("pattern", "*.csv")

        # Find build script
        pkg_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        script_path = os.path.join(pkg_root, "scripts", "build_fault_dataset.py")
        if not os.path.isfile(script_path):
            self._error_response(500, "build_fault_dataset.py not found at %s" % script_path)
            return

        cmd = [
            "python3", script_path,
            "--input_dir", input_dir,
            "--output_dir", output_dir,
            "--feature_set", feature_set,
            "--window_size", str(window_size),
            "--step_size", str(step_size),
            "--scaler", scaler,
            "--trim_start_sec", str(trim_start),
            "--trim_end_sec", str(trim_end),
            "--pattern", pattern,
        ]
        if allow_same_run:
            cmd.append("--allow_same_run_split")

        build_id = uuid.uuid4().hex[:12]
        build_state = {
            "build_id": build_id,
            "state": "running",
            "log_lines": [],
            "result": None,
            "started_at": time.time(),
        }
        self.server.active_builds[build_id] = build_state

        def run_build():
            try:
                proc = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    bufsize=1,
                )
                for raw_line in proc.stdout:
                    line = raw_line.decode("utf-8", errors="replace").rstrip("\n")
                    build_state["log_lines"].append(line)
                    if len(build_state["log_lines"]) > 500:
                        build_state["log_lines"] = build_state["log_lines"][-500:]
                proc.wait()
                if proc.returncode == 0:
                    build_state["state"] = "done"
                    # Try to load feature_config.json
                    config_path = os.path.join(output_dir, "feature_config.json")
                    if os.path.isfile(config_path):
                        with open(config_path, "r") as f:
                            build_state["result"] = json.load(f)
                else:
                    build_state["state"] = "error"
                    build_state["log_lines"].append("Process exited with code %d" % proc.returncode)
            except Exception as e:
                build_state["state"] = "error"
                build_state["log_lines"].append("Exception: %s" % str(e))

        t = threading.Thread(target=run_build)
        t.daemon = True
        t.start()

        self._json_response({"status": "started", "build_id": build_id})

    def _handle_dataset_status(self, parsed):
        params = parse_qs(parsed.query or "")
        build_id = (params.get("build_id") or [None])[0]
        if not build_id:
            self._error_response(400, "build_id required")
            return

        builds = self.server.active_builds
        if build_id not in builds:
            self._error_response(404, "build not found")
            return

        state = builds[build_id]
        # Return last 100 log lines
        self._json_response({
            "build_id": build_id,
            "state": state["state"],
            "log_lines": state["log_lines"][-100:],
            "result": state["result"],
        })

    def _handle_dataset_list(self, parsed):
        params = parse_qs(parsed.query or "")
        base_dir = (params.get("dir") or [None])[0]
        if not base_dir:
            base_dir = self.server.data_dir
        if not base_dir or not os.path.isdir(base_dir):
            self._json_response({"datasets": []})
            return

        datasets = []
        for name in sorted(os.listdir(base_dir)):
            d = os.path.join(base_dir, name)
            config_path = os.path.join(d, "feature_config.json")
            if os.path.isdir(d) and os.path.isfile(config_path):
                try:
                    with open(config_path, "r") as f:
                        config = json.load(f)
                    datasets.append({"name": name, "path": d, "config": config})
                except Exception:
                    datasets.append({"name": name, "path": d, "config": None})
        self._json_response({"datasets": datasets})

    def _json_response(self, obj, code=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _error_response(self, code, msg):
        self._json_response({"error": msg}, code)


class StaticDashboardServer(object):
    def __init__(self):
        self.host = get_str("~host", "0.0.0.0")
        self.port = get_int("~port", 8000)
        self.data_dir = get_str("~data_dir", "/home/wheeltec/R550PLUS_data_collect/log")
        self.package_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.web_root = os.path.join(self.package_root, "web")
        self.dist_root = os.path.join(self.web_root, "dist")

        if not os.path.isdir(self.web_root):
            raise RuntimeError("Web root does not exist: %s" % self.web_root)

        self.server = None
        self.server_thread = None

    def start(self):
        os.chdir(self.dist_root if os.path.isdir(self.dist_root) else self.web_root)
        self.server = ReusableTCPServer((self.host, self.port), DashboardHandler)
        self.server.data_dir = self.data_dir
        self.server.active_builds = {}
        self.server_thread = threading.Thread(target=self.server.serve_forever)
        self.server_thread.daemon = True
        self.server_thread.start()
        rospy.on_shutdown(self.shutdown)
        rospy.loginfo(
            "web dashboard started http://%s:%d (web=%s, data=%s)",
            self.host, self.port, os.getcwd(), self.data_dir,
        )

    def shutdown(self):
        if self.server is not None:
            try:
                self.server.shutdown()
                self.server.server_close()
            except Exception:
                pass
            self.server = None


if __name__ == "__main__":
    rospy.init_node("web_dashboard_server", anonymous=False)
    server = StaticDashboardServer()
    server.start()
    rospy.spin()
