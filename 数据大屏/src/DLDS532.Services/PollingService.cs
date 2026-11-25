using DLDS532.Communication;
using DLDS532.DataModels;
using DLDS532.PlcData;

namespace DLDS532.Services;

/// <summary>
/// 采集服务：后台线程按周期读取 → 解码 → 发布不可变快照。
/// UI 线程只读取 Latest，永不阻塞在 PLC 上；通信中断不会让界面卡死。
/// </summary>
public sealed class PollingService : IDisposable
{
    private IPlcFrameSource _source;
    private readonly Db120Decoder _decoder;
    private PlcConnectionSettings _settings;

    private CancellationTokenSource? _cts;
    private Task? _loop;
    private int _started;

    private PlcSnapshot? _latest;
    private DecodedFrame? _latestFrame;
    private int _state = (int)ConnectionState.Disconnected;
    private int _cpu = (int)PlcCpuState.Unknown;

    private long _success;
    private long _fail;
    private long _latencyTicks;
    private long _lastSuccessTicks;
    private long _lastAttemptTicks;
    private long _connectedAtTicks;
    private string _lastError = "";
    private DateTime? _reconnectDue;

    private readonly int[] _lastHeartbeats = new int[3];
    private bool _heartbeatInitialized;
    private long _heartbeatChangedTicks = DateTime.Now.Ticks;

    public PollingService(IPlcFrameSource source, Db120Decoder decoder, PlcConnectionSettings settings)
    {
        _source = source;
        _decoder = decoder;
        _settings = settings;
    }

    public PlcConnectionSettings Settings => _settings;

    public IPlcFrameSource Source => _source;

    public PlcSnapshot? Latest => Volatile.Read(ref _latest);

    /// <summary>最近一次完整解码结果（含 61 个语义字段的原始显示值），供「单元数据」页使用。</summary>
    public DecodedFrame? LatestFrame => Volatile.Read(ref _latestFrame);

    public ConnectionState State => (ConnectionState)Volatile.Read(ref _state);

    public PlcCpuState Cpu => (PlcCpuState)Volatile.Read(ref _cpu);

    public long SuccessCount => Interlocked.Read(ref _success);

    public long FailCount => Interlocked.Read(ref _fail);

    public TimeSpan LastLatency => TimeSpan.FromTicks(Interlocked.Read(ref _latencyTicks));

    public DateTime? LastSuccessAt => FromTicks(Interlocked.Read(ref _lastSuccessTicks));

    public DateTime? LastAttemptAt => FromTicks(Interlocked.Read(ref _lastAttemptTicks));

    public DateTime? ConnectedAt => FromTicks(Interlocked.Read(ref _connectedAtTicks));

    public string LastError => Volatile.Read(ref _lastError);

    public int ExpectedFrameBytes => _decoder.ExpectedLength;

    /// <summary>解码完成事件（后台线程触发，订阅方需自行切回 UI 线程）。</summary>
    public event Action<DecodedFrame>? FrameDecoded;

    public void UpdateSettings(PlcConnectionSettings settings) => _settings = settings;

    public void Start()
    {
        if (Interlocked.Exchange(ref _started, 1) == 1) return;

        _cts = new CancellationTokenSource();
        _loop = Task.Run(() => RunAsync(_cts.Token));
    }

    public void Stop()
    {
        if (Interlocked.Exchange(ref _started, 0) == 0) return;
        _cts?.Cancel();
        try { _loop?.Wait(TimeSpan.FromSeconds(2)); } catch { /* 退出时不抛 */ }
        _cts?.Dispose();
        _cts = null;
    }

    /// <summary>立即尝试连接（同步，供「手动连接」按钮调用）。</summary>
    public bool ConnectNow(out string? error)
    {
        Volatile.Write(ref _state, (int)ConnectionState.Connecting);
        var ok = _source.Connect(_settings, out error);
        if (ok)
        {
            Volatile.Write(ref _state, (int)ConnectionState.Connected);
            Interlocked.Exchange(ref _connectedAtTicks, DateTime.Now.Ticks);
            Volatile.Write(ref _lastError, "");
            _reconnectDue = null;
        }
        else
        {
            Volatile.Write(ref _state, (int)ConnectionState.Faulted);
            Volatile.Write(ref _lastError, error ?? "连接失败");
        }
        return ok;
    }

    public void DisconnectNow()
    {
        _source.Disconnect();
        Volatile.Write(ref _state, (int)ConnectionState.Disconnected);
        Volatile.Write(ref _cpu, (int)PlcCpuState.Unknown);
        Interlocked.Exchange(ref _connectedAtTicks, 0);
    }

    /// <summary>通信正常但三站心跳长时间不变 —— 多半是 CPU 处于 STOP 或程序未刷新。</summary>
    public bool IsDataFrozen
    {
        get
        {
            if (!_heartbeatInitialized || State != ConnectionState.Connected) return false;
            var last = new DateTime(Interlocked.Read(ref _heartbeatChangedTicks));
            return (DateTime.Now - last).TotalMilliseconds > _settings.FrozenAfterMs;
        }
    }

