using System.Diagnostics;
using DLDS532.DataModels;
using S7.Net;

namespace DLDS532.Communication;

/// <summary>
/// 真实 PLC 帧源（唯一数据源：192.168.40.115 的 DB120）。
/// 只做两件事：Open 连接、ReadBytes 读一个 DB。
/// 类中**不存在任何写操作**（没有 Write/WriteBytes/WriteClass 调用），从代码层面保证只读。
/// </summary>
public sealed class S7FrameSource : IPlcFrameSource
{
    private readonly object _gate = new();
    private Plc? _plc;
    private PlcConnectionSettings _settings = new();
    private ConnectionState _state = ConnectionState.Disconnected;
    private PlcCpuState _cpu = PlcCpuState.Unknown;
    private TimeSpan _latency;

    public string DisplayName => "S7 实时数据";

    public bool IsSimulation => false;

    public ConnectionState State => _state;

    public PlcCpuState Cpu => _cpu;

    public TimeSpan LastLatency => _latency;

    /// <summary>最近一次连接的失败原因，供界面显示。</summary>
    public string LastError { get; private set; } = "";

    public bool Connect(PlcConnectionSettings settings, out string? error)
    {
        lock (_gate)
        {
            _settings = settings;
            CloseInternal();

            var plc = new Plc(CpuType.S71200, settings.IpAddress, (short)settings.Rack, (short)settings.Slot)
            {
                ReadTimeout = settings.TimeoutMs,
                WriteTimeout = settings.TimeoutMs,
            };

            try
            {
                // S7.Net 的 Open 在错误 IP 上可能阻塞到系统超时，这里自己箍一层超时
                var openTask = Task.Run(() => plc.Open());
                if (!openTask.Wait(Math.Max(500, settings.TimeoutMs)))
                    throw new TimeoutException($"连接超时（{settings.TimeoutMs} ms）");
                openTask.GetAwaiter().GetResult();

                if (!plc.IsConnected)
                    throw new InvalidOperationException("会话已建立但连接状态为断开");

                _plc = plc;
                _state = ConnectionState.Connected;
                _cpu = ReadCpuState(plc);
                LastError = "";
                error = null;
                return true;
            }
            catch (Exception ex)
            {
                var message = Describe(ex, settings);
                LastError = message;
                error = message;
                _state = ConnectionState.Faulted;
                _cpu = PlcCpuState.Unknown;
                try { plc.Close(); } catch { /* 清理失败忽略 */ }
                return false;
            }
        }
    }

    public void Disconnect()
    {
        lock (_gate)
        {
            CloseInternal();
            _state = ConnectionState.Disconnected;
            _cpu = PlcCpuState.Unknown;
        }
    }

    /// <summary>读取一帧；失败即抛异常，由上层标记通信异常。全程只读。</summary>
    public byte[] Read(int dbNumber, int start, int length)
    {
        lock (_gate)
        {
            if (_plc is null || _state != ConnectionState.Connected)
                throw new InvalidOperationException("PLC 未连接");

            var sw = Stopwatch.StartNew();
            try
            {
                var data = _plc.ReadBytes(DataType.DataBlock, dbNumber, start, length);
                sw.Stop();
                _latency = sw.Elapsed;

                if (data.Length != length)
                    throw new System.IO.InvalidDataException($"返回 {data.Length} 字节，期望 {length} 字节");

                return data;
            }
            catch (Exception ex)
            {
                sw.Stop();
                _state = ConnectionState.Faulted;
                _cpu = PlcCpuState.Unknown;
                LastError = ex.Message;
                CloseInternal();
                throw new IOException($"读取 DB{dbNumber} 失败：{ex.Message}", ex);
            }
        }
    }

    public void Dispose()
    {
        lock (_gate) CloseInternal();
    }

    private void CloseInternal()
    {
        if (_plc is null) return;
        try { _plc.Close(); } catch { /* 忽略关闭异常 */ }
        try { ((IDisposable)_plc).Dispose(); } catch { /* 忽略释放异常 */ }
        _plc = null;
    }

    /// <summary>
    /// 读取 CPU 状态。S7 SZL 0x0424 返回的是状态字节：本项目只把已现场验证过的 8（RUN）映射为 Run，
    /// 其余一律返回 Unknown —— 不去猜 STOP 的编码，冻结与否改由心跳停滞判定，避免误报。
    /// </summary>
    private PlcCpuState ReadCpuState(Plc plc)
    {
        try
        {
            var status = plc.ReadStatus();
            return status == 8 ? PlcCpuState.Run : PlcCpuState.Unknown;
        }
        catch
        {
            return PlcCpuState.Unknown;
        }
    }

    private static string Describe(Exception ex, PlcConnectionSettings settings)
    {
        var target = $"{settings.IpAddress}:{settings.Port} Rack{settings.Rack}/Slot{settings.Slot}";
        return ex switch
        {
            TimeoutException => $"连接 {target} 超时，请检查网线、IP 网段与防火墙",
            PlcException plcEx => $"S7 会话失败（{target}）：{plcEx.Message}。请确认 Rack/Slot、CPU 已允许 PUT/GET",
            System.Net.Sockets.SocketException sock => $"TCP 连接失败（{target}）：{sock.Message}",
            _ => $"连接 {target} 失败：{ex.Message}",
        };
    }
}
