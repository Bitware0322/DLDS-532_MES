using System.Buffers.Binary;
using DLDS532.DataModels;
using DLDS532.PlcData;

namespace DLDS532.Communication;

/// <summary>
/// 模拟数据源：按映射表的真实偏移写入 190 字节帧，模拟一条单件流生产线的节拍。
/// 目的不是"看起来像"，而是让解码、绑定、趋势、报警整条链路在阶段二就被真实跑通；
/// 阶段三只需把本类替换为 S7 数据源，其余代码不动。
/// </summary>
public sealed class SimulatedFrameSource : IPlcFrameSource
{
    private const int OrderTicks = 48; // 24 秒一单（500ms/帧）

    private readonly Db120Mapping _mapping;
    private readonly Dictionary<string, FieldDef> _byId;
    private readonly Random _rng = new(20261123);
    private readonly byte[] _frame;
    private long _tick;
    private TimeSpan _latency = TimeSpan.FromMilliseconds(2);
    private int _sequence;

    /// <param name="startTick">起始节拍。默认从稳态开始，避免软件刚打开时整条线全为零。</param>
    public SimulatedFrameSource(Db120Mapping mapping, int startTick = 420)
    {
        _mapping = mapping;
        _byId = mapping.Document.Fields.Where(f => f.Id.Length > 0).ToDictionary(f => f.Id);
        _frame = new byte[mapping.Document.TotalBytes];
        _tick = startTick;
        State = ConnectionState.Disconnected;
        Advance();
    }

    public string DisplayName => "模拟数据源";

    public bool IsSimulation => true;

    public ConnectionState State { get; private set; }

    public PlcCpuState Cpu { get; private set; } = PlcCpuState.Unknown;

    public TimeSpan LastLatency => _latency;

    /// <summary>测试用：置 true 后读取抛异常，用于验证断线与重连逻辑。</summary>
    public bool SimulateOffline { get; set; }

    public bool Connect(PlcConnectionSettings settings, out string? error)
    {
        error = null;
        State = ConnectionState.Connecting;
        Thread.Sleep(220);
        State = ConnectionState.Connected;
        Cpu = PlcCpuState.Run;
        return true;
    }

    public void Disconnect()
    {
        State = ConnectionState.Disconnected;
        Cpu = PlcCpuState.Unknown;
    }

    public byte[] Read(int dbNumber, int start, int length)
    {
        if (State != ConnectionState.Connected)
            throw new InvalidOperationException("模拟数据源未连接。");

        if (SimulateOffline)
        {
            State = ConnectionState.Faulted;
            throw new IOException("模拟断线：无法读取 DB" + dbNumber + "。");
        }

        if (length != _frame.Length)
            throw new ArgumentOutOfRangeException(nameof(length),
                $"模拟帧长度固定为 {_frame.Length} 字节，请求 {length} 字节。");

        _tick++;
        Advance();

        _latency = TimeSpan.FromMilliseconds(1.2 + _rng.NextDouble() * 2.6);
        var sw = System.Diagnostics.Stopwatch.StartNew();
        while (sw.Elapsed < _latency) Thread.SpinWait(60);
        return (byte[])_frame.Clone();
    }

    public void Dispose()
    {
        State = ConnectionState.Disconnected;
    }

    // ------------------------------------------------------------ 模拟节拍

