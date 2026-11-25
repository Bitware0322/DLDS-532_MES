using System.Collections.ObjectModel;
using System.Globalization;
using System.Windows.Input;
using System.Windows.Media;
using DLDS532.DataModels;
using DLDS532.Services;

namespace DLDS532.App.ViewModels;

/// <summary>
/// 系统总览大屏视图模型。
/// 所有数值都由 PollingService 发布的最新快照推导，界面层不做任何测量逻辑，
/// 也不存在"没有数据时补 0"的分支 —— 无数据一律显示 --。
/// </summary>
public sealed class DashboardViewModel : ObservableObject
{
    private static readonly CultureInfo Inv = CultureInfo.InvariantCulture;
    private static readonly CultureInfo Zh = new("zh-CN");

    private readonly PollingService _polling;
    private readonly TrendBuffer _trend;

    private readonly WorkingTimeTracker _work1 = new();
    private readonly WorkingTimeTracker _work2 = new();
    private readonly WorkingTimeTracker _work3 = new();

    private PlcSnapshot? _snap;
    private DateTime _lastSnapshotAt = DateTime.MinValue;
    private DateTime _lastTick = DateTime.Now;
    private DateTime _lastTrendAdd = DateTime.MinValue;
    private DataFreshness _freshness = DataFreshness.Offline;
    private bool _isPaused;
    private double _windowMinutes = 5;
    private int _trendPoints;
    private int _lastOrderId;
    private int _completedOrders;


    public DashboardViewModel(PollingService polling, TrendBuffer trend)
    {
        _polling = polling;
        _trend = trend;

        AllSeries = TrendSignals.All
            .Select(s => new TrendSeriesVm(s, () => OnPropertyChanged(nameof(SelectedSeriesText))))
            .ToList();

        TrendGroups = new ObservableCollection<TrendGroupVm>(
            TrendSignals.Groups.Select(g => new TrendGroupVm(g)));

        ChartSeries = new ObservableCollection<TrendSeriesVm>();
        GroupSeries = new ObservableCollection<TrendSeriesVm>();
        SetGroup(TrendGroups[0]);

        FlowUnits = new[]
        {
            new FlowUnitVm("自动供料单元", ("当前工艺步骤", "")),
            new FlowUnitVm("智能分拣单元", ("8mm 灌注", "颗"), ("10mm 灌注", "颗")),
            new FlowUnitVm("智能仓储单元", ("称重数据", "g"), ("产品合格状态", "")),
        };



        // 界面按现场物理排布摆放（A 在右下角）；数据本身仍按 A..I 顺序存放
        Slots = new ObservableCollection<SlotVm>(
            Station3Snapshot.SlotDisplayOrder.Select(i => new SlotVm(i, Station3Snapshot.SlotNames[i])));

        PauseCommand = new RelayCommand(() => IsPaused = !IsPaused);
        ClearTrendCommand = new RelayCommand(() =>
        {
            _trend.Clear();
            _trendPoints = 0;
            OnAllChanged();
        });
        SetWindowCommand = new RelayCommand(p =>
        {
            if (p is null) return;
            WindowMinutes = double.Parse(p.ToString()!, Inv);
        });
        ToggleSeriesCommand = new RelayCommand(p =>
        {
            if (p is not TrendSeriesVm s) return;
            s.IsSelected = !s.IsSelected;
            if (s.IsSelected)
            {
                if (!ChartSeries.Contains(s)) ChartSeries.Add(s);
            }
            else
            {
                ChartSeries.Remove(s);
            }
            OnPropertyChanged(nameof(SelectedSeriesText));
        });

        SelectGroupCommand = new RelayCommand(p =>
        {
            if (p is TrendGroupVm g) SetGroup(g);
        });

        OpenUnitCommand = new RelayCommand(p =>
        {
            if (p is not null && int.TryParse(p.ToString(), out var index))
                NavigateToUnit?.Invoke(index);
        });

    }

    // ────────────────────────────────────────────── 刷新（UI 线程定时调用）

