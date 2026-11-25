using System.Globalization;
using System.Windows.Input;
using System.Windows.Media;
using DLDS532.Communication;
using DLDS532.DataModels;
using DLDS532.Services;

namespace DLDS532.App.ViewModels;

/// <summary>PLC 通信管理页：连接参数、统计、心跳与手动控制。</summary>
public sealed class CommViewModel : ObservableObject
{
    private static readonly CultureInfo Inv = CultureInfo.InvariantCulture;

    private readonly PollingService _polling;
    private readonly SimulatedFrameSource? _simulator;
    private bool _autoReconnect;

    public CommViewModel(PollingService polling)
    {
        _polling = polling;
        _simulator = polling.Source as SimulatedFrameSource;
        _autoReconnect = polling.Settings.AutoReconnect;

        ConnectCommand = new RelayCommand(() =>
        {
            _polling.ConnectNow(out _);
            OnAllChanged();
        });

        DisconnectCommand = new RelayCommand(() =>
        {
            _polling.DisconnectNow();
            OnAllChanged();
        });

        ToggleOfflineCommand = new RelayCommand(() =>
        {
            if (_simulator is null) return;
            _simulator.SimulateOffline = !_simulator.SimulateOffline;
            OnAllChanged();
        });
    }

    public void Refresh() => OnAllChanged();

    public bool IsSimulation => _polling.Source.IsSimulation;

    public string SourceName => _polling.Source.DisplayName;

    public string EndpointText =>
        $"{_polling.Settings.IpAddress}:{_polling.Settings.Port}   Rack {_polling.Settings.Rack} / Slot {_polling.Settings.Slot}";

    public string DbText => $"DB{_polling.Settings.DbNumber}";

    public string FrameText => $"{_polling.ExpectedFrameBytes} B";

    public string PollText => $"{_polling.Settings.PollIntervalMs} ms";

    public string TimeoutText => $"{_polling.Settings.TimeoutMs} ms";

    public string StateText => _polling.State switch
    {
        ConnectionState.Connected => "已连接",
        ConnectionState.Connecting => "连接中",
        ConnectionState.Faulted => "通信异常",
        _ => "未连接",
    };

    public Brush StateBrush => _polling.State switch
    {
        ConnectionState.Connected => Palette.Green,
        ConnectionState.Connecting => Palette.Amber,
        ConnectionState.Faulted => Palette.Red,
        _ => Palette.Gray,
    };

    public string CpuText => _polling.Cpu switch
    {
        PlcCpuState.Run => "RUN",
        PlcCpuState.Stop => "STOP",
        _ => "未知",
    };

    public Brush CpuBrush => _polling.Cpu switch
    {
        PlcCpuState.Run => Palette.Green,
        PlcCpuState.Stop => Palette.Amber,
        _ => Palette.Gray,
    };

    public string ConnectedForText => _polling.ConnectedAt is { } at
        ? (DateTime.Now - at).ToString(@"hh\:mm\:ss")
        : "—";

    public string SuccessText => _polling.SuccessCount.ToString(Inv);

    public string FailText => _polling.FailCount.ToString(Inv);

    public string LatencyText => _polling.LastSuccessAt is null
        ? "--"
        : _polling.LastLatency.TotalMilliseconds.ToString("F1", Inv) + " ms";

    public string LastSuccessText => _polling.LastSuccessAt?.ToString("HH:mm:ss.fff") ?? "—";

    public string LastAttemptText => _polling.LastAttemptAt?.ToString("HH:mm:ss.fff") ?? "—";

    public string SuccessRateText
    {
        get
        {
            long ok = _polling.SuccessCount, fail = _polling.FailCount;
            if (ok + fail == 0) return "—";
            return (ok * 100.0 / (ok + fail)).ToString("F2", Inv) + " %";
        }
    }

    public string FramesText => _polling.SuccessCount.ToString(Inv);

    public string BytesText
    {
        get
        {
            long bytes = _polling.SuccessCount * _polling.ExpectedFrameBytes;
            return bytes < 1024 * 1024
                ? (bytes / 1024.0).ToString("F0", Inv) + " KB"
                : (bytes / 1024.0 / 1024.0).ToString("F1", Inv) + " MB";
        }
    }

    public string ErrorText => string.IsNullOrWhiteSpace(_polling.LastError) ? "无" : _polling.LastError;

    public Brush ErrorBrush => string.IsNullOrWhiteSpace(_polling.LastError) ? Palette.TextMuted : Palette.Amber;

    public string HeartbeatS1Text => Heartbeat(_polling.Latest?.S1.Heartbeat);
    public string HeartbeatS2Text => Heartbeat(_polling.Latest?.S2.Heartbeat);
    public string HeartbeatS3Text => Heartbeat(_polling.Latest?.S3.Heartbeat);

    public string HeartbeatChangeText
    {
        get
        {
            var s = _polling.Latest;
            if (s is null) return "—";
            return $"一站 {Heartbeat(s.S1.Heartbeat)} / 二站 {Heartbeat(s.S2.Heartbeat)} / 三站 {Heartbeat(s.S3.Heartbeat)}";
        }
    }

    public bool AutoReconnect
    {
        get => _autoReconnect;
        set
        {
            if (!Set(ref _autoReconnect, value)) return;
            _polling.UpdateSettings(_polling.Settings with { AutoReconnect = value });
            OnPropertyChanged(nameof(AutoReconnectText));
        }
    }

    public string AutoReconnectText => _autoReconnect ? "已开启" : "已关闭";

    public string SimulatedOfflineText => _simulator switch
    {
        null => "真实 PLC 不支持模拟断线",
        { SimulateOffline: true } => "模拟断线中（读取将失败）",
        _ => "点击切断模拟链路，验证自动重连",
    };

    public Brush SimulatedOfflineBrush =>
        _simulator is { SimulateOffline: true } ? Palette.Red : Palette.TextLabel;

    public bool CanSimulateOffline => _simulator is not null;

    public ICommand ConnectCommand { get; }
    public ICommand DisconnectCommand { get; }
    public ICommand ToggleOfflineCommand { get; }

    private static string Heartbeat(int? value) => value is null ? "--" : (value.Value & 0xFFFF).ToString(Inv);
}
