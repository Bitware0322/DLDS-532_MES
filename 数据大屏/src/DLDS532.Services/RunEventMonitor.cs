using DLDS532.DataModels;

namespace DLDS532.Services;

/// <summary>
/// 运行事件检测器：对比相邻两帧的 DB120 数据与连接状态，只在**真实发生跃变**时产生事件。
/// 不做任何推测、不生成模拟事件；没有变化就没有记录。
/// </summary>
public sealed class RunEventMonitor
{
    private sealed class StationPrev
    {
        public bool Valid;
        public int Online = -1;
        public int RunMode = -1;
        public int Busy = -1;
        public int Fault = -1;
        public int OrderId = -1;
        public bool Done;
        public bool Received;
    }

    private readonly Dictionary<string, StationPrev> _prev = new()
    {
        ["s1"] = new StationPrev(),
        ["s2"] = new StationPrev(),
        ["s3"] = new StationPrev(),
    };

    private bool _primed;
    private ConnectionState _prevConn = ConnectionState.Disconnected;
    private PlcCpuState _prevCpu = PlcCpuState.Unknown;

    /// <param name="snapshot">最新快照，null 表示本轮没有取到数据。</param>
    public void Tick(PlcSnapshot? snapshot, ConnectionState connection, PlcCpuState cpu,
        string lastError, RunEventLog log)
    {
        var now = DateTime.Now;

        if (!_primed)
        {
            _primed = true;
            _prevConn = connection;
            _prevCpu = cpu;
            if (snapshot is not null) CaptureAll(snapshot);
            return;
        }

        // 通信与 CPU 状态跃变
        if (connection != _prevConn)
        {
            if (connection is ConnectionState.Connected)
            {
                Emit(log, now, "通信", _prevConn == ConnectionState.Disconnected
                    ? "PLC 通信已建立"
                    : "PLC 通信恢复", RunEventLevel.Normal);
            }
            else if (connection is ConnectionState.Faulted)
            {
                var reason = string.IsNullOrWhiteSpace(lastError) ? "读取失败" : lastError;
                Emit(log, now, "通信", "PLC 通信中断：" + Shorten(reason, 48), RunEventLevel.Fault);
            }
            else if (connection is ConnectionState.Disconnected)
            {
                Emit(log, now, "通信", "已断开与 PLC 的连接", RunEventLevel.Warning);
            }

            _prevConn = connection;
        }

        if (cpu != _prevCpu && cpu != PlcCpuState.Unknown)
        {
            if (cpu == PlcCpuState.Stop)
                Emit(log, now, "通信", "PLC 进入 STOP，数据已冻结", RunEventLevel.Warning);
            else if (cpu == PlcCpuState.Run && _prevCpu == PlcCpuState.Stop)
                Emit(log, now, "通信", "PLC 恢复 RUN", RunEventLevel.Normal);

            _prevCpu = cpu;
        }

        if (snapshot is null) return;

        Compare("s1", "自动供料单元", "供料",
            snapshot.S1.Online, snapshot.S1.RunMode, snapshot.S1.Busy, snapshot.S1.Fault,
            snapshot.S1.OrderId, snapshot.S1.Done, snapshot.S1.Received, log, now);

        Compare("s2", "智能分拣单元", "灌注",
            snapshot.S2.Online, snapshot.S2.RunMode, snapshot.S2.Busy, snapshot.S2.Fault,
            snapshot.S2.OrderId, snapshot.S2.Done, snapshot.S2.Received, log, now);

        Compare("s3", "智能仓储单元", "入库",
            snapshot.S3.Online, snapshot.S3.RunMode, snapshot.S3.Busy, snapshot.S3.Fault,
            snapshot.S3.OrderId, snapshot.S3.Done, snapshot.S3.Received, log, now);
    }

    private void Compare(string key, string unit, string action,
        int online, int runMode, int busy, int fault, int orderId, bool done, bool received,
        RunEventLog log, DateTime now)
    {
        var prev = _prev[key];
        if (!prev.Valid)
        {
            prev.Online = online;
            prev.RunMode = runMode;
            prev.Busy = busy;
            prev.Fault = fault;
            prev.OrderId = orderId;
            prev.Done = done;
            prev.Received = received;
            prev.Valid = true;
            return;
        }

        // 故障：0 → 非 0 记故障，非 0 → 0 记恢复
        if (prev.Fault == 0 && fault != 0)
            Emit(log, now, unit, $"发生故障，故障码 {fault}", RunEventLevel.Fault);
        else if (prev.Fault != 0 && fault == 0)
            Emit(log, now, unit, "故障已恢复", RunEventLevel.Normal);

        // 在线状态
        if (prev.Online != online)
        {
            if (online == 0)
                Emit(log, now, unit, "单元离线", RunEventLevel.Warning);
            else if (online == 1 && prev.Online == 0)
                Emit(log, now, unit, "单元恢复在线", RunEventLevel.Normal);
        }

        // 运行模式
        if (prev.RunMode != runMode)
        {
            var (text, level) = runMode switch
            {
                RunModeText.AutoRun => ("进入自动运行", RunEventLevel.Normal),
                RunModeText.AutoStandby => ("进入自动待机", RunEventLevel.Info),
                RunModeText.Manual => ("切换为手动模式", RunEventLevel.Info),
                _ => ($"运行模式变更为未知值 {runMode}", RunEventLevel.Warning),
            };
            Emit(log, now, unit, text, level);
        }

        // 订单
        if (prev.OrderId != orderId && orderId != 0)
        {
            if (prev.OrderId != 0)
                Emit(log, now, unit, $"订单切换 {prev.OrderId} → {orderId}", RunEventLevel.Info);
            else
                Emit(log, now, unit, $"载入订单 {orderId}", RunEventLevel.Info);
        }

        if (!prev.Received && received)
            Emit(log, now, unit, $"已接收订单 {orderId}", RunEventLevel.Info);

        if (prev.Busy != 1 && busy == 1)
            Emit(log, now, unit, $"开始{action}" + (orderId != 0 ? $"（订单 {orderId}）" : ""), RunEventLevel.Info);

        if (!prev.Done && done)
            Emit(log, now, unit, $"完成{action}工序", RunEventLevel.Normal);

        prev.Online = online;
        prev.RunMode = runMode;
        prev.Busy = busy;
        prev.Fault = fault;
        prev.OrderId = orderId;
        prev.Done = done;
        prev.Received = received;
    }

    private void CaptureAll(PlcSnapshot s)
    {
        Seed("s1", s.S1.Online, s.S1.RunMode, s.S1.Busy, s.S1.Fault, s.S1.OrderId, s.S1.Done, s.S1.Received);
        Seed("s2", s.S2.Online, s.S2.RunMode, s.S2.Busy, s.S2.Fault, s.S2.OrderId, s.S2.Done, s.S2.Received);
        Seed("s3", s.S3.Online, s.S3.RunMode, s.S3.Busy, s.S3.Fault, s.S3.OrderId, s.S3.Done, s.S3.Received);
    }

    private void Seed(string key, int online, int runMode, int busy, int fault,
        int orderId, bool done, bool received)
    {
        var prev = _prev[key];
        prev.Online = online;
        prev.RunMode = runMode;
        prev.Busy = busy;
        prev.Fault = fault;
        prev.OrderId = orderId;
        prev.Done = done;
        prev.Received = received;
        prev.Valid = true;
    }

    private static void Emit(RunEventLog log, DateTime time, string unit, string message, RunEventLevel level) =>
        log.Add(new RunEventRecord(time, unit, message, level));

    private static string Shorten(string text, int max) =>
        text.Length <= max ? text : text[..max] + "…";
}