    public void Refresh()
    {
        var now = DateTime.Now;
        var dt = now - _lastTick;
        if (dt > TimeSpan.FromSeconds(2)) dt = TimeSpan.FromSeconds(2);
        _lastTick = now;

        var latest = _polling.Latest;
        if (latest is not null && latest.Timestamp != _lastSnapshotAt)
        {
            _lastSnapshotAt = latest.Timestamp;
            _snap = latest;

            TrackCompletedOrders(latest);

            if (!_isPaused && (latest.Timestamp - _lastTrendAdd).TotalMilliseconds >= 950)
            {
                _lastTrendAdd = latest.Timestamp;
                _trend.Add(latest);
                _trendPoints = _trend.Count(TrendSignals.S2Inject8);
            }

            UpdateFlowUnits(latest);
            UpdateSlotStates(latest);
            UpdateSeriesValues(latest);
        }

        if (_snap is null)
            foreach (var slot in Slots) slot.IsUnknown = true;

        _freshness = _polling.GetFreshness();

        if (_snap is not null && _freshness == DataFreshness.Live)
        {
            _work1.Accumulate(dt, RunModeText.IsRunning(_snap.S1.RunMode));
            _work2.Accumulate(dt, RunModeText.IsRunning(_snap.S2.RunMode));
            _work3.Accumulate(dt, RunModeText.IsRunning(_snap.S3.RunMode));
        }

        OnAllChanged();
    }

    private TrendGroupVm? _activeGroup;

    private void SetGroup(TrendGroupVm group)
    {
        _activeGroup = group;
        foreach (var g in TrendGroups) g.IsSelected = ReferenceEquals(g, group);

        ChartSeries.Clear();
        GroupSeries.Clear();
        foreach (var key in group.Signals.Select(sig => sig.Key))
        {
            var series = AllSeries.FirstOrDefault(s => s.Key == key);
            if (series is null) continue;
            series.IsSelected = true;
            GroupSeries.Add(series);
            ChartSeries.Add(series);
        }

        OnPropertyChanged(nameof(ChartUnit));
        OnPropertyChanged(nameof(ChartGroupCaption));
        OnPropertyChanged(nameof(SelectedSeriesText));
    }

    private void TrackCompletedOrders(PlcSnapshot snapshot)
    {
        if (_lastOrderId != 0 && snapshot.Order.Id != _lastOrderId && snapshot.Order.Id != 0)
            _completedOrders++;

        _lastOrderId = snapshot.Order.Id;
    }

    private void UpdateSlotStates(PlcSnapshot snapshot)
    {
        // 按每个灯的 DataIndex 取数：界面顺序 ≠ 数据顺序，不能直接用循环下标
        foreach (var slot in Slots)
        {
            slot.IsUnknown = false;
            slot.Occupied = slot.DataIndex < snapshot.S3.Slots.Count && snapshot.S3.Slots[slot.DataIndex];
        }
    }

    private void UpdateSeriesValues(PlcSnapshot s) => ApplyValues(s);

    private void ApplyValues(PlcSnapshot s)
    {
        foreach (var series in AllSeries)
        {
            var (value, decimals) = series.Key switch
            {
                TrendSignals.S1Depth => (s.S1.Depth, 3),
                TrendSignals.S1TurnAngle => (s.S1.TurntableAngle, 1),
                TrendSignals.S2Inject8 => (s.S2.Inject8mm, 0),
                TrendSignals.S2Inject10 => (s.S2.Inject10mm, 0),
                TrendSignals.S3Weight => (s.S3.Weight, 0),
                TrendSignals.S3AxisX => (s.S3.AxisX, 2),
                TrendSignals.S3AxisY => (s.S3.AxisY, 2),
                _ => (0f, 2),
            };
            series.CurrentText = value.ToString("F" + decimals, Inv);
        }
    }

    /// <summary>
    /// 更新三张流程卡。每个单元只取自己的 DB120 字段，
    /// 三个单元订单不同也照实显示，不拼成一条统一进度。
    /// </summary>
    private void UpdateFlowUnits(PlcSnapshot s)
    {
        ApplyFlow(FlowUnits[0], s.S1.Online, s.S1.RunMode, s.S1.Busy, s.S1.Fault, s.S1.OrderId, s.S1.Done);
        FlowUnits[0].Rows[0].Value = Real(s.S1.Step, 2);

        ApplyFlow(FlowUnits[1], s.S2.Online, s.S2.RunMode, s.S2.Busy, s.S2.Fault, s.S2.OrderId, s.S2.Done);
        FlowUnits[1].Rows[0].Value = Num(s.S2.Inject8mm);
        FlowUnits[1].Rows[1].Value = Num(s.S2.Inject10mm);

        ApplyFlow(FlowUnits[2], s.S3.Online, s.S3.RunMode, s.S3.Busy, s.S3.Fault, s.S3.OrderId, s.S3.Done);
        FlowUnits[2].Rows[0].Value = s.S3.Weight.ToString(Inv);
        FlowUnits[2].Rows[1].Value = s.S3.QualityState == 0 ? "未判定" : s.S3.QualityState.ToString(Inv);
        FlowUnits[2].Rows[1].ValueBrush = s.S3.QualityState == 1 ? Palette.Green : Palette.Value;
    }

