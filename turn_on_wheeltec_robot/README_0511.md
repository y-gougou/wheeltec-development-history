# 0511 数据采集操作手册

本文档记录当前阶段的可用流程：先跑通 normal / drive_fault 二分类数据闭环，优先保证能采、能检、能生成 `[N, 12, 50]` 数据集。当前数据集定位为流程验证数据集，后续论文正式数据集再补采、更规范。

## 当前目标

二分类标签：

| 数据类型 | fault_label | fault_name | fault_mode | 底盘固件 |
| --- | --- | --- | --- | --- |
| 正常数据 | 0 | normal | 0 | `FAULT_MODE = 0` |
| 驱动异常 | 1 | drive_fault | 1 | `FAULT_MODE = 1` |

第一版模型只使用 12 个核心特征：

```text
odom_vx, odom_vy, odom_wz,
imu_ax, imu_ay, imu_az,
imu_gx, imu_gy, imu_gz,
current0, current1, current2
```

raw CSV 可以保留 `cmd_*`、`voltage`、`*_time`、`*_age`、`current_dt`、`current_reused_count` 等调试字段，但这些字段不进入第一版 `X_train.npy`。

## 固件模式切换

驱动异常通过底盘固件软件注入实现，不使用物理堵转。

修改文件：

```text
03 omi_car/BALANCE/balance.c
```

当前宏定义：

```c
#define FAULT_MODE 0
#define DRIVE_FAULT_SCALE 0.5f
```

正常采集时：

```c
#define FAULT_MODE 0
```

驱动异常采集时：

```c
#define FAULT_MODE 1
#define DRIVE_FAULT_SCALE 0.5f
```

注入位置在三全向轮逆解之后、PID 之前：

```c
#if FAULT_MODE == 1
    MOTOR_B.Target = MOTOR_B.Target * DRIVE_FAULT_SCALE;
#endif
```

每次切换 `FAULT_MODE` 后，都需要重新编译并烧录底盘固件。ROS 端协议、24 字节上报协议、`wheeltec_robot.cpp` 都不需要修改。

## 采集前检查

确认设备：

```bash
ls -l /dev/ttyUSB*
```

当前电流板常用端口：

```text
/dev/ttyUSB0
```

底盘串口由底盘 launch 内部配置，不在本手册中重复修改。

## 终端 1：启动底盘

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

## 终端 2：单独检查电流板

正式采 CSV 前，建议先单独确认 `/current_data` 频率。

```bash
rosrun turn_on_wheeltec_robot current_reader.py \
  _port:=/dev/ttyUSB1 \
  _baud:=115200 \
  _timeout:=0.05 \
  _loop_rate:=200 \
  _report_interval:=5
```

另开终端检查：

```bash
rostopic hz /current_data
rostopic echo -n 5 /current_data
```

期望：

```text
/current_data about 80-100Hz
parse_error=0
checksum_error=0
data contains 3 current values
```

检查完成后，按 `Ctrl+C` 停止这个单独运行的 `current_reader.py`。后面的 `data_collector.launch` 会自动启动自己的 `current_reader`。

## 终端 2：启动 CSV 采集

启动采集后，必须先看到：

```text
First valid current frame received; CSV recording can start
CSV output: ...
```

看到这两行后再让小车运动。

### 采 normal 数据

底盘固件必须是：

```c
#define FAULT_MODE 0
```

采 `normal_001`：

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

继续采 normal 时，只改 `run_id`：

```bash
run_id:=normal_002
run_id:=normal_003
```

当前建议先采：

```text
normal_001
normal_002
normal_003
```

### 采 drive_fault 数据

先把底盘固件改为：

```c
#define FAULT_MODE 1
#define DRIVE_FAULT_SCALE 0.5f
```

重新编译并烧录底盘固件。第一次上实车先低速验证，不要直接采正式数据。

采 `drive_fault_001`：

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

继续采 drive_fault 时，只改 `run_id`：

```bash
run_id:=drive_fault_002
run_id:=drive_fault_003
```

当前建议先采：

```text
drive_fault_001
drive_fault_002
drive_fault_003
```

## 终端 3：启动 Web 控制

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

采集动作建议：

```text
0-5s 静止
中间 0.25m/s 前后直线折返
最后 5s 静止
总时长 90-120s
```

