using System.Collections.ObjectModel;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Threading;
using DLDS532.DataModels;
using DLDS532.PlcData;
using DLDS532.Services;

namespace DLDS532.App.ViewModels;

/// <summary>左侧导航项。</summary>
public sealed class NavItem : ObservableObject
{
    private bool _isSelected;

    public NavItem(string glyph, string label, object? page, bool enabled, string tooltip)
    {
        Glyph = glyph;
        Label = label;
        Page = page;
        IsEnabled = enabled;
        Tooltip = tooltip;
    }

    public string Glyph { get; }
    public string Label { get; }
    public object? Page { get; }
    public bool IsEnabled { get; }
    public string Tooltip { get; }

    public bool IsSelected
    {
        get => _isSelected;
        set => Set(ref _isSelected, value);
    }
}

/// <summary>主窗口视图模型：顶部状态、左侧导航、页面切换与统一刷新节拍。</summary>
public sealed class MainViewModel : ObservableObject
{
    private readonly PollingService _polling;
    private readonly RunEventLog _eventLog;
    private readonly RunEventMonitor _eventMonitor = new();
    private readonly DispatcherTimer _timer;
    private object _currentPage;
    private DataFreshness _freshness = DataFreshness.Offline;

    public MainViewModel(PollingService polling, TrendBuffer trend, Db120Mapping mapping, string mappingPath,
        RunEventLog eventLog)
    {
        _polling = polling;
        _eventLog = eventLog;

        Dashboard = new DashboardViewModel(polling, trend);
        Comm = new CommViewModel(polling);
        Fields = new FieldsViewModel(polling, mapping);
        Settings = new SettingsViewModel(polling, mappingPath,
            mapping.Document.Fields.Count, mapping.Document.TotalBytes,
            mapping.Document.BlockName, mapping.Document.DbNumber);

        Dashboard.NavigateToUnit = index =>
        {
            ShowPage(2);
            Fields.FocusGroup(index);
        };

        _currentPage = Dashboard;

        NavItems = new ObservableCollection<NavItem>
        {
            new("总", "系统总览", Dashboard, true, "工业监控大屏"),
            new("通", "通信管理", Comm, true, "PLC 连接与通信统计"),
            new("单", "单元数据", Fields, true, "DB120 全部字段实时值"),
            new("趋", "历史趋势", null, false, "阶段五实现：SQLite 历史曲线与导出"),
            new("警", "报警管理", null, false, "阶段五实现：故障记录与恢复配对"),
            new("设", "系统设置", Settings, true, "通信参数与映射信息"),
        };
        NavItems[0].IsSelected = true;

        NavigateCommand = new RelayCommand(p =>
        {
            if (p is not NavItem item || !item.IsEnabled || item.Page is null) return;
            CurrentPage = item.Page;
            foreach (var nav in NavItems) nav.IsSelected = ReferenceEquals(nav, item);
        });

        _timer = new DispatcherTimer(DispatcherPriority.Background)
        {
            Interval = TimeSpan.FromMilliseconds(150),
        };
        _timer.Tick += (_, _) => Tick();
        _timer.Start();
    }

    public DashboardViewModel Dashboard { get; }
    public CommViewModel Comm { get; }
    public FieldsViewModel Fields { get; }
    public SettingsViewModel Settings { get; }

    public ObservableCollection<NavItem> NavItems { get; }

    public object CurrentPage
    {
        get => _currentPage;
        private set => Set(ref _currentPage, value);
    }

    public ICommand NavigateCommand { get; }

    public string AppTitle => "工业网络智能控制与维护可视化系统";

    public string AppSubtitle => "DLDS-532  ·  工业网络实训平台";

    public string VersionText => "v0.5.0  阶段二 · UI R4 · 模拟数据";

    public string TimeText => DateTime.Now.ToString("HH:mm:ss");

    public string DateText => DateTime.Now.ToString("yyyy-MM-dd  dddd", new System.Globalization.CultureInfo("zh-CN"));

    public string ConnText => _freshness switch
    {
        DataFreshness.Live => "通信正常",
        DataFreshness.Stale => _polling.IsDataFrozen ? "数据冻结" : "数据已过期",
        _ => _polling.State == ConnectionState.Faulted ? "通信中断" : "未连接",
    };

    public Brush ConnBrush => _freshness switch
    {
        DataFreshness.Live => Palette.Green,
        DataFreshness.Stale => Palette.Amber,
        _ => Palette.Red,
    };

    public string SourceBadge => _polling.Source.IsSimulation ? "模拟数据" : "实时数据";

    public Brush SourceBadgeBrush => _polling.Source.IsSimulation ? Palette.Amber : Palette.Green;

    public bool IsOffline => _freshness == DataFreshness.Offline;

    public string RefreshText => $"刷新 {_polling.Settings.PollIntervalMs} ms";

    public Brush RefreshBrush => _freshness switch
    {
        DataFreshness.Live => Palette.Green,
        DataFreshness.Stale => Palette.Amber,
        _ => Palette.Red,
    };

    public string EndpointText =>
        $"{_polling.Settings.IpAddress}:{_polling.Settings.Port}  ·  DB{_polling.Settings.DbNumber}  ·  {_polling.Settings.PollIntervalMs}ms";

    private void Tick()
    {
        // 事件采集保留：大屏不再显示，但记录仍写入，供阶段五报警/历史页使用
        _eventMonitor.Tick(_polling.Latest, _polling.State, _polling.Cpu, _polling.LastError, _eventLog);

        Dashboard.Refresh();
        Comm.Refresh();
        Fields.Refresh();

        var freshness = _polling.GetFreshness();
        bool changed = freshness != _freshness;
        _freshness = freshness;

        OnPropertyChanged(nameof(TimeText));
        OnPropertyChanged(nameof(DateText));
        OnPropertyChanged(nameof(IsOffline));

        if (changed)
        {
            OnPropertyChanged(nameof(ConnText));
            OnPropertyChanged(nameof(ConnBrush));
            OnPropertyChanged(nameof(RefreshBrush));
        }
    }

    /// <summary>按导航序号切换页面（0 总览 / 1 通信 / 2 单元 / 5 设置）。</summary>
    public void ShowPage(int index)
    {
        if (index < 0 || index >= NavItems.Count) return;
        var item = NavItems[index];
        if (item.Page is null) return;
        CurrentPage = item.Page;
        foreach (var nav in NavItems) nav.IsSelected = ReferenceEquals(nav, item);
    }

    public void Stop() => _timer.Stop();
}
