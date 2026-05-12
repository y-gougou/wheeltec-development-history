# R550PLUS 机器人串口通信协议

本文档基于源码逆向整理，描述 ROS 节点与底盘 STM32 控制器、电流传感器之间的串口通信协议。

---

## 1. 协议总览

| 协议 | 设备 | 串口 | 波特率 | 帧格式 | 校验方式 |
|------|------|------|--------|--------|----------|
| A - 底盘控制 | STM32 控制器 | `/dev/ttyCH343USB0` | 115200 | 二进制定长帧 | BCC XOR |
| B - 电流传感器 | 电流采集板 | `/dev/ttyUSB0` | 115200 | ASCII 文本帧 | XOR hex |

---

## 2. 协议 A：底盘控制器（二进制）

### 2.1 帧定界符

| 符号 | 字节值 | 说明 |
|------|--------|------|
| 帧头 | `0x7B` | 每帧第一个字节 |
| 帧尾 | `0x7D` | 每帧最后一个字节 |

### 2.2 校验算法（BCC XOR）

对帧内从第 0 字节到第 N-1 字节做按位异或，结果存放在第 N 字节：

```
checksum = byte[0] ^ byte[1] ^ ... ^ byte[N-1]
```

- 发送帧：对 byte[0..10] 异或，结果存入 byte[11]
- 接收帧：对 byte[0..27] 异或，结果与 byte[28] 比对

源码位置：`wheeltec_robot.cpp` 第 209-228 行 `Check_Sum()` 函数。

### 2.3 发送帧：ROS -> STM32（速度指令）

**帧长度：13 字节**

| 偏移 | 长度 | 字段 | 编码方式 | 说明 |
|------|------|------|----------|------|
| 0 | 1 | 帧头 | `uint8` | 固定 `0x7B` |
| 1 | 1 | 保留位 | `uint8` | 固定 `0x00` |
| 2 | 1 | 角度标志 | `uint8` | 见下方角度标志表 |
| 3-4 | 2 | VX（X 轴线速度） | `int16` 大端 | 单位 mm/s，原始值 = m/s * 1000 |
| 5-6 | 2 | VY（Y 轴线速度） | `int16` 大端 | 单位 mm/s，原始值 = m/s * 1000 |
| 7-8 | 2 | WZ（Z 轴角速度） | `int16` 大端 | 单位 mrad/s，原始值 = rad/s * 1000 |
| 9-10 | 2 | 目标角度 | `int16` 大端 | 单位 0.1 度，原始值 = 度 * 10 |
| 11 | 1 | BCC 校验 | `uint8` | byte[0..10] 的 XOR |
| 12 | 1 | 帧尾 | `uint8` | 固定 `0x7D` |

#### 角度标志（byte[2]）

| 值 | 含义 | 触发话题 | 说明 |
|----|------|----------|------|
| 0 | 正常速度指令 | `/cmd_vel` | 携带 vx, vy, wz + 存储的目标角度 |
| 1 | 设置目标角度 | `/target_angle` | 速度为零，发送指定角度，后续 cmd_vel 帧沿用此角度 |
| 2 | 重置目标角度 | `/target_angle_reset` | 速度和角度均归零 |
| 3 | 外部航向指令 | `/chassis/heading_deg` | 速度为零，发送外部 IMU 航向角 |

#### 数据编码示例

```
vx = 0.5 m/s  ->  (short)(0.5 * 1000) = 500  ->  tx[3]=0x01, tx[4]=0xF4
wz = -1.0 rad/s -> (short)(-1.0 * 1000) = -1000 -> tx[7]=0xFC, tx[8]=0x18
angle = 45.0° -> (short)(45.0 * 10) = 450    ->  tx[9]=0x01, tx[10]=0xC2
```

源码位置：`wheeltec_robot.cpp` 第 47-82 行 `Send_Chassis_Command()` 函数。

### 2.4 接收帧：STM32 -> ROS（传感器数据）

**帧长度：30 字节**