注意：normal 和 drive_fault 必须使用相同运动工况，例如都使用 `straight_back_forth_0.25ms`。不要一类直线、一类旋转，否则模型容易学到动作差异而不是故障差异。

## 可选：命令行低速测试

故障固件第一次上车时，建议先用 `0.15m/s` 低速测试：

```bash
rostopic pub /cmd_vel geometry_msgs/Twist \
  '{linear: {x: 0.15, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.0}}' \
  -r 20
```

停止：

```bash
rostopic pub /cmd_vel geometry_msgs/Twist \
  '{linear: {x: 0.0, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.0}}' \
  -1
```

确认无失控、无明显发热后，再用 Web 页面按 `0.25m/s` 正式采集。

## 采完后检查 CSV

查看最新 CSV：

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

最低合格标准：

```text
fault_label 正确
12 个核心特征存在
核心特征没有 NaN / Inf
average sample rate 接近 20Hz
timestamp mean dt 接近 0.05s
current0/current1/current2 有有效值
current_valid ratio 接近 1.0
```

当前阶段可以接受：

```text
current_reused_count 偶尔 > 0
cmd 动作不完全干净
启动段/停车段有一点波动
每类只有 1 个 run
使用 allow_same_run_split
```

后续构建数据集时会用 `--trim_start_sec 5 --trim_end_sec 5` 裁掉启动和停车段。

## 构建流程验证数据集

当目录中至少有：

```text
normal_001.csv
drive_fault_001.csv
```

即可先跑通闭环：

```bash
python3 ~/ml_robot_ws/src/turn_on_wheeltec_robot/scripts/build_fault_dataset.py \
  --input_dir /home/wheeltec/R550PLUS_data_collect/log_v2 \
  --output_dir /home/wheeltec/R550PLUS_dataset/binary_v1 \
  --window_size 50 \
  --step_size 10 \
  --scaler standard \
  --trim_start_sec 5 \
  --trim_end_sec 5 \
  --allow_same_run_split
```

期望输出：

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

重点看终端输出：

```text
train: X=(?, 12, 50)
test: X=(?, 12, 50)
```

只要能得到：

```text
X_train.shape = [N, 12, 50]
X_test.shape = [N, 12, 50]
```

就可以进入 CWCNN-FA 二分类 baseline。

## 不同数据集采集时需要调整什么

### 从 normal 切换到 drive_fault

需要调整：

```text
1. 修改底盘固件 FAULT_MODE: 0 -> 1
2. 重新编译并烧录底盘固件
3. data_collector 参数改为 fault_label:=1
4. fault_name:=drive_fault
5. fault_mode:=1
6. run_id:=drive_fault_00x
```

不要调整：

```text
motion_mode
expected_rate
current_port
ROS 解析协议
底盘 24 字节上报协议
current_reader.py
data_collector.py 的 CSV 字段
```

### 从 drive_fault 切回 normal

需要调整：

```text
1. 修改底盘固件 FAULT_MODE: 1 -> 0
2. 重新编译并烧录底盘固件
3. data_collector 参数改为 fault_label:=0
4. fault_name:=normal
5. fault_mode:=0
6. run_id:=normal_00x
```

### 增加新的 run

只改 `run_id`：

```bash
run_id:=normal_002
run_id:=normal_003
run_id:=drive_fault_002
run_id:=drive_fault_003
```

其他参数保持一致。

## 实车安全注意事项

- 不再使用物理堵转构造故障。
- drive_fault 第一次烧录后，先 `0.15m/s` 低速测试。
- 观察是否出现原地剧烈旋转、失控、电机尖叫、明显发热。
- 如果 `DRIVE_FAULT_SCALE=0.5f` 太激烈，可临时改为 `0.7f`。
- 如果故障表现不明显，再恢复到 `0.5f`。
- 采集时随时准备急停。

## 当前闭环成功标准

满足下面条件即可推进训练：

```text
normal 和 drive_fault 都有数据
fault_label 正确
12 个核心特征存在
没有大量 NaN / Inf
采样频率约 20Hz
current0/current1/current2 有有效值
能生成 X_train.npy / X_test.npy
X.shape = [N, 12, 50]
```

