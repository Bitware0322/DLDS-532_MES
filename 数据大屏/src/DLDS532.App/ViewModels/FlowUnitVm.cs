using System.Collections.ObjectModel;
using System.Windows.Media;

namespace DLDS532.App.ViewModels;

/// <summary>工艺流程卡里的一行指标（标签固定，值随快照刷新）。</summary>
public sealed class FlowRowVm : ObservableObject
{
    private string _value = "--";
    private Brush _valueBrush = Palette.Value;

    public FlowRowVm(string label, string unit)
    {
        Label = label;
        Unit = unit;
    }

    public string Label { get; }
    public string Unit { get; }

    public string Value
    {
        get => _value;
        set => Set(ref _value, value);
    }

    public Brush ValueBrush
    {
        get => _valueBrush;
        set => Set(ref _valueBrush, value);
    }
}

/// <summary>
/// 产线工艺流程总览中的一个单元卡片。
/// 每个单元只反映**自己**的 DB120 数据，订单不同也照实显示，不做统一进度条。
/// </summary>
public sealed class FlowUnitVm : ObservableObject
{
    private string _stateText = "—";
    private Brush _stateBrush = Palette.Gray;
    private string _orderText = "--";
    private string _doneText = "未完成";
    private Brush _doneBrush = Palette.Gray;
    private bool _isActive;
    private bool _isFault;
    private bool _isOffline;

    public FlowUnitVm(string title, params (string Label, string Unit)[] rows)
    {
        Title = title;
        Rows = new ObservableCollection<FlowRowVm>(rows.Select(r => new FlowRowVm(r.Label, r.Unit)));
    }

    public string Title { get; }
    public ObservableCollection<FlowRowVm> Rows { get; }

    public string StateText
    {
        get => _stateText;
        set => Set(ref _stateText, value);
    }

    public Brush StateBrush
    {
        get => _stateBrush;
        set => Set(ref _stateBrush, value);
    }

    public string OrderText
    {
        get => _orderText;
        set => Set(ref _orderText, value);
    }

    public string DoneText
    {
        get => _doneText;
        set => Set(ref _doneText, value);
    }

    public Brush DoneBrush
    {
        get => _doneBrush;
        set => Set(ref _doneBrush, value);
    }

    /// <summary>正在加工：卡片轻微高亮 + 连接线流动。</summary>
    public bool IsActive
    {
        get => _isActive;
        set => Set(ref _isActive, value);
    }

    public bool IsFault
    {
        get => _isFault;
        set => Set(ref _isFault, value);
    }

    public bool IsOffline
    {
        get => _isOffline;
        set => Set(ref _isOffline, value);
    }
}

/// <summary>运行事件列表项（界面用）。</summary>
public sealed class RunEventVm
{
    public RunEventVm(DataModels.RunEventRecord record)
    {
        TimeText = record.TimeText;
        Unit = record.Unit;
        Message = record.Message;
        LevelText = record.Level switch
        {
            DataModels.RunEventLevel.Normal => "正常",
            DataModels.RunEventLevel.Info => "提示",
            DataModels.RunEventLevel.Warning => "警告",
            _ => "故障",
        };
        LevelBrush = record.Level switch
        {
            DataModels.RunEventLevel.Normal => Palette.Green,
            DataModels.RunEventLevel.Info => Palette.Accent,
            DataModels.RunEventLevel.Warning => Palette.Amber,
            _ => Palette.Red,
        };
    }

    public string TimeText { get; }
    public string Unit { get; }
    public string Message { get; }
    public string LevelText { get; }
    public Brush LevelBrush { get; }
}