| 偏移 | 长度 | 字段 | 编码方式 | 转换公式 | 输出单位 |
|------|------|------|----------|----------|----------|
| 0 | 1 | 帧头 | `uint8` | 必须为 `0x7B` | - |
| 1 | 1 | 标志位 | `uint8` | 保留（存入 Flag_Stop，未使用） | - |
| 2-3 | 2 | VX（X 轴速度） | `int16` 大端 | `raw / 1000.0` | m/s |
| 4-5 | 2 | VY（Y 轴速度） | `int16` 大端 | `raw / 1000.0` | m/s |
| 6-7 | 2 | WZ（Z 轴角速度） | `int16` 大端 | `raw / 1000.0` | rad/s |
| 8-9 | 2 | 加速度计 X | `int16` 大端 | `raw / 1671.84` | m/s^2 |
| 10-11 | 2 | 加速度计 Y | `int16` 大端 | `raw / 1671.84` | m/s^2 |
| 12-13 | 2 | 加速度计 Z | `int16` 大端 | `raw / 1671.84` | m/s^2 |
| 14-15 | 2 | 陀螺仪 X | `int16` 大端 | `raw * 0.00026644` | rad/s |
| 16-17 | 2 | 陀螺仪 Y | `int16` 大端 | `raw * 0.00026644` | rad/s |
| 18-19 | 2 | 陀螺仪 Z | `int16` 大端 | `raw * 0.00026644` | rad/s |
| 20-21 | 2 | 电池电压 | `int16` 大端 | `raw / 1000.0` | V |
| 22-23 | 2 | 轮 0 速度 | `int16` 大端 | `raw / 1000.0` | m/s |
| 24-25 | 2 | 轮 1 速度 | `int16` 大端 | `raw / 1000.0` | m/s |
| 26-27 | 2 | 轮 2 速度 | `int16` 大端 | `raw / 1000.0` | m/s |
| 28 | 1 | BCC 校验 | `uint8` | byte[0..27] 的 XOR | - |
| 29 | 1 | 帧尾 | `uint8` | 必须为 `0x7D` | - |

#### IMU 量程说明

| 传感器 | 量程 | 原始数据范围 | 换算系数 | 说明 |
|--------|------|-------------|----------|------|
| 加速度计 | +/-2g (19.6 m/s^2) | +/-32768 | 32768 / 19.6 = 1671.84 LSB/(m/s^2) | `ACCEl_RATIO` |
| 陀螺仪 | +/-500 deg/s | +/-32768 | 1 / 65.5 / 57.30 = 0.00026644 rad/s/LSB | `GYROSCOPE_RATIO` |

源码位置：`wheeltec_robot.h` 第 43-49 行，`wheeltec_robot.cpp` 第 360-450 行。

### 2.5 速度转换函数 `Odom_Trans()`

```cpp
float Odom_Trans(uint8_t Data_High, uint8_t Data_Low) {
    short raw = (Data_High << 8) | Data_Low;  // 大端组合为 int16
    return (raw / 1000) + (raw % 1000) * 0.001;  // 等价于 raw / 1000.0
}
```

等价于 `raw / 1000.0`，但整数除法 + 取模的写法保留了亚毫米精度。

### 2.6 帧同步机制（逐字节法）

使用 `Get_Sensor_Data_New()` 函数（推荐），逐字节读取串口并重组帧：

1. 读取 1 字节
2. 若为 `0x7B`（帧头）或已在帧中（count > 0），存入 `rx[count]` 并递增 count
3. 否则重置 count = 0（丢弃非帧头字节）
4. 当 count == 30 时，验证 `rx[29] == 0x7D` 且 `rx[28] == XOR(rx[0..27])`
5. 校验通过则解析全部字段，重置 count = 0

源码位置：`wheeltec_robot.cpp` 第 360-450 行。

### 2.7 ROS 话题映射

#### 发布（从底盘读取）

