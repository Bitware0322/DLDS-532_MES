using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Windows.Input;
using System.Windows.Media;
using DLDS532.DataModels;
using DLDS532.Services;

namespace DLDS532.App.ViewModels;

/// <summary>系统设置页（阶段二）：通信参数、DB 映射信息、刷新与重连策略。</summary>
public sealed class SettingsViewModel : ObservableObject
{
    private static readonly CultureInfo Inv = CultureInfo.InvariantCulture;

    private readonly PollingService _polling;
    private readonly string _mappingPath;

    private string _ipAddress;
    private string _rack;
    private string _slot;
    private string _port;
    private string _dbNumber;
    private string _pollInterval;
    private string _timeout;
    private string _reconnectInterval;
    private bool _autoReconnect;
    private DataSourceMode _dataSource;
    private string _message = "";
    private Brush _messageBrush = Palette.TextMuted;

    /// <summary>数据源切换后由 App 重建帧源（真实 PLC ↔ 模拟）。</summary>
    public event Action<DataSourceMode>? SourceModeChanged;

    public SettingsViewModel(PollingService polling, string mappingPath, int fieldCount, int totalBytes, string blockName, int dbNumber)
    {
        _polling = polling;
        _mappingPath = mappingPath;
        FieldCount = fieldCount;
        TotalBytes = totalBytes;
        BlockName = blockName;
        DbNumber = dbNumber;

        var s = polling.Settings;
        _ipAddress = s.IpAddress;
        _rack = s.Rack.ToString(Inv);
        _slot = s.Slot.ToString(Inv);
        _port = s.Port.ToString(Inv);
        _dbNumber = s.DbNumber.ToString(Inv);
        _pollInterval = s.PollIntervalMs.ToString(Inv);
        _timeout = s.TimeoutMs.ToString(Inv);
        _reconnectInterval = s.ReconnectIntervalMs.ToString(Inv);
        _autoReconnect = s.AutoReconnect;
        _dataSource = s.DataSource;

        ApplyCommand = new RelayCommand(Apply);
        SetRealModeCommand = new RelayCommand(() => DataSource = DataSourceMode.RealPlc);
        SetSimulationModeCommand = new RelayCommand(() => DataSource = DataSourceMode.Simulation);
        ResetCommand = new RelayCommand(() => LoadFrom(_polling.Settings));
        OpenFolderCommand = new RelayCommand(() =>
        {
            try
            {
                Process.Start(new ProcessStartInfo("explorer.exe", $"/select,\"{_mappingPath}\"") { UseShellExecute = true });
            }
            catch (Exception ex)
            {
                SetMessage("打开目录失败：" + ex.Message, Palette.Red);
            }
        });
    }

    public int FieldCount { get; }
    public int TotalBytes { get; }
    public string BlockName { get; }
    public int DbNumber { get; }
    public string MappingPath => _mappingPath;

    public string MappingSummary => $"{BlockName} · DB{DbNumber} · {TotalBytes} 字节 · {FieldCount} 字段";

    public string IpAddress { get => _ipAddress; set => Set(ref _ipAddress, value); }
    public string Rack { get => _rack; set => Set(ref _rack, value); }
    public string Slot { get => _slot; set => Set(ref _slot, value); }
    public string Port { get => _port; set => Set(ref _port, value); }
    public string DbNumberText { get => _dbNumber; set => Set(ref _dbNumber, value); }
    public string PollInterval { get => _pollInterval; set => Set(ref _pollInterval, value); }
    public string Timeout { get => _timeout; set => Set(ref _timeout, value); }
    public string ReconnectInterval { get => _reconnectInterval; set => Set(ref _reconnectInterval, value); }

    public bool AutoReconnect
    {
        get => _autoReconnect;
        set => Set(ref _autoReconnect, value);
    }

    public DataSourceMode DataSource
    {
        get => _dataSource;
        set
        {
            if (!Set(ref _dataSource, value)) return;
            OnPropertyChanged(nameof(IsRealMode));
            OnPropertyChanged(nameof(IsSimulationMode));
            OnPropertyChanged(nameof(DataSourceText));
        }
    }

    public bool IsRealMode => _dataSource == DataSourceMode.RealPlc;

    public bool IsSimulationMode => _dataSource == DataSourceMode.Simulation;

    public string DataSourceText => IsRealMode
        ? "真实 PLC：只读 192.168.40.115 的 DB120"
        : "模拟数据：按真实偏移生成帧，仅用于无 PLC 时演示";