    /// <summary>按当前时间评估数据新鲜度，界面据此决定数值是青色、变暗还是显示 --。</summary>
    public DataFreshness GetFreshness()
    {
        var latest = Latest;
        if (State is ConnectionState.Disconnected or ConnectionState.Faulted) return DataFreshness.Offline;
        if (latest is null) return DataFreshness.Offline;

        if (IsDataFrozen) return DataFreshness.Stale;
        if (Cpu == PlcCpuState.Stop) return DataFreshness.Stale;

        return (DateTime.Now - latest.Timestamp).TotalMilliseconds > _settings.StaleAfterMs
            ? DataFreshness.Stale
            : DataFreshness.Live;
    }

    private async Task RunAsync(CancellationToken token)
    {
        while (!token.IsCancellationRequested)
        {
            var interval = Math.Max(100, _settings.PollIntervalMs);
            var started = DateTime.Now;

            // 断开后（含读失败进入 Faulted）都要尝试重连，否则断线后再也不会恢复
            if (State != ConnectionState.Connected)
                TryConnect();

            if (State == ConnectionState.Connected)
                PollOnce();

            var elapsed = DateTime.Now - started;
            var wait = TimeSpan.FromMilliseconds(interval) - elapsed;
            if (wait < TimeSpan.FromMilliseconds(20)) wait = TimeSpan.FromMilliseconds(20);
            try { await Task.Delay(wait, token).ConfigureAwait(false); }
            catch (OperationCanceledException) { break; }
        }
    }

    private void TryConnect()
    {
        if (!_settings.AutoReconnect) return;
        if (State == ConnectionState.Connecting) return;
        if (_reconnectDue is { } due && DateTime.Now < due) return;

        Volatile.Write(ref _state, (int)ConnectionState.Connecting);
        if (_source.Connect(_settings, out var error))
        {
            Volatile.Write(ref _state, (int)ConnectionState.Connected);
            Interlocked.Exchange(ref _connectedAtTicks, DateTime.Now.Ticks);
            Volatile.Write(ref _lastError, "");
            _reconnectDue = null;
        }
        else
        {
            Volatile.Write(ref _state, (int)ConnectionState.Faulted);
            Volatile.Write(ref _lastError, error ?? "连接失败");
            _reconnectDue = DateTime.Now.AddMilliseconds(Math.Max(500, _settings.ReconnectIntervalMs));
        }
    }

    private void PollOnce()
    {
        Interlocked.Exchange(ref _lastAttemptTicks, DateTime.Now.Ticks);
        var sw = System.Diagnostics.Stopwatch.StartNew();
        try
        {
            var frame = _source.Read(_settings.DbNumber, 0, _decoder.ExpectedLength);
            sw.Stop();

            var decoded = _decoder.Decode(frame, DateTime.Now, _source.Cpu);
            Volatile.Write(ref _latest, decoded.Snapshot);
            Volatile.Write(ref _latestFrame, decoded);
            Volatile.Write(ref _cpu, (int)_source.Cpu);
            Interlocked.Increment(ref _success);
            Interlocked.Exchange(ref _latencyTicks, sw.Elapsed.Ticks);
            Interlocked.Exchange(ref _lastSuccessTicks, decoded.Snapshot.Timestamp.Ticks);
            Volatile.Write(ref _state, (int)ConnectionState.Connected);
            Volatile.Write(ref _lastError, "");

            TrackHeartbeat(decoded.Snapshot);
            FrameDecoded?.Invoke(decoded);
        }
        catch (Exception ex)
        {
            sw.Stop();
            Interlocked.Increment(ref _fail);
            Volatile.Write(ref _state, (int)ConnectionState.Faulted);
            Volatile.Write(ref _lastError, ex.Message);
            _reconnectDue = DateTime.Now.AddMilliseconds(Math.Max(500, _settings.ReconnectIntervalMs));

            if (!_settings.AutoReconnect)
                _source.Disconnect();
        }
    }

    private void TrackHeartbeat(PlcSnapshot snapshot)
    {
        bool changed = !_heartbeatInitialized
                       || snapshot.S1.Heartbeat != _lastHeartbeats[0]
                       || snapshot.S2.Heartbeat != _lastHeartbeats[1]
                       || snapshot.S3.Heartbeat != _lastHeartbeats[2];

        if (!changed) return;

        _heartbeatInitialized = true;
        _lastHeartbeats[0] = snapshot.S1.Heartbeat;
        _lastHeartbeats[1] = snapshot.S2.Heartbeat;
        _lastHeartbeats[2] = snapshot.S3.Heartbeat;
        Interlocked.Exchange(ref _heartbeatChangedTicks, DateTime.Now.Ticks);
    }

    /// <summary>
    /// 运行时切换数据源（真实 PLC ↔ 模拟）：先停采集循环，再换源重启。
    /// 统计与最后快照保留，界面无需重建。
    /// </summary>
    public void ReplaceSource(IPlcFrameSource source)
    {
        Stop();
        try { _source.Dispose(); } catch { /* 旧源释放失败忽略 */ }

        _source = source;
        _heartbeatInitialized = false;
        Interlocked.Exchange(ref _heartbeatChangedTicks, DateTime.Now.Ticks);
        Volatile.Write(ref _state, (int)ConnectionState.Disconnected);
        _reconnectDue = null;
        Start();
    }

    private static DateTime? FromTicks(long ticks) =>
        ticks <= 0 ? null : new DateTime(ticks, DateTimeKind.Local);

    public void Dispose()
    {
        Stop();
        _source.Dispose();
    }
}