| 话题 | 类型 | 频率 | 内容 |
|------|------|------|------|
| `/odom` | `nav_msgs/Odometry` | ~20Hz | 位置（速度积分）+ 速度 |
| `/imu` | `sensor_msgs/Imu` | ~20Hz | 四元数姿态 + 角速度 + 加速度 |
| `/PowerVoltage` | `std_msgs/Float32` | ~2Hz（每 11 帧发 1 次） | 电池电压 (V) |
| `/wheel_speed` | `std_msgs/Float32MultiArray` | ~20Hz | 三轮独立速度 (m/s) |

#### 订阅（发送到底盘）

| 话题 | 类型 | 角度标志 | 说明 |
|------|------|----------|------|
| `/cmd_vel` | `geometry_msgs/Twist` | 0 | 速度指令 |
| `/target_angle` | `std_msgs/Float32` | 1 | 设置目标角度 (度) |
| `/target_angle_reset` | `std_msgs/Empty` | 2 | 重置目标角度 |
| `/chassis/heading_deg` | `std_msgs/Float32` | 3 | 外部航向指令 (度) |

---

## 3. 协议 B：电流传感器（ASCII）

### 3.1 帧格式

电流传感器通过 ASCII 文本行发送数据，每行一帧。

**格式 1（无序号）：**
```
$CURRENT,ch0,ch1,ch2*XX\r\n
```

**格式 2（带序号）：**
```
$CURRENT,seq,ch0,ch1,ch2*XX\r\n
```

| 部分 | 说明 |
|------|------|
| `$CURRENT,` | 固定帧头 |
| `seq` | 可选整数序号（格式 2） |
| `ch0,ch1,ch2` | 三通道电流值，ASCII 浮点数 |
| `*` | 分隔符 |
| `XX` | 2 字符大写十六进制校验和 |
| `\r\n` | 行结束符 |

### 3.2 校验算法

对 `$` 到 `*` 之前（不含 `*`）的所有字符的 ASCII 码做按位异或：

```python
def xor_ascii(payload):
    checksum = 0
    for ch in payload:
        checksum ^= ord(ch)
    return checksum
```

校验和以 2 字符大写十六进制与 `*` 后的值比对。

源码位置：`scripts/core/serial_utils.py` 第 45-49 行。

### 3.3 解析流程

1. 在行中查找 `$CURRENT,`
2. 查找 `*` 分隔符
3. 提取 `$` 到 `*` 之间的数据字符串
4. 提取 `*` 后 2 字符十六进制校验和
5. 计算 XOR 校验并比对
6. 按 `,` 分割数据：4 段则第 1 段为序号，后 3 段为电流值；3 段则全部为电流值
7. 输出 `Float32MultiArray`：`[ch0, ch1, ch2]` 或 `[ch0, ch1, ch2, seq]`

源码位置：`scripts/current_reader.py` 第 135-199 行 `parse_frame()` 函数。

### 3.4 ROS 输出

| 话题 | 类型 | 说明 |
|------|------|------|
| `/current_data` | `std_msgs/Float32MultiArray` | `[ch0, ch1, ch2]` 或 `[ch0, ch1, ch2, seq]` |

---

## 4. Web 控制适配层

`cmd_vel_web_adapter.py` 不是串口协议，而是 ROS 话题层的安全适配器，位于浏览器（rosbridge）和底盘节点之间。

```
浏览器 --(rosbridge WS:9090)--> /cmd_vel_web --> adapter --> /cmd_vel --> 底盘节点
```

安全机制：

| 机制 | 默认值 | 说明 |
|------|--------|------|
| 指令超时 | 0.5s | 无新指令则发布零速度 |
| 心跳超时 | 1.0s | 无心跳则急停锁定 |
| X 轴限速 | 1.50 m/s | `max_linear_x` |
| Y 轴限速 | 1.00 m/s | `max_linear_y` |
| Z 轴限速 | 3.75 rad/s | `max_angular_z` |
| 线速度死区 | 0.02 | 低于此值视为零 |
| 角速度死区 | 0.03 | 低于此值视为零 |

巡航模式下使用 PID 闭环控制，订阅 `/web/cruise_cmd` 和 `/web/cruise_enable`。

