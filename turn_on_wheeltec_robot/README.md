# R550PLUS 故障诊断数据采集说明

本文档只保留当前阶段需要的流程：先采到可用、规范、可靠的二分类数据集。暂时不训练复杂模型，不修改底盘 24 字节协议，不加入轮速字段作为模型输入。

## 当前目标

第一版只做二分类：

| fault_label | fault_name | 说明 |
| --- | --- | --- |
| 0 | normal | 正常运行 |
| 1 | drive_fault | 驱动异常 |

标准采集链路：

```text
底盘固件 DATA_task 20Hz
  -> wheeltec_robot.cpp
  -> /odom /imu /PowerVoltage

电流采集板约 86Hz 实测
  -> current_reader.py
  -> /current_data

data_collector.py
  -> 以 /odom 触发，20Hz 写 CSV
  -> 其他话题使用最新缓存值

build_fault_dataset.py
  -> 按 run_id 划分训练/测试
  -> 生成 X_train.npy / y_train.npy / X_test.npy / y_test.npy
```

当前实测电流话题：

```text
/current_data average rate: about 86Hz
parse_error=0
checksum_error=0
```

## 第一版模型特征

`build_fault_dataset.py` 默认只使用下面 12 个核心特征：

```text
odom_vx, odom_vy, odom_wz,
imu_ax, imu_ay, imu_az,
imu_gx, imu_gy, imu_gz,
current0, current1, current2
```

下面字段可以保留在 raw CSV 或 meta CSV 中，但不能进入第一版 `X_train.npy`：

```text
timestamp, run_id, sample_id, fault_name, fault_mode, motion_mode,
record_rate,
odom_time, imu_time, voltage_time, current_time, cmd_time,
odom_age, imu_age, voltage_age, current_age, cmd_age,
current_dt, current_seq, current_valid, current_reused_count,
x, y, z, voltage,
cmd_vx, cmd_vy, cmd_wz,
wheel_speed0, wheel_speed1, wheel_speed2
```

## 启动顺序

建议分三个终端启动，避免节点重复启动和串口占用。

### 1. 启动底盘

终端 1：

```bash
roslaunch turn_on_wheeltec_robot turn_on_wheeltec_robot.launch
```

检查底盘话题：

```bash
rostopic hz /odom
rostopic hz /imu
rostopic echo -n 1 /PowerVoltage
```

期望：

```text
/odom about 20Hz
/imu about 20Hz
/PowerVoltage has output
```

### 2. 单独检查电流板

终端 2 先只测电流，不采 CSV：

```bash
rosrun turn_on_wheeltec_robot current_reader.py \
  _port:=/dev/ttyUSB0 \
  _baud:=115200 \
  _timeout:=0.05 \
  _loop_rate:=200 \
  _report_interval:=5
```

另开一个终端检查：

```bash
rostopic hz /current_data
rostopic echo -n 5 /current_data
```

期望：

```text
/current_data about 80-100Hz
current_reader log: parse_error=0 checksum_error=0
echo data: exactly three current values
```

如果 `/dev/ttyUSB0` 不对，先查设备：

```bash
ls -l /dev/ttyUSB*
dmesg | tail -n 50
```

确认哪个端口能稳定输出 `/current_data`，采集命令里的 `current_port` 就填哪个端口。

### 3. 启动 CSV 采集

确认第 2 步电流正常后，停止单独的 `current_reader.py`，再启动采集 launch。

normal run：

```bash
roslaunch turn_on_wheeltec_robot data_collector.launch \
  current_port:=/dev/ttyUSB0 \
  output_dir:=/home/wheeltec/R550PLUS_data_collect/log_v2 \
  fault_label:=0 \
  fault_name:=normal \
  fault_mode:=0 \
  run_id:=normal_001 \
  motion_mode:=straight_back_forth_0.25ms \
  expected_rate:=20.0
```

drive_fault run：

```bash
roslaunch turn_on_wheeltec_robot data_collector.launch \
  current_port:=/dev/ttyUSB0 \
  output_dir:=/home/wheeltec/R550PLUS_data_collect/log_v2 \
  fault_label:=1 \
  fault_name:=drive_fault \
  fault_mode:=1 \
  run_id:=drive_fault_001 \
  motion_mode:=straight_back_forth_0.25ms \
  expected_rate:=20.0
```

启动后必须先看到：

```text
First valid current frame received; CSV recording can start
CSV output: ...
```

看到这两行后再让小车运动。

### 4. 启动 Web 控制

终端 3：

```bash
roslaunch turn_on_wheeltec_robot web_control.launch \
  start_base:=false \
  start_current_reader:=false \
  start_data_collector:=false
```

浏览器访问：

```text
http://<robot-ip>:8000/
```

Rosbridge 地址：

```text
ws://<robot-ip>:9090
```

当前推荐先用 `0.25m/s` 前后直线折返，保证场地安全和工况一致。如果正式实验改为 `0.5m/s`，normal 和 drive_fault 必须同时改，并同步修改 `motion_mode` 和 inspect 命令中的 `--expected_cmd_abs`。

## CSV 字段

`data_collector.py` 固定写入如下字段：