    private static void ApplyFlow(FlowUnitVm unit, int online, int runMode, int busy, int fault,
        int orderId, bool done)
    {
        unit.OrderText = orderId == 0 ? "无" : orderId.ToString(Inv);
        unit.IsFault = fault != 0;
        unit.IsOffline = online == 0;
        unit.IsActive = busy == 1;

        (unit.StateText, unit.StateBrush) = FlowState(online, runMode, busy, fault);
        unit.DoneText = done ? "已完成" : "未完成";
        unit.DoneBrush = done ? Palette.Green : Palette.Gray;
    }

    private static (string Text, Brush Brush) FlowState(int online, int runMode, int busy, int fault)
    {
        if (fault != 0) return ($"故障码 {fault}", Palette.Red);
        if (online == 0) return ("离线", Palette.Gray);
        if (busy == 1) return ("加工中", Palette.Accent);
        // 运行模式文字与「运行模式」指标统一取自 RunModeText，避免两处口径不一致
        return (RunModeText.Describe(runMode), ModeBrush(runMode));
    }


    // ────────────────────────────────────────────── 顶部栏

    public string DateText => DateTime.Now.ToString("yyyy-MM-dd dddd", Zh);

    public string TimeText => DateTime.Now.ToString("HH:mm:ss");

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

    public string FreshnessDetail => _freshness switch
    {
        DataFreshness.Live => $"数据时间 {(_snap?.Timestamp ?? DateTime.Now):HH:mm:ss}",
        DataFreshness.Stale =>
            $"数据已过期 {Math.Max(0, (DateTime.Now - (_snap?.Timestamp ?? DateTime.Now)).TotalSeconds):F1}s",
        _ => string.IsNullOrWhiteSpace(_polling.LastError) ? "等待连接" : Truncate(_polling.LastError, 42),
    };

    /// <summary>普通数值：实时为灰白，过期转橙，离线转灰。关键测量值在 XAML 里单独指定青色。</summary>
    public Brush ValueBrush => _freshness switch
    {
        DataFreshness.Live => Palette.Value,
        DataFreshness.Stale => Palette.Amber,
        _ => Palette.TextMuted,
    };

    public bool S1IsFault => _snap is { } s && s.S1.Fault != 0;
    public bool S2IsFault => _snap is { } s && s.S2.Fault != 0;
    public bool S3IsFault => _snap is { } s && s.S3.Fault != 0;
    public bool HasFault => S1IsFault || S2IsFault || S3IsFault;

    public string StationSummary =>
        (_snap is null ? "等待数据" : $"一站在线 {(_snap.S1.Online == 1 ? "是" : "否")} · 二站 {(_snap.S2.Online == 1 ? "是" : "否")} · 三站 {(_snap.S3.Online == 1 ? "是" : "否")}");

    // ────────────────────────────────────────────── 数据管理单元

    public string DbStateText => _freshness == DataFreshness.Live ? "正常" : "异常";

    public Brush DbStateBrush => _freshness == DataFreshness.Live ? Palette.Green : Palette.Red;

    public string LatencyText => _polling.LastSuccessAt is null ? "--" : _polling.LastLatency.TotalMilliseconds.ToString("F1", Inv);

    public string PollText => _polling.Settings.PollIntervalMs.ToString(Inv);

    public string FrameText => (_snap?.FrameBytes ?? _polling.ExpectedFrameBytes).ToString(Inv);

    public string S1OnlineText => OnlineText(_snap?.S1.Online);
    public Brush S1OnlineBrush => OnlineBrush(_snap?.S1.Online);
    public string S2OnlineText => OnlineText(_snap?.S2.Online);
    public Brush S2OnlineBrush => OnlineBrush(_snap?.S2.Online);
    public string S3OnlineText => OnlineText(_snap?.S3.Online);
    public Brush S3OnlineBrush => OnlineBrush(_snap?.S3.Online);

    public string S1HeartbeatText => HeartbeatText(_snap?.S1.Heartbeat);
    public string S2HeartbeatText => HeartbeatText(_snap?.S2.Heartbeat);
    public string S3HeartbeatText => HeartbeatText(_snap?.S3.Heartbeat);