---

## 5. 固件侧协议验证（STM32 源码对照）

固件源码位于 `D:\projects\03 omi_car`，Keil ARM MDK 项目。关键文件：

- `HARDWARE/usartx.h` — 协议结构体定义、帧常量
- `HARDWARE/usartx.c` — 数据打包、帧发送、接收解析、校验

### 5.1 常量对照

| 常量 | STM32 固件 (`usartx.h`) | ROS 包 (`wheeltec_robot.h`) | 一致性 |
|------|------------------------|---------------------------|--------|
| 帧头 | `FRAME_HEADER = 0X7B` | `FRAME_HEADER = 0X7B` | 一致 |
| 帧尾 | `FRAME_TAIL = 0X7D` | `FRAME_TAIL = 0X7D` | 一致 |
| 发送帧长 | `SEND_DATA_SIZE = 30` | `RECEIVE_DATA_SIZE = 30` | 一致（方向相反） |
| 接收帧长 | `RECEIVE_DATA_SIZE = 13` | `SEND_DATA_SIZE = 13` | 一致（方向相反） |

注意：固件的"发送"对应 ROS 的"接收"，命名方向相反但数值完全匹配。

### 5.2 发送帧（STM32 -> ROS，30 字节）逐字节对照

固件在 `data_transition()` 函数（`usartx.c` 第 28-131 行）中打包数据：

```c
// 固件侧打包（usartx.c:67-111）
Send_Data.buffer[0]  = Frame_Header;           // 0x7B
Send_Data.buffer[1]  = Flag_Stop;              // 标志位
Send_Data.buffer[2]  = X_speed >> 8;           // 速度高字节
Send_Data.buffer[3]  = X_speed;                // 速度低字节
Send_Data.buffer[4]  = Y_speed >> 8;
Send_Data.buffer[5]  = Y_speed;
Send_Data.buffer[6]  = Z_speed >> 8;
Send_Data.buffer[7]  = Z_speed;
Send_Data.buffer[8]  = Accelerometer.X_data >> 8;  // 加速度计
Send_Data.buffer[9]  = Accelerometer.X_data;
...
Send_Data.buffer[20] = Power_Voltage >> 8;     // 电压
Send_Data.buffer[21] = Power_Voltage;
Send_Data.buffer[22] = Wheel_Speed_A >> 8;     // 轮速 A
Send_Data.buffer[23] = Wheel_Speed_A;
Send_Data.buffer[24] = Wheel_Speed_B >> 8;     // 轮速 B
Send_Data.buffer[25] = Wheel_Speed_B;
Send_Data.buffer[26] = Wheel_Speed_C >> 8;     // 轮速 C
Send_Data.buffer[27] = Wheel_Speed_C;
Send_Data.buffer[28] = Check_Sum(28, 1);       // BCC XOR
Send_Data.buffer[29] = Frame_Tail;             // 0x7D
```

| 偏移 | 固件字段 | ROS 解析字段 | 编码 | 一致性 |
|------|---------|-------------|------|--------|
| 0 | `FRAME_HEADER` | `FRAME_HEADER` | `0x7B` | 一致 |
| 1 | `Flag_Stop` | `Flag_Stop` | `uint8` | 一致 |
| 2-3 | `X_speed` | `Robot_Vel.X` | `int16` 大端, mm/s | 一致 |
| 4-5 | `Y_speed` | `Robot_Vel.Y` | `int16` 大端, mm/s | 一致 |
| 6-7 | `Z_speed` | `Robot_Vel.Z` | `int16` 大端, mm/s | 一致 |
| 8-9 | `Accelerometer.X_data` | `accele_x_data` | `int16` 大端 | 一致 |
| 10-11 | `Accelerometer.Y_data` | `accele_y_data` | `int16` 大端 | 一致 |
| 12-13 | `Accelerometer.Z_data` | `accele_z_data` | `int16` 大端 | 一致 |
| 14-15 | `Gyroscope.X_data` | `gyros_x_data` | `int16` 大端 | 一致 |
| 16-17 | `Gyroscope.Y_data` | `gyros_y_data` | `int16` 大端 | 一致 |
| 18-19 | `Gyroscope.Z_data` | `gyros_z_data` | `int16` 大端 | 一致 |
| 20-21 | `Power_Voltage` | `Power_voltage` | `int16` 大端, mV | 一致 |
| 22-23 | `Wheel_Speed_A` | `Wheel_Speed[0]` | `int16` 大端, mm/s | 一致 |
| 24-25 | `Wheel_Speed_B` | `Wheel_Speed[1]` | `int16` 大端, mm/s | 一致 |
| 26-27 | `Wheel_Speed_C` | `Wheel_Speed[2]` | `int16` 大端, mm/s | 一致 |
| 28 | `Check_Sum(28,1)` | `Check_Sum(28,0)` | XOR byte[0..27] | 一致 |
| 29 | `FRAME_TAIL` | `FRAME_TAIL` | `0x7D` | 一致 |