    private void Advance()
    {
        double sec = _tick * 0.5;
        int t = (int)(_tick % OrderTicks);
        int completed = (int)(_tick / OrderTicks);
        int orderNo = 100 + completed + 1;

        bool s1Busy = t <= 17;
        bool s2Busy = t is >= 8 and <= 33;
        bool s3Busy = t >= 24;

        float noise = (float)((_rng.NextDouble() - 0.5) * 0.08);

        SetInt("s1.online", 1);
        SetInt("s1.runMode", RunModeText.AutoRun);  // 3 = 自动运行（现场定义）
        SetInt("s1.busy", s1Busy ? 1 : 0);
        SetInt("s1.fault", 0);
        SetInt("s1.orderId", s1Busy ? orderNo : 0);
        SetReal("s1.step", s1Busy ? t / 18f * 6f : 0f);
        SetInt("s1.heartbeat", unchecked((short)(_tick % 32767)));
        SetBool("s1.done", t == 17);
        SetBool("s1.received", t is >= 0 and <= 2);
        SetInt("s1.scanCode", s1Busy ? orderNo : 0);
        SetReal("s1.turntableAngle", (float)(sec * 24 % 360));
        SetReal("s1.robotPos", s1Busy ? t / 18f * 120f : 0f);
        SetReal("s1.depth", 12.5f + 3.1f * (float)Math.Sin(sec * 0.06) + noise * 0.6f);
        SetInt("s1.boxUsed", 40 + completed * 2);
        SetInt("s1.matA", completed * 3);
        SetInt("s1.matB", completed * 2);

        SetInt("s2.online", 1);
        SetInt("s2.runMode", RunModeText.AutoRun);  // 3 = 自动运行（现场定义）
        SetInt("s2.busy", s2Busy ? 1 : 0);
        SetInt("s2.fault", 0);
        SetInt("s2.orderId", s2Busy ? orderNo : 0);
        SetReal("s2.step", s2Busy ? (t - 8) / 26f * 6f : 0f);
        SetInt("s2.heartbeat", unchecked((short)((_tick + 917) % 32767)));
        SetBool("s2.done", t == 33);
        SetBool("s2.received", t is >= 8 and <= 10);
        SetInt("s2.scanCode", s2Busy ? orderNo : 0);
        SetInt("s2.inject8", s2Busy ? Math.Min(8, (int)((t - 8) * 8f / 26f)) : 0);
        SetInt("s2.inject10", s2Busy ? Math.Min(6, (int)((t - 8) * 6f / 26f)) : 0);
        SetBool("s2.hopper8", true);
        SetBool("s2.hopper10", completed % 5 != 4);

        SetInt("s3.online", 1);
        SetInt("s3.runMode", RunModeText.AutoRun);  // 3 = 自动运行（现场定义）
        SetInt("s3.busy", s3Busy ? 1 : 0);
        SetInt("s3.fault", 0);
        SetInt("s3.orderId", s3Busy ? orderNo : 0);
        SetReal("s3.step", s3Busy ? (t - 24) / 24f * 6f : 0f);
        SetInt("s3.heartbeat", unchecked((short)((_tick + 2131) % 32767)));
        SetBool("s3.done", t == 47);
        SetBool("s3.received", t is >= 24 and <= 26);
        SetInt("s3.inboundScan", s3Busy ? orderNo : 0);
        SetInt("s3.storageScan", t >= 44 ? orderNo : 0);
        SetInt("s3.weight", s3Busy ? 218 + (int)(_rng.NextDouble() * 16) : 0);
        SetInt("s3.qualityState", t >= 42 ? 1 : 0);
        SetInt("s3.qualifiedCount", completed);
        SetInt("s3.unqualifiedCount", completed / 9);
        SetReal("s3.axisX", s3Busy ? (float)(150 + 145 * Math.Sin((t - 24) / 24.0 * Math.PI)) : 0f);
        SetReal("s3.axisY", s3Busy ? (float)(80 + 60 * Math.Cos((t - 24) / 24.0 * Math.PI)) : 0f);

        int filled = Math.Min(completed % 10, 9);
        // 数组[0]=仓位 A，按「从 A 开始占用」依次写入
        var slots = new bool[9];
        for (int i = 0; i < 9; i++) slots[i] = i < filled;
        SetBools("s3.slots", slots);

        SetInt("order.id", orderNo);
        SetInt("order.abMaterial", orderNo % 2 == 0 ? 2 : 1);
        SetInt("order.ball8mmQty", 8);
        SetInt("order.ball10mmQty", 6);
        SetInt("order.slot", filled % 9 + 1);
        SetBool("order.done", t == 47);
        SetInt("order.startSignal", t is >= 0 and <= 3 ? 1 : 0);
        SetInt("order.resetSignal", 0);

        _sequence++;
    }

    // ------------------------------------------------------------ 写入工具

    private void SetInt(string id, int value)
    {
        if (!_byId.TryGetValue(id, out var f)) return;
        BinaryPrimitives.WriteInt16BigEndian(_frame.AsSpan(f.Offset), (short)Math.Clamp(value, short.MinValue, short.MaxValue));
    }

    private void SetReal(string id, float value)
    {
        if (!_byId.TryGetValue(id, out var f)) return;
        BinaryPrimitives.WriteSingleBigEndian(_frame.AsSpan(f.Offset), value);
    }

    private void SetBool(string id, bool value)
    {
        if (!_byId.TryGetValue(id, out var f) || f.Bit is not { } bit) return;
        if (value) _frame[f.Offset] |= (byte)(1 << bit);
        else _frame[f.Offset] &= (byte)~(1 << bit);
    }

    private void SetBools(string id, bool[] values)
    {
        if (!_byId.TryGetValue(id, out var f) || f.Elements is null) return;
        foreach (var e in f.Elements)
        {
            if (e.Index < 0 || e.Index >= values.Length) continue;
            if (values[e.Index]) _frame[e.Byte] |= (byte)(1 << e.Bit);
            else _frame[e.Byte] &= (byte)~(1 << e.Bit);
        }
    }

    /// <summary>用于诊断显示：当前模拟帧序号。</summary>
    public int Sequence => _sequence;

    internal byte[] CurrentFrame => _frame;

    internal int FrameLength => _mapping.Document.TotalBytes;
}
