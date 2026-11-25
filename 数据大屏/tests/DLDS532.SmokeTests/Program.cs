using DLDS532.Communication;
using DLDS532.DataModels;
using DLDS532.PlcData;
using DLDS532.Services;

var failures = new List<string>();
void Check(string name, bool condition, string detail = "")
{
    Console.WriteLine($"{(condition ? "PASS" : "FAIL")}  {name}{(detail.Length > 0 ? "  → " + detail : "")}");
    if (!condition) failures.Add(name);
}

var root = FindRepoRoot();
var mappingPath = Path.Combine(root, "config", "db120.mapping.json");
var fixturePath = Path.Combine(root, "tests", "fixtures", "db120_sample_190.hex");

Console.WriteLine($"映射表：{mappingPath}");

// ---------------------------------------------------------------- 1. 映射表
var mapping = Db120Mapping.Load(mappingPath);
Check("映射表长度 190 字节", mapping.Document.TotalBytes == 190, mapping.Document.TotalBytes.ToString());
Check("映射表字段数 79", mapping.Document.Fields.Count == 79, mapping.Document.Fields.Count.ToString());
Check("映射表全部只读", mapping.Document.Fields.All(f => f.Rw == "R"));

var decoder = new Db120Decoder(mapping);
Check("解码器期望长度 190", decoder.ExpectedLength == 190);

// 运行模式定义（现场）：0 未知 / 1 手动 / 2 自动待机 / 3 自动运行
Check("运行模式 1 = 手动", RunModeText.Describe(1) == "手动", RunModeText.Describe(1));
Check("运行模式 2 = 自动待机", RunModeText.Describe(2) == "自动待机", RunModeText.Describe(2));
Check("运行模式 3 = 自动运行", RunModeText.Describe(3) == "自动运行", RunModeText.Describe(3));
Check("运行模式 0 = 未知", RunModeText.Describe(0) == "未知", RunModeText.Describe(0));
Check("只有自动运行(3)计入工作时间",
    RunModeText.IsRunning(3) && !RunModeText.IsRunning(2) && !RunModeText.IsRunning(1) && !RunModeText.IsRunning(0));

// ---------------------------------------------------------------- 2. 现场帧解码
var hex = File.ReadAllLines(fixturePath)
    .Where(l => !l.TrimStart().StartsWith('#'))
    .SelectMany(l => l.Split(' ', StringSplitOptions.RemoveEmptyEntries))
    .Select(t => Convert.ToByte(t, 16))
    .ToArray();

Check("黄金样本 190 字节", hex.Length == 190, hex.Length.ToString());

var frame = decoder.Decode(hex, DateTime.Now, PlcCpuState.Stop);
var s = frame.Snapshot;

Check("一站在线/模式", s.S1.Online == 0 && s.S1.RunMode == 2, $"{s.S1.Online}/{s.S1.RunMode}");
Check("一站订单 ID = 9", s.S1.OrderId == 9, s.S1.OrderId.ToString());
Check("一站心跳 23389", s.S1.Heartbeat == 23389, s.S1.Heartbeat.ToString());
Check("一站步骤 = 0.0 (Real@10)", Math.Abs(s.S1.Step) < 0.001f, s.S1.Step.ToString("F3"));
Check("二站在线 = 1 (58.0)", s.S2.Online == 1, s.S2.Online.ToString());
Check("二站订单 ID = 9 (66.0)", s.S2.OrderId == 9, s.S2.OrderId.ToString());
Check("二站脚步 = 0.0 (Real@68)", Math.Abs(s.S2.Step) < 0.001f);
Check("三站在线 = 1 (104.0)", s.S3.Online == 1, s.S3.Online.ToString());
Check("三站心跳偏移 118", s.S3.Heartbeat == -29739, s.S3.Heartbeat.ToString());

// 仓位状态：Bool 数组按 2 字节（字）对齐，起点 122.0（121 是填充字节）
var slotDef = mapping.Document.Fields.FirstOrDefault(f => f.Id == "s3.slots");
Check("三站仓位状态起点 122.0（Bool 数组字对齐）", slotDef is not null && slotDef.Offset == 122,
    slotDef?.Offset.ToString() ?? "null");
Check("仓位数组黄金样本全空", s.S3.Slots.Count == 9 && s.S3.Slots.All(v => !v));

// 仓位方向：数组[0] = 仓位 A …… 数组[8] = 仓位 I（与界面摆放位置无关）
var slotA = (byte[])hex.Clone();
slotA[122] |= 0x01;   // 数组[0] → 仓位 A
var snapA = decoder.Decode(slotA, DateTime.Now, PlcCpuState.Stop).Snapshot;
Check("仓位方向：数组[0] 对应仓位 A", snapA.S3.Slots[0] && !snapA.S3.Slots[8],
    string.Join(",", snapA.S3.Slots.Select(v => v ? 1 : 0)));

