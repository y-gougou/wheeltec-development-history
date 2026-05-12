# turn_on_wheeltec_robot

WHEELTEC omni-directional chassis ROS package.

This package has been reorganized around four responsibilities:

- Chassis command protocol and angle-control command routing.
- Browser-based driving console built with React + Vite.
- Runtime CSV data collection and download.
- N100 IMU heading normalization before heading data is sent to the chassis.

The old workflow required four terminals for chassis startup, current-board checking,
CSV collection, and Web control. The recommended workflow now uses one launch entry
and controls collection from the Web page.

---

## 1. Recommended Startup

Daily use:

```bash
roslaunch turn_on_wheeltec_robot web_control.launch
```

This starts, by default:

- `wheeltec_robot_node`, the STM32 chassis serial node.
- `heading_bridge.py`, started by the base serial include.
- `cmd_vel_web_adapter.py`, the Web command safety adapter.
- `current_reader.py`, the current-board serial reader.
- `data_collector.py`, the CSV collection node.
- `rosbridge_websocket`, used by the Web frontend.
- `web_dashboard_server.py`, the static Web server and CSV file API.

Open the Web console:

```text
http://<robot-ip>:8000/
```

The frontend connects to rosbridge by default:

```text
ws://<robot-ip>:9090
```

### Optional Startup Switches

Disable modules when they are already running or not needed:

```bash
roslaunch turn_on_wheeltec_robot web_control.launch \
  start_base:=false \
  start_current_reader:=false \
  start_data_collector:=false
```

Start the N100 fdilink AHRS driver together with this package:

```bash
roslaunch turn_on_wheeltec_robot web_control.launch \
  start_fdilink_ahrs:=true
```

If you start fdilink manually, use:

```bash
roslaunch fdilink_ahrs ahrs_data.launch
roslaunch turn_on_wheeltec_robot web_control.launch
```

`data_collector.launch` can also start fdilink when explicitly requested:

```bash
roslaunch turn_on_wheeltec_robot data_collector.launch \
  start_fdilink_ahrs:=true \
  imu_topic:=/n100/imu
```

Launching `data_collector.launch imu_topic:=/n100/imu` alone only changes the
subscription topic. It does not start `fdilink_ahrs` unless `start_fdilink_ahrs:=true`
is also passed.

---

## 2. Launch Parameters

`web_control.launch` is the main entry point.

Common parameters:

| Parameter | Default | Meaning |
| --- | --- | --- |
| `start_base` | `true` | Start chassis serial node and heading bridge. |
| `start_current_reader` | `true` | Start current-board reader. |
| `start_data_collector` | `true` | Start CSV collector. |
| `start_fdilink_ahrs` | `false` | Include `fdilink_ahrs/ahrs_data.launch`. |
| `rosbridge_host` | `0.0.0.0` | rosbridge bind address. |
| `rosbridge_port` | `9090` | rosbridge port. |
| `web_host` | `0.0.0.0` | Web server bind address. |
| `web_port` | `8000` | Web server port. |
| `current_port` | `/dev/ttyUSB1` | Current-board serial port. |
| `output_dir` | `/home/wheeltec/R550PLUS_data_collect/log_v2` | CSV output directory. |
| `fault_label` | `0` | Numeric fault label. |
| `fault_name` | `normal` | Fault name stored in CSV. |
| `fault_mode` | `0` | Extra fault mode field. |
| `run_id` | empty | CSV run id. Empty means auto-generated. |
| `motion_mode` | `straight_back_forth_0.25ms` | Motion description stored in CSV. |
| `expected_rate` | `20.0` | Expected collection rate stored in CSV. |
| `imu_topic` | `/imu` | IMU topic used by `data_collector.py`. |

Example with explicit collection parameters:

```bash
roslaunch turn_on_wheeltec_robot web_control.launch \
  current_port:=/dev/ttyUSB1 \
  output_dir:=/home/wheeltec/R550PLUS_data_collect/log_v2 \
  fault_label:=0 \
  fault_name:=normal \
  fault_mode:=0 \
  run_id:=normal_001 \
  motion_mode:=straight_back_forth_0.25ms \
  expected_rate:=20.0
```

For N100 IMU data collection:

```bash
roslaunch turn_on_wheeltec_robot web_control.launch \
  start_fdilink_ahrs:=true \
  imu_topic:=/n100/imu
```

---