    public string UpdateText => _snap is null ? "--:--:--" : _snap.Timestamp.ToString("HH:mm:ss.fff");

    public string TrendPointText => _trendPoints.ToString(Inv) + " 点";

    // ────────────────────────────────────────────── 一站：自动供料

    public string S1ModeText => _snap is null ? "—" : RunModeText.Describe(_snap.S1.RunMode);
    public Brush S1ModeBrush => _snap is null ? Palette.Gray : ModeBrush(_snap.S1.RunMode);
    public string S1BusyText => _snap is null ? "—" : BusyText.Describe(_snap.S1.Busy);
    public Brush S1BusyBrush => _snap?.S1.Busy == 1 ? Palette.Accent : Palette.TextLabel;
    public string S1FaultText => _snap is null ? "—" : _snap.S1.Fault == 0 ? "无故障" : $"故障码 {_snap.S1.Fault}";
    public Brush S1FaultBrush => _snap is null ? Palette.Gray : _snap.S1.Fault == 0 ? Palette.Green : Palette.Red;

    public string S1OrderText => Num(_snap?.S1.OrderId);
    public string S1StepText => Real(_snap?.S1.Step, 2);
    public string S1AngleText => Real(_snap?.S1.TurntableAngle, 1);
    public string S1RobotText => Real(_snap?.S1.RobotPosition, 1);
    public string S1DepthText => Real(_snap?.S1.Depth, 3);
    public string S1BoxText => Num(_snap?.S1.BoxUsed);
    public string S1AText => Num(_snap?.S1.MaterialA);
    public string S1BText => Num(_snap?.S1.MaterialB);
    public string S1ScanText => Num(_snap?.S1.ScanCode);

    /// <summary>A / B 料使用数合并为一个单元格，避免左侧卡片过度拥挤。</summary>
    public string S1MaterialText => _snap is null ? "-- / --" : $"{_snap.S1.MaterialA} / {_snap.S1.MaterialB}";
    public string S1DoneText => Bool(_snap?.S1.Done);
    public Brush S1DoneBrush => Lamp(_snap?.S1.Done);
    public string S1RecvText => Bool(_snap?.S1.Received);
    public Brush S1RecvBrush => Lamp(_snap?.S1.Received);
    public string S1WorkTimeText => _work1.Total.ToString(@"hh\:mm\:ss");

    // ────────────────────────────────────────────── 二站：智能分拣

    public string S2ModeText => _snap is null ? "—" : RunModeText.Describe(_snap.S2.RunMode);
    public Brush S2ModeBrush => _snap is null ? Palette.Gray : ModeBrush(_snap.S2.RunMode);
    public string S2BusyText => _snap is null ? "—" : BusyText.Describe(_snap.S2.Busy);
    public Brush S2BusyBrush => _snap?.S2.Busy == 1 ? Palette.Accent : Palette.TextLabel;
    public string S2FaultText => _snap is null ? "—" : _snap.S2.Fault == 0 ? "无故障" : $"故障码 {_snap.S2.Fault}";
    public Brush S2FaultBrush => _snap is null ? Palette.Gray : _snap.S2.Fault == 0 ? Palette.Green : Palette.Red;

    public string S2OrderText => Num(_snap?.S2.OrderId);
    public string S2StepText => Real(_snap?.S2.Step, 2);
    public string S2Inject8Text => Num(_snap?.S2.Inject8mm);
    public string S2Inject10Text => Num(_snap?.S2.Inject10mm);
    public string S2Hopper8Text => _snap is null ? "—" : _snap.S2.Hopper8mmPresent ? "有钢珠" : "无钢珠";
    public Brush S2Hopper8Brush => _snap is null ? Palette.Gray : _snap.S2.Hopper8mmPresent ? Palette.Green : Palette.Red;
    public string S2Hopper10Text => _snap is null ? "—" : _snap.S2.Hopper10mmPresent ? "有钢珠" : "无钢珠";
    public Brush S2Hopper10Brush => _snap is null ? Palette.Gray : _snap.S2.Hopper10mmPresent ? Palette.Green : Palette.Red;
    public string S2ScanText => Num(_snap?.S2.ScanCode);
    public string S2DoneText => Bool(_snap?.S2.Done);
    public Brush S2DoneBrush => Lamp(_snap?.S2.Done);
    public string S2RecvText => Bool(_snap?.S2.Received);
    public Brush S2RecvBrush => Lamp(_snap?.S2.Received);
    public string S2WorkTimeText => _work2.Total.ToString(@"hh\:mm\:ss");