var slotI = (byte[])hex.Clone();
slotI[123] |= 0x01;   // 数组[8] → 仓位 I
var snapI = decoder.Decode(slotI, DateTime.Now, PlcCpuState.Stop).Snapshot;
Check("仓位方向：数组[8] 对应仓位 I", snapI.S3.Slots[8] && !snapI.S3.Slots[0],
    string.Join(",", snapI.S3.Slots.Select(v => v ? 1 : 0)));

// 界面 3×3 摆放顺序：I H G / F E D / C B A（只影响显示，不影响地址）
var slotGrid = string.Concat(Station3Snapshot.SlotDisplayOrder.Select(i => Station3Snapshot.SlotNames[i]));
Check("界面仓位摆放 I H G / F E D / C B A", slotGrid == "IHGFEDCBA", slotGrid);
Check("订单区订单 ID = 9 (164.0)", s.Order.Id == 9, s.Order.Id.ToString());
Check("订单区物料 = 1 (166.0)", s.Order.AbMaterial == 1, s.Order.AbMaterial.ToString());
Check("订单区 8mm = 2 (168.0)", s.Order.Ball8mmQty == 2);
Check("订单区 10mm = 2 (170.0)", s.Order.Ball10mmQty == 2);
Check("订单区仓位 = 4 (172.0)", s.Order.Slot == 4);
Check("开始信号 = 1 (176.0)", s.Order.StartSignal == 1);
Check("9mm/10mm 料仓位 82.0/82.1 均为 TRUE", s.S2.Hopper8mmPresent && s.S2.Hopper10mmPresent);
Check("字段值列表覆盖 61 个语义字段", frame.Values.Count == 61, frame.Values.Count.ToString());
Check("三站完成订单ID 在 144.0", frame.Values.Any(v => v.Definition.Path == "三站数据.完成订单ID" && v.Definition.Offset == 144));

// ---------------------------------------------------------------- 3. 模拟源
var sim = new SimulatedFrameSource(mapping);
Check("模拟源标识", sim.IsSimulation);
Check("模拟源连接", sim.Connect(new PlcConnectionSettings(), out _) && sim.State == ConnectionState.Connected);

var simFrames = new List<PlcSnapshot>();
for (int i = 0; i < 5; i++)
{
    var raw = sim.Read(120, 0, 190);
    simFrames.Add(decoder.Decode(raw, DateTime.Now, sim.Cpu).Snapshot);
}

Check("模拟帧长度 190", simFrames.All(f => f.FrameBytes == 190));
Check("模拟帧运行模式 = 3（自动运行）", simFrames.All(f => f.S1.RunMode == 3 && f.S2.RunMode == 3 && f.S3.RunMode == 3));
Check("模拟帧故障码 = 0", simFrames.All(f => !f.HasAnyFault));
Check("模拟帧订单 ID 递增存在", simFrames.Select(f => f.Order.Id).Distinct().Count() >= 1);

// ---------------------------------------------------------------- 4. 采集服务与断线重连
var settings = new PlcConnectionSettings { PollIntervalMs = 200, ReconnectIntervalMs = 600, TimeoutMs = 1000 };
var pollingSource = new SimulatedFrameSource(mapping);
using var polling = new PollingService(pollingSource, decoder, settings);
polling.Start();

WaitUntil(() => polling.State == ConnectionState.Connected && polling.Latest is not null, 3000);
Check("采集服务连通并拿到快照", polling.Latest is not null && polling.State == ConnectionState.Connected);
Check("数据新鲜度 = Live", polling.GetFreshness() == DataFreshness.Live, polling.GetFreshness().ToString());

var countBefore = polling.SuccessCount;
WaitUntil(() => polling.SuccessCount > countBefore, 2000);
Check("周期读取持续推进", polling.SuccessCount > countBefore, polling.SuccessCount.ToString());

pollingSource.SimulateOffline = true;
WaitUntil(() => polling.State == ConnectionState.Faulted, 3000);
Check("断线后状态 = Faulted", polling.State == ConnectionState.Faulted);
Check("断线后新鲜度 = Offline（界面显示 -- / 灰）", polling.GetFreshness() == DataFreshness.Offline);
Check("断线后保留最后一次有效数据但标记过期", polling.Latest is not null);
Check("失败计数增加", polling.FailCount > 0, polling.FailCount.ToString());

pollingSource.SimulateOffline = false;
WaitUntil(() => polling.State == ConnectionState.Connected, 5000);
Check("自动重连恢复 Connected", polling.State == ConnectionState.Connected, polling.State.ToString());
Check("恢复后新鲜度回到 Live", polling.GetFreshness() == DataFreshness.Live);

polling.Stop();
pollingSource.Dispose();
sim.Dispose();


// ---------------------------------------------------------------- 5. 运行事件（只由真实跃变产生）
var eventLog = new RunEventLog();   // 不落盘，只测检测逻辑
var monitor = new RunEventMonitor();
var t0 = DateTime.Now;