### 5.3 接收帧（ROS -> STM32，13 字节）固件解析

固件在 `USART3_IRQHandler()`（`usartx.c` 第 512-616 行）中解析接收帧：

```c
// 固件侧解析（usartx.c:561-590）
Move_X = XYZ_Target_Speed_transition(buffer[3], buffer[4]);  // VX
Move_Y = XYZ_Target_Speed_transition(buffer[5], buffer[6]);  // VY
Move_Z = XYZ_Target_Speed_transition(buffer[7], buffer[8]);  // WZ

if (buffer[2] == 1) {       // angle_flag=1: 设置目标角度
    angle_raw = (buffer[9]<<8) + buffer[10];
    Target_Angle = Normalize_Angle(angle_raw / 10.0f);
}
else if (buffer[2] == 2) {  // angle_flag=2: 重置角度
    Set_Current_Angle_Zero_Flag = 1;
}
else if (buffer[2] == 3) {  // angle_flag=3: 外部航向
    angle_raw = (buffer[9]<<8) + buffer[10];
    External_Heading_Angle = Normalize_Angle(angle_raw / 10.0f);
}
```

| 偏移 | ROS 发送 | 固件解析 | 编码 | 一致性 |
|------|---------|---------|------|--------|
| 0 | `FRAME_HEADER` | `FRAME_HEADER` | `0x7B` | 一致 |
| 1 | `0x00` | `buffer[1]` (充电模式判断) | `uint8` | 一致（正常模式=0） |
| 2 | `angle_flag` | `buffer[2]` (角度标志) | `uint8` | 一致 |
| 3-4 | `vx * 1000` | `XYZ_Target_Speed_transition()` | `int16` 大端, mm/s | 一致 |
| 5-6 | `vy * 1000` | `XYZ_Target_Speed_transition()` | `int16` 大端, mm/s | 一致 |
| 7-8 | `wz * 1000` | `XYZ_Target_Speed_transition()` | `int16` 大端, mm/s | 一致 |
| 9-10 | `angle * 10` | `angle_raw / 10.0f` | `int16` 大端, 0.1度 | 一致 |
| 11 | `Check_Sum(11,1)` | `Check_Sum(11,0)` | XOR byte[0..10] | 一致 |
| 12 | `FRAME_TAIL` | `FRAME_TAIL` | `0x7D` | 一致 |

速度解码函数对比：

```c
// 固件侧（usartx.c:618-629）
float XYZ_Target_Speed_transition(u8 High, u8 Low) {
    short transition = (High << 8) + Low;
    return transition / 1000 + (transition % 1000) * 0.001;
}

// ROS 侧（wheeltec_robot.cpp:32-41）
float Odom_Trans(uint8_t Data_High, uint8_t Data_Low) {
    short transition_16 = (Data_High << 8) | Data_Low;
    return (transition_16 / 1000) + (transition_16 % 1000) * 0.001;
}
```

两个函数逻辑完全等价。

### 5.4 固件侧 IMU 轴映射