## 3. Web Console

The Web UI was rewritten with React + Vite.

Source:

```text
web/src/
```

Build output:

```text
web/dist/
```

Build command:

```bash
cd web
npm run build
```

Development preview:

```bash
cd web
npm run dev -- --host 0.0.0.0 --port 5173
```

### Web Sections

The current Web console contains:

- Status monitoring:
  - ROS connection state.
  - Control state.
  - Cruise state.
  - Collection state.
  - Battery voltage.
  - IMU angular velocity.
  - Standard heading from `/chassis/heading_deg`.
  - Heading source/status from `/web/heading_status`.
  - Odom velocities and position.
  - Current-board data.
- Manual driving:
  - Virtual joystick.
  - Keyboard control.
  - Stop.
  - E-stop and release.
- Cruise control:
  - Direction pad.
  - Cruise speed slider.
  - Target velocity display.
  - Actual velocity display from `/web/cruise_status`.
- Heading angle control:
  - Target angle input.
  - Send target angle.
  - Set current heading as zero.
- Data collection:
  - Start collection.
  - Stop collection.
  - Reconnect current board.
  - Refresh CSV files.
  - Download CSV files.
  - Advanced collection parameters.

### Keyboard Mapping

| Key | Action |
| --- | --- |
| `W` / arrow up | Forward. |
| `S` / arrow down | Backward. |
| `Q` | Strafe left. |
| `E` | Strafe right. |
| `A` / arrow left | Manual left turn through `angular.z`. |
| `D` / arrow right | Manual right turn through `angular.z`. |
| `Shift` | Higher speed scale. |
| `Space` | Stop. |

Left/right keys are manual turn commands. They do not publish a target angle.

---

## 4. Command Architecture

The system separates speed commands from heading target commands.

### Speed Path

Manual driving and cruise ultimately produce speed commands:

```text
Web frontend
  -> /cmd_vel_web
  -> cmd_vel_web_adapter.py
  -> /cmd_vel
  -> wheeltec_robot_node
  -> STM32 serial frame
```

For manual driving, the frontend continuously publishes `/cmd_vel_web`.

For cruise driving, the frontend publishes:

```text
/web/cruise_cmd      geometry_msgs/Twist
/web/cruise_enable   std_msgs/Bool
```

Formal cruise mode sends:

```text
linear.x = direction.x * cruise_speed
linear.y = direction.y * cruise_speed
angular.z = 0
```

The adapter keeps velocity PID correction on `linear.x` and `linear.y`.
Cruise `angular.z` is intentionally not PID-controlled by ROS. Heading hold is
left to the STM32 angle loop.

### Heading Target Path

Target heading commands are independent:

```text
/target_angle        std_msgs/Float32, unit: degree
/target_angle_reset  std_msgs/Empty
```

`/target_angle` updates the chassis target angle.
`/target_angle_reset` asks the chassis to treat the current direction as zero.

The Web "set current to 0" button also publishes:

```text
/web/heading_zero    std_msgs/Empty
```

This keeps the ROS-standardized heading zero point aligned with the chassis zero point.

---

## 5. Chassis Serial Protocol Changes

The ROS chassis node sends a 13-byte frame to STM32.

The third byte, `tx[2]`, is now used as the angle-control flag:

| `tx[2]` | Meaning |
| --- | --- |
| `0` | Normal speed frame. Parse `vx`, `vy`, `wz`; do not update target angle. |
| `1` | Target angle frame. Parse target angle from `tx[9:10]`, unit `0.1 deg`. |
| `2` | Set current heading as zero. STM32 should set yaw zero and sync target angle to `0`. |
| `3` | External heading measurement frame. ROS sends standardized heading to STM32. |

ROS implementation:

- `Cmd_Vel_Callback()` sends flag `0`.
- `Angle_Callback()` sends flag `1`.
- `Angle_Reset_Callback()` sends flag `2`.
- `Heading_Callback()` subscribes `/chassis/heading_deg` and sends flag `3`.

Important behavior:

- `angular.z` always means manual turn speed.
- Target heading only comes from `/target_angle`.
- Heading zero only comes from `/target_angle_reset` and `/web/heading_zero`.
- Cruise does not change target heading.

---

## 6. STM32 Angle-Loop Interaction

The intended STM32 behavior is:

