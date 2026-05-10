#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Current sensor reader node
Reads $CURRENT,ch0,ch1,ch2*XX\r\n format current data and publishes to ROS topic

Serial port: auto, /dev/current_sensor, /dev/ttyUSB0, or /dev/ttyUSB1
Protocol: Text format with XOR checksum
          Format: $CURRENT,-0.0391,-0.0287,-0.1038*7E\r\n
          Checksum: XOR of all bytes from $ to * (exclusive)

Baud rate: 115200

    Published topic: /current_data (std_msgs/Float32MultiArray)
    data[0] = current0 (firmware g_current_values[1], M2)
    data[1] = current1 (firmware g_current_values[2], M3)
    data[2] = current2 (firmware g_current_values[3], M4)
    data[3] = optional seq if firmware sends $CURRENT,seq,ch0,ch1,ch2*XX

Usage:
    rosrun turn_on_wheeltec_robot current_reader.py _port:=auto _baud:=115200
    rosrun turn_on_wheeltec_robot current_reader.py _port:=/dev/current_sensor _baud:=115200
"""

import glob
import os
import sys
import time

import rospy
import serial
from std_msgs.msg import Float32MultiArray

FRAME_HEADER = "$CURRENT,"
FRAME_TAIL = "*"
FRAME_END = "\r\n"


class CurrentReader:
    def __init__(self):
        rospy.init_node('current_reader', anonymous=True)

        # Parameters
        self.port = rospy.get_param('~port', 'auto')
        self.baud = rospy.get_param('~baud', 115200)
        self.timeout = rospy.get_param('~timeout', 1.0)
        self.candidate_ports = rospy.get_param(
            '~candidate_ports',
            '/dev/current_sensor,/dev/serial/by-id/*,/dev/ttyUSB0,/dev/ttyUSB1,/dev/ttyUSB2,/dev/ttyUSB3'
        )
        self.probe_timeout = float(rospy.get_param('~probe_timeout', 2.0))

        # Publisher
        self.pub = rospy.Publisher('/current_data', Float32MultiArray, queue_size=10)

        # Statistics
        self.frame_count = 0
        self.timeout_count = 0
        self.parse_error_count = 0
        self.checksum_error_count = 0
        self.last_report_time = rospy.Time.now().to_sec()
        self.last_seq = -1

        # Open serial port.  USB serial device numbers may swap between
        # ttyUSB0 and ttyUSB1, so "auto" probes ports for a valid CURRENT frame.
        self.serial_port = self.open_current_port()

        # Clear buffer
        self.serial_port.reset_input_buffer()

    def get_candidate_ports(self):
        """Return a stable, de-duplicated list of serial port candidates."""
        if self.port and self.port != 'auto':
            return [self.port]

        ports = []
        for item in self.candidate_ports.split(','):
            pattern = item.strip()
            if not pattern:
                continue
            matched = glob.glob(pattern) if any(ch in pattern for ch in ['*', '?', '[']) else [pattern]
            for port in sorted(matched):
                if port not in ports:
                    ports.append(port)
        return ports

    def open_serial(self, port, timeout=None):
        return serial.Serial(
            port=port,
            baudrate=self.baud,
            timeout=self.timeout if timeout is None else timeout
        )

    def probe_current_port(self, port):
        """Return an opened serial handle if a port is sending valid CURRENT frames."""
        if not os.path.exists(port):
            return None

        try:
            ser = self.open_serial(port, timeout=0.2)
        except serial.SerialException as e:
            rospy.logwarn("Skip serial candidate %s: %s" % (port, e))
            return None

        deadline = time.time() + self.probe_timeout
        try:
            ser.reset_input_buffer()
            while time.time() < deadline and not rospy.is_shutdown():
                line = ser.readline()
                if not line:
                    continue
                try:
                    line = line.decode('ascii', errors='ignore')
                except Exception:
                    continue
                if FRAME_HEADER in line and self.parse_frame(line):
                    rospy.loginfo("Detected current sensor on %s" % port)
                    ser.timeout = self.timeout
                    ser.reset_input_buffer()
                    return ser
        except serial.SerialException as e:
            rospy.logwarn("Probe failed on %s: %s" % (port, e))

        try:
            ser.close()
        except Exception:
            pass
        return None

    def open_current_port(self):
        ports = self.get_candidate_ports()
        if not ports:
            raise serial.SerialException("No serial candidates for current sensor")

        if self.port and self.port != 'auto':
            rospy.loginfo("Opening current serial port: %s @ %d" % (self.port, self.baud))
            ser = self.open_serial(self.port)
            rospy.loginfo("Serial port opened: %s" % ser.name)
            return ser

        rospy.loginfo("Auto-detecting current sensor serial port from: %s" % ', '.join(ports))
        for port in ports:
            ser = self.probe_current_port(port)
            if ser:
                rospy.loginfo("Current serial port opened: %s @ %d" % (ser.name, self.baud))
                self.port = port
                return ser

        raise serial.SerialException(
            "Cannot find current sensor. Tried: %s. "
            "Check wiring, baudrate, and whether the board is sending $CURRENT frames."
            % ', '.join(ports)
        )

    def parse_frame(self, line):
        """
        Parse $CURRENT,ch0,ch1,ch2*XX\r\n frame
        Returns: [ch0, ch1, ch2] or [ch0, ch1, ch2, seq] or None
        """
        try:
            # Align to frame header. Some USB-serial adapters may leave a
            # partial line in the buffer when the node starts.
            header_pos = line.find(FRAME_HEADER)
            if header_pos < 0:
                self.parse_error_count += 1
                return None
            if header_pos > 0:
                line = line[header_pos:]

            # Find checksum separator
            if FRAME_TAIL not in line:
                self.parse_error_count += 1
                return None

            # Extract data between $CURRENT, and *
            data_start = len(FRAME_HEADER)
            data_end = line.index(FRAME_TAIL, data_start)
            data_str = line[data_start:data_end]

            # Extract received checksum
            checksum_start = data_end + 1
            checksum_end = line.find(FRAME_END, checksum_start)
            if checksum_end == -1:
                # Try without \r\n
                recv_checksum_str = line[checksum_start:]
            else:
                recv_checksum_str = line[checksum_start:checksum_end]

            # Parse current values.  The firmware normally sends three values:
            #   $CURRENT,ch0,ch1,ch2*XX
            # A future extended text frame may add a sequence prefix:
            #   $CURRENT,seq,ch0,ch1,ch2*XX
            parts = data_str.split(',')
            seq = None
            if len(parts) == 4:
                try:
                    seq = int(float(parts[0]))
                except ValueError:
                    self.parse_error_count += 1
                    rospy.logwarn_throttle(5, "Invalid current seq: %s" % parts[0])
                    return None
                parts = parts[1:]
            if len(parts) != 3:
                self.parse_error_count += 1
                rospy.logwarn_throttle(5, "Expected 3 current channels, got %d" % len(parts))
                return None

            values = []
            for p in parts:
                try:
                    val = float(p)
                    values.append(val)
                except ValueError:
                    self.parse_error_count += 1
                    rospy.logwarn_throttle(5, "Invalid float value: %s" % p)
                    return None

            # Calculate checksum (XOR from $ to * exclusive)
            calc_checksum = 0
            for i in range(data_end):
                calc_checksum ^= ord(line[i])

            # Parse received checksum
            try:
                recv_checksum = int(recv_checksum_str, 16)
            except ValueError:
                self.parse_error_count += 1
                rospy.logwarn_throttle(5, "Invalid checksum format: %s" % recv_checksum_str)
                return None

            # Verify checksum
            if calc_checksum != recv_checksum:
                self.checksum_error_count += 1
                rospy.logwarn_throttle(5, "Checksum mismatch: calc=0x%02X, recv=0x%02X" % (calc_checksum, recv_checksum))
                return None

            if seq is not None:
                self.last_seq = seq
                values.append(float(seq))
            return values

        except Exception as e:
            self.parse_error_count += 1
            rospy.logdebug("Parse frame failed: %s" % e)
        return None

    def read_frame(self):
        """
        Read one frame of data
        Returns: [ch0, ch1, ch2] or None
        """
        try:
            line = self.serial_port.readline()
            if not line:
                self.timeout_count += 1
                return None

            try:
                line = line.decode('ascii', errors='ignore')
            except Exception:
                self.parse_error_count += 1
                return None

            return self.parse_frame(line)
        except Exception as e:
            rospy.logdebug("Read failed: %s" % e)
            return None

    def run(self):
        """Main loop"""
        rate = rospy.Rate(100)  # 100Hz
        rospy.loginfo("Start reading current data (3-channel omnidirectional robot)...")

        while not rospy.is_shutdown():
            try:
                data = self.read_frame()
                if data:
                    msg = Float32MultiArray()
                    msg.data = data
                    self.pub.publish(msg)
                    self.frame_count += 1

                # Print statistics every 10 seconds
                now = rospy.Time.now().to_sec()
                if now - self.last_report_time >= 10.0:
                    measured_rate = self.frame_count / max(1e-6, now - self.last_report_time)
                    rospy.loginfo(
                        "Current reader: %.1f Hz, ok=%d, timeout=%d, parse_error=%d, checksum_error=%d, last_seq=%d",
                        measured_rate,
                        self.frame_count,
                        self.timeout_count,
                        self.parse_error_count,
                        self.checksum_error_count,
                        self.last_seq,
                    )
                    self.frame_count = 0
                    self.timeout_count = 0
                    self.parse_error_count = 0
                    self.checksum_error_count = 0
                    self.last_report_time = now

            except serial.SerialException as e:
                rospy.logerr("Serial error: %s" % e)
                break
            except KeyboardInterrupt:
                rospy.loginfo("User interrupt")
                break

            rate.sleep()

        # Close serial port
        if hasattr(self, 'serial_port') and self.serial_port.is_open:
            self.serial_port.close()
            rospy.loginfo("Serial port closed")
            rospy.loginfo(
                "Final statistics: ok=%d timeout=%d parse_error=%d checksum_error=%d",
                self.frame_count,
                self.timeout_count,
                self.parse_error_count,
                self.checksum_error_count,
            )


if __name__ == '__main__':
    try:
        reader = CurrentReader()
        reader.run()
    except rospy.ROSInterruptException:
        pass
    except Exception as e:
        rospy.logerr("Startup failed: %s" % e)
        sys.exit(1)