    public ICommand SetRealModeCommand { get; }
    public ICommand SetSimulationModeCommand { get; }

    public string Message
    {
        get => _message;
        private set => Set(ref _message, value);
    }

    public Brush MessageBrush
    {
        get => _messageBrush;
        private set => Set(ref _messageBrush, value);
    }

    public ICommand ApplyCommand { get; }
    public ICommand ResetCommand { get; }
    public ICommand OpenFolderCommand { get; }

    private void Apply()
    {
        if (!int.TryParse(_rack, out var rack) || rack is < 0 or > 7)
        {
            SetMessage("Rack 需为 0 ~ 7 的整数。", Palette.Red);
            return;
        }
        if (!int.TryParse(_slot, out var slot) || slot is < 0 or > 31)
        {
            SetMessage("Slot 需为 0 ~ 31 的整数。", Palette.Red);
            return;
        }
        if (!int.TryParse(_port, out var port) || port is < 1 or > 65535)
        {
            SetMessage("端口需为 1 ~ 65535。", Palette.Red);
            return;
        }
        if (!int.TryParse(_dbNumber, out var db) || db <= 0)
        {
            SetMessage("DB 块编号必须为正整数。", Palette.Red);
            return;
        }
        if (!int.TryParse(_pollInterval, out var poll) || poll is < 100 or > 5000)
        {
            SetMessage("刷新周期需在 100 ~ 5000 ms 之间。", Palette.Red);
            return;
        }
        if (!int.TryParse(_timeout, out var timeout) || timeout is < 200 or > 10000)
        {
            SetMessage("连接超时需在 200 ~ 10000 ms 之间。", Palette.Red);
            return;
        }
        if (!int.TryParse(_reconnectInterval, out var reconnect) || reconnect is < 500 or > 60000)
        {
            SetMessage("重连间隔需在 500 ~ 60000 ms 之间。", Palette.Red);
            return;
        }
        if (string.IsNullOrWhiteSpace(_ipAddress))
        {
            SetMessage("PLC IP 不能为空。", Palette.Red);
            return;
        }
        if (db != DbNumber)
        {
            SetMessage($"映射表对应 DB{DbNumber}，当前填的是 DB{db}；改 DB 号需同时替换映射表。", Palette.Amber);
            return;
        }

        var previousMode = _polling.Settings.DataSource;
        var updated = _polling.Settings with
        {
            DataSource = _dataSource,
            IpAddress = _ipAddress.Trim(),
            Rack = rack,
            Slot = slot,
            Port = port,
            DbNumber = db,
            PollIntervalMs = poll,
            TimeoutMs = timeout,
            ReconnectIntervalMs = reconnect,
            AutoReconnect = _autoReconnect,
        };

        _polling.UpdateSettings(updated);

        if (!AppSettingsStore.Save(updated, out var saveError))
            SetMessage("参数已生效，但写入配置文件失败：" + saveError, Palette.Amber);

        if (updated.DataSource != previousMode)
        {
            SourceModeChanged?.Invoke(updated.DataSource);
            SetMessage(updated.DataSource == DataSourceMode.RealPlc
                ? "已切换到真实 PLC 模式，正在连接 192.168.40.115 …"
                : "已切换到模拟数据模式（界面会标注「模拟数据」）。", Palette.Green);
            return;
        }

        SetMessage(updated.DataSource == DataSourceMode.Simulation
            ? "参数已保存。当前为模拟数据源，IP / 机架 / 槽位在切回真实 PLC 后生效。"
            : "参数已保存，下个刷新周期生效。", Palette.Green);
    }

    private void LoadFrom(DataModels.PlcConnectionSettings s)
    {
        IpAddress = s.IpAddress;
        Rack = s.Rack.ToString(Inv);
        Slot = s.Slot.ToString(Inv);
        Port = s.Port.ToString(Inv);
        DbNumberText = s.DbNumber.ToString(Inv);
        PollInterval = s.PollIntervalMs.ToString(Inv);
        Timeout = s.TimeoutMs.ToString(Inv);
        ReconnectInterval = s.ReconnectIntervalMs.ToString(Inv);
        AutoReconnect = s.AutoReconnect;
        SetMessage("已恢复为当前生效参数。", Palette.TextMuted);
    }

    private void SetMessage(string text, Brush brush)
    {
        Message = text;
        MessageBrush = brush;
    }
}