- Before self-check and IMU calibration are complete, do not respond to motion commands.
- Each control cycle computes the current heading.
- If a zero command is received, set the current heading as zero and clear angle PID state.
- If `Move_Z` is non-zero, treat it as manual turning:
  - Run normal speed control.
  - Disable heading hold for that cycle.
  - Synchronize `Target_Angle = Current_Angle` so the vehicle does not rebound after the key is released.
- If `Move_Z` is zero, apply heading hold:
  - Compute corrected yaw speed from angle PID.
  - Call the motor driver with `Move_X`, `Move_Y`, and corrected yaw speed together.
  - Do not clear `Move_X` or `Move_Y` while correcting heading.

This is the key point for continuous driving:

```text
Drive_Motor(Move_X, Move_Y, corrected_Vz)
```

Do not implement heading correction by stopping translation, turning in place, then resuming.
If the robot still "moves, stops, turns, moves", reduce the moving-state heading correction limit
or tune the angle PID output limit before changing ROS cruise logic.

---

## 7. N100 IMU Heading Standardization

The preferred architecture is:

```text
/n100/imu
  -> heading_bridge.py
  -> /chassis/heading_deg
  -> wheeltec_robot_node
  -> STM32 external heading frame, tx[2] = 3
```

`heading_bridge.py`:

- Subscribes `sensor_msgs/Imu`.
- Converts quaternion orientation to yaw.
- Unwraps yaw across the `180 / -180` boundary.
- Applies a zero offset.
- Publishes normalized heading in degrees.
- Publishes JSON status for Web monitoring.

Default topics:

| Topic | Type | Meaning |
| --- | --- | --- |
| `/n100/imu` | `sensor_msgs/Imu` | Raw N100 IMU input. |
| `/chassis/heading_deg` | `std_msgs/Float32` | Standard heading in degrees. |
| `/web/heading_status` | `std_msgs/String` | JSON heading status. |
| `/web/heading_zero` | `std_msgs/Empty` | Set current ROS heading to zero. |
| `/web/heading_offset` | `std_msgs/Float32` | Manually set heading zero offset. |

`heading_bridge.py` is started by `launch/include/base_serial.launch` when
`start_heading_bridge:=true`, which is the default.

The N100 driver itself is not always started by default. Enable it with:

```bash
roslaunch turn_on_wheeltec_robot web_control.launch start_fdilink_ahrs:=true
```

or start it separately:

```bash
roslaunch fdilink_ahrs ahrs_data.launch
```

---

## 8. Data Collection

`data_collector.py` now has an explicit state machine:

```text
idle -> collecting -> stopped
              |
              -> error
```

The node opens a CSV file only when collection starts.
Stopping collection closes the current CSV file.

Control topics:

| Topic | Type | Meaning |
| --- | --- | --- |
| `/web/collection_enable` | `std_msgs/Bool` | Start or stop recording. |
| `/web/collection_config` | `std_msgs/String` | JSON runtime configuration. |
| `/web/collection_status` | `std_msgs/String` | JSON status for the Web page. |

Runtime config JSON fields:

```json
{
  "output_dir": "/home/wheeltec/R550PLUS_data_collect/log_v2",
  "fault_label": 0,
  "fault_name": "normal",
  "fault_mode": 0,
  "run_id": "normal_001",
  "motion_mode": "straight_back_forth_0.25ms",
  "expected_rate": 20.0,
  "start": true
}
```

CSV rows are triggered by `/odom`. Other sources are cached and written as the latest
known values. The schema is intentionally kept compatible with the previous collector.

Main input topics:

| Topic | Type | CSV usage |
| --- | --- | --- |
| `/odom` | `nav_msgs/Odometry` | Row trigger, odom velocity and position timing. |
| `/imu` or `/n100/imu` | `sensor_msgs/Imu` | Acceleration and angular velocity. |
| `/PowerVoltage` | `std_msgs/Float32` | Battery voltage. |
| `/current_data` | `std_msgs/Float32MultiArray` | Three current channels and sequence. |
| `/cmd_vel` | `geometry_msgs/Twist` | Commanded chassis velocity. |

For N100 IMU in the CSV:

```bash
roslaunch turn_on_wheeltec_robot web_control.launch \
  start_fdilink_ahrs:=true \
  imu_topic:=/n100/imu
```

---

## 9. Current Board Reader

`current_reader.py` reads the current board and publishes:

```text
/current_data    std_msgs/Float32MultiArray
```