    // ────────────────────────────────────────────── 三站：智能仓储

    public string S3ModeText => _snap is null ? "—" : RunModeText.Describe(_snap.S3.RunMode);
    public Brush S3ModeBrush => _snap is null ? Palette.Gray : ModeBrush(_snap.S3.RunMode);
    public string S3BusyText => _snap is null ? "—" : BusyText.Describe(_snap.S3.Busy);
    public Brush S3BusyBrush => _snap?.S3.Busy == 1 ? Palette.Accent : Palette.TextLabel;
    public string S3FaultText => _snap is null ? "—" : _snap.S3.Fault == 0 ? "无故障" : $"故障码 {_snap.S3.Fault}";
    public Brush S3FaultBrush => _snap is null ? Palette.Gray : _snap.S3.Fault == 0 ? Palette.Green : Palette.Red;

    public string S3OrderText => Num(_snap?.S3.OrderId);
    public string S3StepText => Real(_snap?.S3.Step, 2);
    public string S3InboundText => Num(_snap?.S3.InboundScan);
    public string S3StorageText => Num(_snap?.S3.StorageScan);
    public string S3WeightText => _snap is null ? "--" : _snap.S3.Weight.ToString(Inv);
    public string S3QualityText => _snap is null ? "—" : _snap.S3.QualityState == 0 ? "未判定" : _snap.S3.QualityState.ToString(Inv);
    public Brush S3QualityBrush => _snap is null ? Palette.Gray : _snap.S3.QualityState == 1 ? Palette.Green : Palette.TextLabel;
    public string S3OkText => Num(_snap?.S3.QualifiedCount);
    public string S3NgText => Num(_snap?.S3.UnqualifiedCount);
    public string S3DoneText => Bool(_snap?.S3.Done);
    public Brush S3DoneBrush => Lamp(_snap?.S3.Done);
    public string S3RecvText => Bool(_snap?.S3.Received);
    public Brush S3RecvBrush => Lamp(_snap?.S3.Received);
    public string S3WorkTimeText => _work3.Total.ToString(@"hh\:mm\:ss");
    public string SlotOccupiedText => _snap is null ? "--" : $"{_snap.S3.OccupiedSlots} / 9";

    public ObservableCollection<SlotVm> Slots { get; }

    // ────────────────────────────────────────────── 轴 / 订单分析 / 表格

    public string AxisTurnText => Real(_snap?.S1.TurntableAngle, 1);
    public string AxisRobotText => Real(_snap?.S1.RobotPosition, 1);
    public string AxisXText => Real(_snap?.S3.AxisX, 2);
    public string AxisYText => Real(_snap?.S3.AxisY, 2);

    public string CurOrderText => _snap is null ? "--" : _snap.Order.Id == 0 ? "0" : "1";
    public string BusyCountText => _snap?.BusyStationCount.ToString(Inv) ?? "--";
    public string CompletedText => _completedOrders.ToString(Inv);
    public string OkCountText => Num(_snap?.S3.QualifiedCount);
    public string NgCountText => Num(_snap?.S3.UnqualifiedCount);

    public double PassPercent
    {
        get
        {
            if (_snap is null) return 0;
            int ok = _snap.S3.QualifiedCount, ng = _snap.S3.UnqualifiedCount;
            return ok + ng == 0 ? 0 : ok * 100.0 / (ok + ng);
        }
    }

    public string PassRateText => _snap is null || _snap.S3.QualifiedCount + _snap.S3.UnqualifiedCount == 0
        ? "—"
        : PassPercent.ToString("F1", Inv) + " %";

    /// <summary>中央工艺流程总览的三张单元卡。</summary>
    public IReadOnlyList<FlowUnitVm> FlowUnits { get; }

    /// <summary>当前运行单元数（忙碌 = 1）。</summary>
    public string RunningStationsText => _snap is null ? "--" : _snap.BusyStationCount.ToString(Inv);

    /// <summary>当前故障单元数（故障码 ≠ 0）。</summary>
    public string FaultStationsText
    {
        get
        {
            if (_snap is null) return "--";
            int n = 0;
            if (_snap.S1.Fault != 0) n++;
            if (_snap.S2.Fault != 0) n++;
            if (_snap.S3.Fault != 0) n++;
            return n.ToString(Inv);
        }
    }

