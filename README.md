# DLDS-532 智能产线 MES 相关工程

本仓库汇总 DLDS-532 实训平台的三套配套工程：PLC/HMI 原程序、Windows 下单终端、工业数据可视化大屏。

## 目录结构

| 目录 | 内容 | 技术栈 |
|---|---|---|
| `DLDS-532_V16_v1.0/` | 数据管理站 PLC + HMI 原始工程（TIA Portal V16 归档项目） | TIA Portal V16（S7-1200 + HMI） |
| `DLDS532_OrderApp/` | 下单终端：新建订单 → 经 S7 TCP 写 DB121 → 按握手信号推进状态并落库 | Python 3.12 + PySide6 + python-snap7 + SQLite |
| `数据大屏/` | 工业数据可视化大屏：只读读取 S7-1200 的 DB120，1920×1080 深蓝工业风 | WPF / .NET 8 (C#) |

各子工程均有独立 README，包含详细的运行、构建与业务说明：

- [DLDS532_OrderApp/README.md](DLDS532_OrderApp/README.md)
- [数据大屏/README.md](数据大屏/README.md)（另见 `数据大屏/docs/` 下的设计与交付文档）

## 系统关系概览

```
下单终端 (DB121 写入)  ──►  数据管理站 PLC (S7-1200)  ──►  产线设备
                                   │
数据大屏 (DB120 只读) ◄────────────┘
```

- **下单终端**只负责写入订单到 `DB121`，不控制设备动作；
- **数据大屏**只读 `DB120`，不写 PLC、不改运行模式；
- PLC 原程序与 HMI 界面位于 `DLDS-532_V16_v1.0/DLDS-532_V16_v1.0.zap16`，可用 TIA Portal V16 打开归档。

## 快速开始

### 下单终端（Python）

```bat
cd DLDS532_OrderApp
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python main.py
```

打包 EXE：`build_exe.bat`，产物在 `dist\DLDS532_OrderApp.exe`。

### 数据大屏（.NET 8）

```bat
cd 数据大屏
dotnet run --project src\DLDS532.App
```

自测：`dotnet run --project tests\DLDS532.SmokeTests`

打包安装程序：`installer\build-installer.bat`（需 Inno Setup）。

### PLC 工程

用 **TIA Portal V16** 打开 `DLDS-532_V16_v1.0/DLDS-532_V16_v1.0.zap16`（归档文件，打开时会提示解压）。

## 构建产物约定

`.venv/`、`dist/`、`bin/`、`obj/`、安装包输出、运行时数据库与日志均已列入 `.gitignore`，不入库；按各子工程 README 重新构建即可得到可执行文件。
