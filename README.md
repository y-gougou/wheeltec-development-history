# WHEELTEC 机器人开发历史

本仓库原名 `0510`，保留 R550PLUS 三全向轮机器人数据采集、Web 控制和故障实验的连续开发历史。它汇集 `data_tackle-task`、`last_code` 到 `0510` 的原始代码提交，用于追溯早期实现与提取历史资源。

日常使用请先查看：

- [wheeltec-robot-platform](https://github.com/y-gougou/wheeltec-robot-platform)：当前机器人平台代码入口。
- [robot-fault-diagnosis-thesis](https://github.com/y-gougou/robot-fault-diagnosis-thesis)：毕业设计完整工程与故障诊断研究。
- [project-index](https://github.com/y-gougou/project-index)：个人项目导航。

## 目录与阅读入口

| 路径 | 内容 |
|---|---|
| [turn_on_wheeltec_robot/](turn_on_wheeltec_robot/) | ROS1 catkin 包；底盘控制、采集、Web 界面和机器人资源 |
| [turn_on_wheeltec_robot/README.md](turn_on_wheeltec_robot/README.md) | ROS 包说明 |
| [turn_on_wheeltec_robot/README_0511.md](turn_on_wheeltec_robot/README_0511.md) | 阶段说明 |
| [turn_on_wheeltec_robot/src/](turn_on_wheeltec_robot/src/) | C++ 节点实现 |
| [turn_on_wheeltec_robot/scripts/](turn_on_wheeltec_robot/scripts/) | 数据采集、电流读取、Web 服务、故障注入和数据集构建脚本 |
| [turn_on_wheeltec_robot/launch/](turn_on_wheeltec_robot/launch/) | ROS 启动文件 |
| [turn_on_wheeltec_robot/web/](turn_on_wheeltec_robot/web/) | Web 源码、构建产物及历史依赖 |
| [turn_on_wheeltec_robot/docs/](turn_on_wheeltec_robot/docs/) | 协议与开发文档 |
| [turn_on_wheeltec_robot/urdf/](turn_on_wheeltec_robot/urdf/) / [meshes/](turn_on_wheeltec_robot/meshes/) | 机器人描述与模型资源 |
| [中期总结](中期总结) | 历史中期总结，内容对应当时开发进度 |

主要脚本包括 `data_collector.py`、`current_reader.py`、`cmd_vel_web_adapter.py`、`web_dashboard_server.py`、`fault_injector.py` 和 `build_fault_dataset.py`。具体参数以所选分支的脚本、launch 文件和包内文档为准。

## 已保留的历史阶段

以下数量和提交指向本次整理前的代码状态；新增说明文档会增加当前分支的提交数。

| 原始入口 | 原代码提交数 | 本仓库访问点 | 原代码末次提交 |
|---|---:|---|---|
| `data_tackle-task/main` | 18 | [archive/data-tackle-task](https://github.com/y-gougou/wheeltec-development-history/tree/archive/data-tackle-task) | `a5cabba15a02e00d864aeb3f318d95a69ce8a292` |
| `last_code/main` | 23 | [archive/last-code](https://github.com/y-gougou/wheeltec-development-history/tree/archive/last-code) | `65435c1e80f238a7536cb2757730c90bdf27c6e8` |
| `0510/main` | 43 | [固定代码快照](https://github.com/y-gougou/wheeltec-development-history/tree/668af4ad85521e6a91191258c2b77c7dfeb5a3ca) | `668af4ad85521e6a91191258c2b77c7dfeb5a3ca` |
| `0510/master` | 1 | [master](https://github.com/y-gougou/wheeltec-development-history/tree/master)（初始化模板） | `71c3002805ae0f366c61bee20b9598aa3164240c` |

Git 提交关系已核对：`data_tackle-task/main` 是 `last_code/main` 的祖先，后者又是 `0510/main` 的祖先。前两仓库的全部原代码历史已在这里保留。`last_code/back_up` 与 `archive/data-tackle-task` 指向同一提交，没有额外独有历史。

## 历史资源与仓库体积

在代码快照 `668af4a` 中：

- `turn_on_wheeltec_robot/meshes/` 包含 **469 个文件，共 1,111,437,646 字节，约 1.11 GB**（十进制）。这是模型资源的文件大小合计，不是 Git 压缩下载量。
- `turn_on_wheeltec_robot/web/node_modules/` 中有 **4,340 个已纳入 Git 的文件，共 80,010,095 字节**。它们是历史提交中的前端依赖，保留用于追溯。
- 当前平台及毕设 ROS 工程中的部分 URDF 仍引用模型文件；需要可视化相应车型时，可从本仓库按实际引用路径提取所需资源。

## 使用与验证范围

本仓库以历史追溯为主要用途。复现旧版需匹配当时的 ROS、串口设备、传感器协议和机器人硬件，构建及启动步骤见包内文档。

本次整理仅新增根 README，并核对目录、文件规模和提交关系；未运行 ROS 构建、前端构建或机器人硬件测试。

原有源码、提交作者信息及文件中的版权声明均保留。