    public Brush FaultStationsBrush => FaultStationsText == "0" ? Palette.Green : Palette.Red;

    // ────────────────────────────────────────────── 趋势

    /// <summary>全部可记录曲线（用于刷新当前值显示）。</summary>
    public IReadOnlyList<TrendSeriesVm> AllSeries { get; }

    /// <summary>当前分组内被勾选的曲线（趋势图绑定它）。</summary>
    public ObservableCollection<TrendSeriesVm> ChartSeries { get; }

    /// <summary>当前分组的全部曲线（图例绑定它，取消勾选后仍可重新打开）。</summary>
    public ObservableCollection<TrendSeriesVm> GroupSeries { get; }

    public ObservableCollection<TrendGroupVm> TrendGroups { get; }

    public string ChartUnit => _activeGroup?.Unit ?? string.Empty;

    public string ChartGroupCaption => _activeGroup?.Caption ?? string.Empty;

    /// <summary>由主视图模型注入：点击单元卡片时跳转到单元数据页。</summary>
    public Action<int>? NavigateToUnit { get; set; }

    /// <summary>趋势图直接读取环形缓冲（只读窗口切片，渲染在 UI 线程完成）。</summary>
    public TrendBuffer TrendBuffer => _trend;

    public bool IsWindow5 => (int)WindowMinutes == 5;
    public bool IsWindow15 => (int)WindowMinutes == 15;
    public bool IsWindow30 => (int)WindowMinutes == 30;
    public bool IsWindow60 => (int)WindowMinutes == 60;

    public double WindowMinutes
    {
        get => _windowMinutes;
        private set
        {
            if (!Set(ref _windowMinutes, value)) return;
            OnPropertyChanged(nameof(WindowText));
            OnPropertyChanged(nameof(IsWindow5));
            OnPropertyChanged(nameof(IsWindow15));
            OnPropertyChanged(nameof(IsWindow30));
            OnPropertyChanged(nameof(IsWindow60));
        }
    }

    public string WindowText => $"{(int)WindowMinutes} 分钟";

    public bool IsPaused
    {
        get => _isPaused;
        set
        {
            if (Set(ref _isPaused, value)) OnPropertyChanged(nameof(PauseText));
        }
    }

    public string PauseText => IsPaused ? "继续" : "暂停";

    public string SelectedSeriesText =>
        $"采样周期 {_polling.Settings.PollIntervalMs} ms · 入图 1 s · 数据点 {_trendPoints}";

    public ICommand PauseCommand { get; }
    public ICommand ClearTrendCommand { get; }
    public ICommand SetWindowCommand { get; }
    public ICommand ToggleSeriesCommand { get; }
    public ICommand SelectGroupCommand { get; }
    public ICommand OpenUnitCommand { get; }

    // ────────────────────────────────────────────── 工具

    private static string OnlineText(int? online) => online switch
    {
        null => "—",
        1 => "在线",
        0 => "离线",
        _ => "异常",
    };

    private static Brush OnlineBrush(int? online) => online switch
    {
        null => Palette.Gray,
        1 => Palette.Green,
        0 => Palette.Gray,
        _ => Palette.Red,
    };

    /// <summary>心跳是 16 位自增计数器，会回绕成负数，按无符号显示。</summary>
    private static string HeartbeatText(int? heartbeat) =>
        heartbeat is null ? "--" : (heartbeat.Value & 0xFFFF).ToString(Inv);

    private static string Num(int? value) => value?.ToString(Inv) ?? "--";

    private static string Real(float? value, int decimals) =>
        value is null ? "--" : value.Value.ToString("F" + decimals, Inv);

    private static string Bool(bool? value) => value switch
    {
        null => "—",
        true => "是",
        false => "否",
    };

    private static Brush Lamp(bool? value) => value switch
    {
        null => Palette.Gray,
        true => Palette.Green,
        false => Palette.Gray,
    };

    /// <summary>运行模式配色：自动运行=绿、自动待机=橙、手动=常规文字、未知=灰。</summary>
    private static Brush ModeBrush(int mode) => mode switch
    {
        RunModeText.AutoRun => Palette.Green,
        RunModeText.AutoStandby => Palette.Amber,
        RunModeText.Manual => Palette.TextLabel,
        _ => Palette.Gray,
    };

    private static string Truncate(string text, int max) =>
        text.Length <= max ? text : text[..max] + "…";
}