固件在打包 IMU 数据时做了坐标轴重映射（`usartx.c` 第 47-61 行）：

```c
Send_Data.Sensor_Str.Accelerometer.X_data =  accel[1];  // 原始 Y -> 发送 X
Send_Data.Sensor_Str.Accelerometer.Y_data = -accel[0];  // 原始 X 取反 -> 发送 Y
Send_Data.Sensor_Str.Accelerometer.Z_data =  accel[2];  // 原始 Z -> 发送 Z

Send_Data.Sensor_Str.Gyroscope.X_data =  gyro[1];  // 原始 Y -> 发送 X
Send_Data.Sensor_Str.Gyroscope.Y_data = -gyro[0];  // 原始 X 取反 -> 发送 Y
// Gyroscope.Z_data = gyro[2]（正常）或 0（电机停止时）
```

这意味着 ROS 收到的 IMU 数据已经过坐标变换，不是 MPU6050 原始坐标系。ROS 侧直接使用这些值发布 `/imu` 话题，无需额外变换。

### 5.5 固件侧电机停止时陀螺仪清零

```c
// usartx.c:54-61
if (Flag_Stop == 0)
    Send_Data.Sensor_Str.Gyroscope.Z_data = gyro[2];   // 正常值
else
    Send_Data.Sensor_Str.Gyroscope.Z_data = 0;          // 电机停止时强制为 0
```

当 `Flag_Stop` 非零（电机故障或急停）时，固件将 Z 轴角速度强制清零后发送。ROS 侧收到的 `/imu` 话题中 `angular_velocity.z` 会是 0，这可能导致 IMU 四元数解算在急停期间失去 Z 轴旋转信息。

### 5.6 双串口中断差异

固件有两个串口接收中断处理函数，对 `angle_flag=3`（外部航向）的支持不同：

| 功能 | `USART1_IRQHandler` | `USART3_IRQHandler` |
|------|--------------------|--------------------|
| angle_flag=0（速度指令） | 支持 | 支持 |
| angle_flag=1（设置角度） | 支持 | 支持 |
| angle_flag=2（重置角度） | 支持 | 支持 |
| angle_flag=3（外部航向） | **不支持** | 支持 |
| byte[1] 充电模式判断 | 不判断 | 判断 (0/1/2/3) |

ROS 节点通过 CH343 USB 串口连接，对应 USART3（`PB10/PB11`），因此 `angle_flag=3` 可以正常工作。但如果通过 USART1 连接，外部航向指令会被忽略。

### 5.7 校验函数对照

```c
// 固件侧（usartx.c:665-685）
u8 Check_Sum(unsigned char Count_Number, unsigned char Mode) {
    unsigned char check_sum = 0, k;
    if (Mode == 1)  // 发送模式
        for (k = 0; k < Count_Number; k++)
            check_sum ^= Send_Data.buffer[k];
    if (Mode == 0)  // 接收模式
        for (k = 0; k < Count_Number; k++)
            check_sum ^= Receive_Data.buffer[k];
    return check_sum;
}

// ROS 侧（wheeltec_robot.cpp:209-228）
unsigned char Check_Sum(unsigned char Count_Number, unsigned char mode) {
    unsigned char check_sum = 0, k;
    if (mode == 0)  // 接收模式
        for (k = 0; k < Count_Number; k++)
            check_sum ^= Receive_Data.rx[k];
    if (mode == 1)  // 发送模式
        for (k = 0; k < Count_Number; k++)
            check_sum ^= Send_Data.tx[k];
    return check_sum;
}
```

逻辑完全一致。注意 mode 参数含义相反：固件 `Mode=1` 是发送，ROS `mode=1` 也是发送——但固件校验 `Send_Data.buffer`，ROS 校验 `Send_Data.tx`，各自校验自己的发送缓冲区，互不冲突。

---

## 6. 协议一致性总结

### 6.1 逐项对照结果