Expected frame formats:

```text
$CURRENT,ch0,ch1,ch2*XX
$CURRENT,seq,ch0,ch1,ch2*XX
```

`XX` is the XOR checksum from `$` to before `*`.

Runtime config topic:

```text
/web/current_reader_config    std_msgs/String
```

Example:

```bash
rostopic pub /web/current_reader_config std_msgs/String \
  'data: "{\"port\":\"/dev/ttyUSB0\",\"reconnect\":true}"' -1
```

Status topic:

```text
/web/current_reader_status    std_msgs/String
```

The Web page uses this to reconnect `/dev/ttyUSB0` or `/dev/ttyUSB1` without
restarting the full launch file.

---

## 10. CSV File API

`web_dashboard_server.py` serves both the frontend and CSV files.

Endpoints:

| Endpoint | Meaning |
| --- | --- |
| `GET /api/data/list?dir=<dir>` | List CSV files in a directory. |
| `GET /api/data/download/<filename>?dir=<dir>` | Download one CSV file. |

The server validates filenames and only serves direct child files from the selected directory.

The Web page passes the currently configured `output_dir` to these endpoints, so changing
the output directory in the UI also changes the file list and download source.

---

## 11. Script Refactor

Reusable logic was moved under `scripts/core/`:

| File | Responsibility |
| --- | --- |
| `control_utils.py` | PID, clamp, zero twist helpers. |
| `csv_utils.py` | CSV writer, run id, unique CSV path. |
| `file_api.py` | CSV file listing and safe file lookup. |
| `ros_params.py` | Typed ROS parameter helpers. |
| `serial_utils.py` | Serial open/retry/close and checksum helpers. |
| `time_utils.py` | Timestamp, age, and float formatting helpers. |

Entry scripts remain focused:

| Script | Responsibility |
| --- | --- |
| `current_reader.py` | Read current board and publish `/current_data`. |
| `data_collector.py` | Record synchronized CSV rows. |
| `cmd_vel_web_adapter.py` | Safety adapter, manual command shaping, cruise control. |
| `heading_bridge.py` | Convert `/n100/imu` to standardized heading. |
| `web_dashboard_server.py` | Serve Web UI and CSV download API. |

---

## 12. ROS Topic Summary

### Web Driving

| Topic | Type | Direction | Meaning |
| --- | --- | --- | --- |
| `/cmd_vel_web` | `geometry_msgs/Twist` | Web -> ROS | Manual driving command. |
| `/web/heartbeat` | `std_msgs/Empty` | Web -> ROS | Browser alive signal. |
| `/web/estop` | `std_msgs/Bool` | Web -> ROS | Emergency stop latch. |
| `/web/control_status` | `std_msgs/String` | ROS -> Web | Adapter state. |

### Cruise

| Topic | Type | Direction | Meaning |
| --- | --- | --- | --- |
| `/web/cruise_cmd` | `geometry_msgs/Twist` | Web -> ROS | Cruise target velocity. |
| `/web/cruise_enable` | `std_msgs/Bool` | Web -> ROS | Enable or disable cruise. |
| `/web/cruise_status` | `std_msgs/String` | ROS -> Web | Target vs actual velocity. |

### Heading

| Topic | Type | Direction | Meaning |
| --- | --- | --- | --- |
| `/target_angle` | `std_msgs/Float32` | Web/ROS -> chassis node | Target heading in degrees. |
| `/target_angle_reset` | `std_msgs/Empty` | Web/ROS -> chassis node | Set current chassis heading as zero. |
| `/n100/imu` | `sensor_msgs/Imu` | IMU driver -> ROS | Raw N100 IMU. |
| `/chassis/heading_deg` | `std_msgs/Float32` | heading bridge -> chassis node | Standard heading in degrees. |
| `/web/heading_status` | `std_msgs/String` | heading bridge -> Web | JSON status. |
| `/web/heading_zero` | `std_msgs/Empty` | Web -> heading bridge | Set ROS heading zero. |

### Collection

| Topic | Type | Direction | Meaning |
| --- | --- | --- | --- |
| `/web/collection_enable` | `std_msgs/Bool` | Web -> collector | Start or stop CSV recording. |
| `/web/collection_config` | `std_msgs/String` | Web -> collector | Runtime JSON config. |
| `/web/collection_status` | `std_msgs/String` | collector -> Web | JSON collection status. |
| `/web/current_reader_config` | `std_msgs/String` | Web -> current reader | Runtime serial config. |
| `/web/current_reader_status` | `std_msgs/String` | current reader -> Web | JSON current-reader status. |