```text
timestamp, run_id, sample_id, fault_label, fault_name, fault_mode, motion_mode,
cmd_vx, cmd_vy, cmd_wz,
odom_vx, odom_vy, odom_wz,
wheel_speed0, wheel_speed1, wheel_speed2,
imu_ax, imu_ay, imu_az, imu_gx, imu_gy, imu_gz,
voltage,
current_seq, current0, current1, current2,
odom_time, imu_time, voltage_time, current_time, current_dt, cmd_time,
odom_age, imu_age, voltage_age, current_age, cmd_age,
record_rate, current_valid, current_reused_count
```

关键调试字段：

| 字段 | 含义 | 正常期望 |
| --- | --- | --- |
| record_rate | CSV 实际写入频率 | 接近 20Hz |
| current_valid | 当前行是否有有效电流 | 基本全为 1 |
| current_age | 写行时距离最近电流帧的时间 | 通常小于 0.05s |
| current_dt | 当前 odom timestamp 与最近电流时间的差 | 通常小于 0.05s |
| current_reused_count | 同一帧电流被连续复用的 CSV 行数 | 多数为 0，偶尔 1 可以接受 |

如果 `current_reused_count` 经常大于 2，说明 20Hz CSV 行在大量复用旧电流，需要重新检查 `/current_data` 频率和串口稳定性。

## 检查 CSV 质量

找到最新 CSV：

```bash
ls -lt /home/wheeltec/R550PLUS_data_collect/log_v2/ | head
```

检查 normal：

```bash
python3 ~/ml_robot_ws/src/turn_on_wheeltec_robot/scripts/inspect_csv.py \
  /home/wheeltec/R550PLUS_data_collect/log_v2/normal_001.csv \
  --expected_run_id normal_001 \
  --expected_fault_label 0 \
  --expected_fault_name normal \
  --expected_fault_mode 0 \
  --expected_motion_mode straight_back_forth_0.25ms \
  --expected_rate 20 \
  --expected_cmd_abs 0.25
```

检查 drive_fault：

```bash
python3 ~/ml_robot_ws/src/turn_on_wheeltec_robot/scripts/inspect_csv.py \
  /home/wheeltec/R550PLUS_data_collect/log_v2/drive_fault_001.csv \
  --expected_run_id drive_fault_001 \
  --expected_fault_label 1 \
  --expected_fault_name drive_fault \
  --expected_fault_mode 1 \
  --expected_motion_mode straight_back_forth_0.25ms \
  --expected_rate 20 \
  --expected_cmd_abs 0.25
```

合格标准：

```text
average sample rate close to 20Hz
record_rate close to 20Hz
current_valid ratio close to 1.0
current_age/current_dt usually below 0.05s
current_reused_count mostly 0 or 1
NaN/Inf count is 0
run_id/fault_label/fault_name/fault_mode/motion_mode are exactly expected
```

## 构建第一版数据集

训练集和测试集必须按 `run_id` 划分，不能把同一个 run 的重叠窗口同时放进训练和测试。

`normal_001` 和 `drive_fault_001` 只能证明链路能跑通、CSV 能被脚本读取。要得到真正可训练、可测试的二分类数据集，至少每类采两个独立 run，例如：

```text
normal_001, normal_002
drive_fault_001, drive_fault_002
```

然后让脚本自动按类别留出测试 run：

```bash
python3 ~/ml_robot_ws/src/turn_on_wheeltec_robot/scripts/build_fault_dataset.py \
  --input_dir /home/wheeltec/R550PLUS_data_collect/log_v2 \
  --output_dir /home/wheeltec/R550PLUS_dataset/v1 \
  --pattern "*.csv" \
  --window_size 50 \
  --step_size 10 \
  --scaler standard
```

输出文件：

```text
X_train.npy
y_train.npy
X_test.npy
y_test.npy
meta_train.csv
meta_test.csv
scaler.pkl
feature_config.json
```

`X_*` 形状为：

```text
[num_samples, 12, window_size]
```

## 常用调试命令

```bash
rostopic list | grep -E "odom|imu|PowerVoltage|current_data|cmd_vel"
rostopic hz /odom
rostopic hz /imu
rostopic hz /current_data
rostopic echo -n 1 /current_data
rostopic echo -n 1 /cmd_vel
```

```bash
head -n 2 /home/wheeltec/R550PLUS_data_collect/log_v2/normal_001.csv
tail -n 5 /home/wheeltec/R550PLUS_data_collect/log_v2/normal_001.csv
```

## 当前阶段不要做的事

- 不要把 `timestamp/run_id/sample_id/*_time/*_age` 放进模型输入。
- 不要把 `cmd_vx/cmd_vy/cmd_wz` 放进第一版模型输入。
- 不要把 `voltage` 放进第一版模型输入。
- 不要把 `wheel_speed0~2` 放进第一版模型输入。
- 不要为了第一版数据集改底盘 24 字节协议。
- 不要在电流频率、CSV 质量没确认前进入模型训练。

## 文件说明

```text
turn_on_wheeltec_robot/
  launch/
    turn_on_wheeltec_robot.launch    # 底盘 ROS 节点
    data_collector.launch            # 电流读取 + CSV 采集
    web_control.launch               # Web 控制
  scripts/
    current_reader.py                # 电流板串口读取，发布 /current_data
    data_collector.py                # /odom 触发写 CSV
    inspect_csv.py                   # CSV 质量检查
    build_fault_dataset.py           # CSV 滑窗构建 npy 数据集
    cmd_vel_web_adapter.py           # Web 控制适配
  src/
    wheeltec_robot.cpp               # 底盘串口解析和 ROS 发布
```