| 检查项 | STM32 固件 | ROS 包 | 一致性 |
|--------|-----------|--------|--------|
| 帧头 `0x7B` | `FRAME_HEADER = 0X7B` | `FRAME_HEADER = 0X7B` | 一致 |
| 帧尾 `0x7D` | `FRAME_TAIL = 0X7D` | `FRAME_TAIL = 0X7D` | 一致 |
| 发送帧长 30 字节 | `SEND_DATA_SIZE = 30` | `RECEIVE_DATA_SIZE = 30` | 一致 |
| 接收帧长 13 字节 | `RECEIVE_DATA_SIZE = 13` | `SEND_DATA_SIZE = 13` | 一致 |
| BCC XOR 校验 | `Check_Sum()` | `Check_Sum()` | 一致 |
| 速度编码 mm/s | `Encoder * 1000` | `vx * 1000` | 一致 |
| 角速度编码 mrad/s | `wz * 1000` | `wz * 1000` | 一致 |
| 角度编码 0.1度 | `angle_raw / 10.0f` | `angle_deg * 10` | 一致 |
| 大端字节序 | `>> 8` | `>> 8` | 一致 |
| 速度解码函数 | `XYZ_Target_Speed_transition()` | `Odom_Trans()` | 逻辑等价 |
| 陀螺仪量程 +/-500deg/s | MPU6050 初始化配置 | `GYROSCOPE_RATIO = 0.00026644` | 一致 |
| 加速度计量程 +/-2g | MPU6050 初始化配置 | `ACCEl_RATIO = 1671.84` | 一致 |
| 电压编码 mV | `Voltage * 1000` | `raw / 1000` 转换 | 一致 |
| 轮速编码 mm/s | `Encoder * 1000` | `Odom_Trans()` 转换 | 一致 |
| 角度标志 0/1/2/3 | USART3 中断完整支持 | `Send_Chassis_Command()` | 一致 |

**结论：ROS 包与 STM32 固件的串口协议完全匹配，所有字段、编码、校验、字节序均一致。**

### 6.2 已知注意事项

1. **IMU 轴映射**：固件发送前已做坐标变换（`accel[1]→X`, `-accel[0]→Y`），ROS 收到的不是 MPU6050 原始轴。

2. **陀螺仪 Z 轴清零**：电机停止时固件将 `Gyroscope.Z_data` 强制为 0，ROS 的 `/imu` 话题会反映这一行为。

3. **双串口差异**：USART1 不支持 `angle_flag=3`（外部航向），仅 USART3 支持。ROS 通过 CH343 连接 USART3，不受影响。

4. **帧内出现 `0x7B`/`0x7D`**：旧的批量读取方法 `Get_Sensor_Data()` 会帧同步失败。当前使用的 `Get_Sensor_Data_New()` 逐字节法已解决此问题。

5. **Odom_Trans() 精度**：`raw / 1000 + raw % 1000 * 0.001` 在 raw 为负数时，C++ 的 `%` 运算结果为负，例如 `raw = -1500`：`-1500/1000 = -1`，`-1500%1000 = -500`，`-1 + (-500)*0.001 = -1.5`，结果正确。

6. **config.py 缺失**：CLAUDE.md 中提到 `scripts/config.py` 定义了全局串口配置，但当前代码中该文件不存在。串口参数通过 launch 文件参数传递。

---

## 6. 数据采集输出

`data_collector.py` 订阅上述所有话题，以 CSV 格式记录 16 通道数据：

| 通道 | 来源 | 说明 |
|------|------|------|
| pos_x, pos_y, pos_z | `/odom` | 位置 (m, m, rad) |
| vel_x, vel_y, vel_z | `/odom` | 速度 (m/s, m/s, rad/s) |
| acc_x, acc_y, acc_z | `/imu` | 加速度 (m/s^2) |
| gyro_x, gyro_y, gyro_z | `/imu` | 角速度 (rad/s) |
| voltage | `/PowerVoltage` | 电压 (V) |
| current_0/1/2 | `/current_data` | 电流 (A) |

采集频率由 `data_collector.launch` 中的参数控制，默认跟随各话题发布频率（~20Hz）。