---

## 13. Typical Test Flow

### Startup

```bash
roslaunch turn_on_wheeltec_robot web_control.launch start_fdilink_ahrs:=true imu_topic:=/n100/imu
```

Check key topics:

```bash
rostopic hz /n100/imu
rostopic echo /chassis/heading_deg
rostopic echo /web/heading_status
rostopic echo /web/control_status
```

### Manual Driving

1. Open `http://<robot-ip>:8000/`.
2. Connect rosbridge.
3. Use `W/S`, `Q/E`, `A/D`, or arrow keys.
4. Release `A/D` or left/right arrows.
5. The vehicle should keep the new heading instead of rebounding.

### Cruise

1. Select forward direction.
2. Set speed, for example `0.20 m/s`.
3. Start cruise.
4. Confirm:

```bash
rostopic echo /web/cruise_cmd
```

Expected:

```text
linear.x = 0.2
linear.y = 0.0
angular.z = 0.0
```

The robot should keep translating while STM32 heading correction runs.

### Target Angle

```bash
rostopic pub /target_angle std_msgs/Float32 'data: 30.0' -1
```

Expected:

- Chassis turns to around 30 degrees.
- It holds the target heading after the turn.

### Set Current Heading as Zero

```bash
rostopic pub /target_angle_reset std_msgs/Empty '{}' -1
rostopic pub /web/heading_zero std_msgs/Empty '{}' -1
```

Expected:

- Current direction becomes zero for STM32 and ROS heading display.
- Publishing `/target_angle 0.0` should not cause a turn.

### Data Collection

From Web:

1. Confirm `current_port`, `output_dir`, `run_id`, and labels.
2. Click start collection.
3. Drive the vehicle.
4. Click stop collection.
5. Refresh files.
6. Download the CSV.

Command-line equivalent:

```bash
rostopic pub /web/collection_config std_msgs/String \
  'data: "{\"run_id\":\"normal_001\",\"fault_label\":0,\"fault_name\":\"normal\",\"motion_mode\":\"straight_back_forth_0.25ms\",\"expected_rate\":20.0,\"start\":true}"' -1

rostopic pub /web/collection_enable std_msgs/Bool 'data: true' -1
rostopic pub /web/collection_enable std_msgs/Bool 'data: false' -1
```

---

## 14. Troubleshooting

### Web connects but robot does not move

Check:

```bash
rostopic echo /web/control_status
rostopic echo /cmd_vel_web
rostopic echo /cmd_vel
```

Common causes:

- rosbridge is not connected.
- `/web/heartbeat` is not arriving, so adapter stays in `waiting_heartbeat`.
- E-stop is latched.
- `start_base:=false` was used and chassis node is not running.
- STM32 is still in self-check or IMU calibration stage.

### N100 heading is not shown

Check:

```bash
rostopic list | grep n100
rostopic hz /n100/imu
rostopic echo /chassis/heading_deg
```

Common causes:

- `fdilink_ahrs` was not started.
- N100 is on a different serial port.
- `heading_bridge.py` is running but subscribing to the wrong `heading_imu_topic`.

### CSV does not start

Check:

```bash
rostopic echo /web/collection_status
rostopic echo /web/current_reader_status
rostopic echo /current_data
```

Common causes:

- `require_current_before_record:=true` and no current frame is received.
- Wrong `current_port`.
- `output_dir` does not exist or is not writable.

### Cruise moves, stops, turns, and moves again

This is not a Web cruise problem if `/web/cruise_cmd.angular.z` is `0`.

The intended fix is on STM32:

- Keep `Move_X` and `Move_Y` active during angle correction.
- Apply heading PID output as `corrected_Vz`.
- Reduce moving-state heading correction limit if correction is too aggressive.

---

## 15. Notes for Maintenance

- Keep comments in English when editing code.
- Remove mojibake comments when touching nearby code.
- Do not mix target angle commands into `/cmd_vel` or `/cmd_vel_web`.
- Keep `/web/cruise_cmd.angular.z` at `0` for normal cruise.
- Keep CSV schema stable unless downstream training scripts are updated together.
- `README_0511.md` is now only a migration note; this file is the main documentation.