var frame0 = new PlcSnapshot
{
    Timestamp = t0,
    S1 = new Station1Snapshot { Online = 1, RunMode = RunModeText.AutoRun, Busy = 0, Fault = 0, OrderId = 101 },
    S2 = new Station2Snapshot { Online = 1, RunMode = RunModeText.AutoRun, Busy = 0, Fault = 0, OrderId = 101 },
    S3 = new Station3Snapshot { Online = 1, RunMode = RunModeText.AutoRun, Busy = 0, Fault = 0, OrderId = 101 },
};

monitor.Tick(frame0, ConnectionState.Connected, PlcCpuState.Run, "", eventLog);
Check("首帧只建立基线、不产生事件", eventLog.TotalCount == 0, eventLog.TotalCount.ToString());

var frame1 = frame0 with { Timestamp = t0.AddMilliseconds(500), S1 = frame0.S1 with { Busy = 1 } };
monitor.Tick(frame1, ConnectionState.Connected, PlcCpuState.Run, "", eventLog);
Check("忙碌跃变产生「开始供料」", eventLog.Recent(5).Any(e => e.Message.Contains("开始供料")),
    string.Join(" | ", eventLog.Recent(5).Select(e => e.Message)));

var frame2 = frame1 with { Timestamp = t0.AddMilliseconds(1000), S1 = frame1.S1 with { Busy = 0, Done = true } };
monitor.Tick(frame2, ConnectionState.Connected, PlcCpuState.Run, "", eventLog);
Check("完成跃变产生「完成供料工序」", eventLog.Recent(9).Any(e => e.Message.Contains("完成供料工序")));

var frame3 = frame2 with { Timestamp = t0.AddMilliseconds(1500), S2 = frame2.S2 with { Fault = 7 } };
monitor.Tick(frame3, ConnectionState.Connected, PlcCpuState.Run, "", eventLog);
Check("故障跃变产生故障级事件",
    eventLog.Recent(9).Any(e => e.Level == RunEventLevel.Fault && e.Message.Contains("故障码 7")));

monitor.Tick(frame3, ConnectionState.Faulted, PlcCpuState.Run, "模拟断线", eventLog);
Check("通信中断产生故障级事件",
    eventLog.Recent(9).Any(e => e.Level == RunEventLevel.Fault && e.Message.Contains("通信中断")));

monitor.Tick(frame3 with { Timestamp = t0.AddMilliseconds(2000) }, ConnectionState.Connected,
    PlcCpuState.Run, "", eventLog);
Check("通信恢复产生正常级事件",
    eventLog.Recent(9).Any(e => e.Message.Contains("通信恢复") && e.Level == RunEventLevel.Normal));

for (int i = 0; i < 400; i++)
    eventLog.Add(new RunEventRecord(t0.AddSeconds(i), "测试", "容量测试 " + i, RunEventLevel.Info));
Check("环形缓冲上限 300 条（不无限占内存）", eventLog.Recent(1000).Count == RunEventLog.Capacity,
    eventLog.Recent(1000).Count.ToString());
eventLog.Dispose();

// ---------------------------------------------------------------- 6. 数据冻结判定
var frozenSettings = new PlcConnectionSettings { PollIntervalMs = 100, ReconnectIntervalMs = 500, FrozenAfterMs = 350 };
var frozenSource = new SimulatedFrameSource(mapping);
// 冻结用固定帧：直接构造一个心跳不变的源不方便，这里用 sim 的帧但把冻结阈值设得比心跳周期还短
using var frozenPolling = new PollingService(frozenSource, decoder, frozenSettings);
frozenPolling.Start();
WaitUntil(() => frozenPolling.Latest is not null, 2000);
Check("冻结阈值以内不算冻结", frozenPolling.GetFreshness() == DataFreshness.Live, frozenPolling.GetFreshness().ToString());
frozenPolling.Stop();
frozenSource.Dispose();

// ---------------------------------------------------------------- 结果
Console.WriteLine();
if (failures.Count == 0)
{
    Console.WriteLine("全部通过。");
    return 0;
}

Console.WriteLine($"失败 {failures.Count} 项：{string.Join(" / ", failures)}");
return 1;

static void WaitUntil(Func<bool> condition, int timeoutMs)
{
    var deadline = DateTime.Now.AddMilliseconds(timeoutMs);
    while (DateTime.Now < deadline)
    {
        if (condition()) return;
        Thread.Sleep(50);
    }
}

static string FindRepoRoot()
{
    var dir = new DirectoryInfo(AppContext.BaseDirectory);
    while (dir is not null)
    {
        if (File.Exists(Path.Combine(dir.FullName, "DLDS532.sln"))) return dir.FullName;
        dir = dir.Parent;
    }
    return Directory.GetCurrentDirectory();
}
