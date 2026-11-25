using System.Collections.ObjectModel;
using System.Globalization;
using System.Windows.Threading;
using DLDS532.PlcData;
using DLDS532.Services;

namespace DLDS532.App.ViewModels;

/// <summary>DB120 一个字段的实时行。</summary>
public sealed class FieldRowVm : ObservableObject
{
    private string _value = "--";

    public FieldRowVm(FieldDef def)
    {
        Def = def;
        Name = def.Path.Contains('.') ? def.Path.Split('.', 2)[1] : def.Path;
        Address = def.IsArray
            ? $"{def.Offset}.0 起"
            : def.Bit is { } bit ? $"{def.Offset}.{bit}" : $"{def.Offset}.0";
    }

    public FieldDef Def { get; }
    public string Name { get; }
    public string TypeLabel => Def.Type;
    public string Address { get; }
    public string Note => Def.Note;
    public bool Show => Def.Show;

    public string Value
    {
        get => _value;
        set => Set(ref _value, value);
    }
}

public sealed class FieldGroupVm : ObservableObject
{
    private bool _isHighlighted;

    public FieldGroupVm(string title, string caption, IEnumerable<FieldRowVm> rows)
    {
        Title = title;
        Caption = caption;
        Rows = new ObservableCollection<FieldRowVm>(rows);
    }

    public string Title { get; }
    public string Caption { get; }
    public ObservableCollection<FieldRowVm> Rows { get; }

    /// <summary>从大屏点击单元卡片跳转过来时短暂高亮，帮助定位。</summary>
    public bool IsHighlighted
    {
        get => _isHighlighted;
        set => Set(ref _isHighlighted, value);
    }
}

/// <summary>单元数据页：把 DB120 全部字段按四个区域原样列出（含保留位与保留数组）。</summary>
public sealed class FieldsViewModel : ObservableObject
{
    private static readonly CultureInfo Inv = CultureInfo.InvariantCulture;

    private readonly PollingService _polling;
    private readonly Db120Mapping _mapping;
    private readonly Dictionary<string, FieldRowVm> _byId = new();
    private DateTime _last = DateTime.MinValue;

    private readonly DispatcherTimer _highlightTimer = new() { Interval = TimeSpan.FromSeconds(4) };

    public FieldsViewModel(PollingService polling, Db120Mapping mapping)
    {
        _polling = polling;
        _mapping = mapping;
        Groups = BuildGroups();

        _highlightTimer.Tick += (_, _) =>
        {
            _highlightTimer.Stop();
            foreach (var group in Groups) group.IsHighlighted = false;
        };
    }

    /// <summary>聚焦到某个区域（0 一站 / 1 二站 / 2 三站 / 3 订单）。</summary>
    public void FocusGroup(int index)
    {
        if (index < 0 || index >= Groups.Count) return;
        for (int i = 0; i < Groups.Count; i++) Groups[i].IsHighlighted = i == index;
        _highlightTimer.Stop();
        _highlightTimer.Start();
    }

    public IReadOnlyList<FieldGroupVm> Groups { get; }

    public string SummaryText =>
        $"DB{_mapping.Document.DbNumber} · {_mapping.Document.BlockName} · {_mapping.Document.TotalBytes} 字节 · {_mapping.Document.Fields.Count} 个字段（{_byId.Count} 个有语义）· 全部只读";

    public string UpdatedText => _polling.Latest is { } s ? "数据时间 " + s.Timestamp.ToString("HH:mm:ss.fff") : "等待数据";

    public void Refresh()
    {
        var frame = _polling.LatestFrame;
        if (frame is null || frame.Snapshot.Timestamp == _last) return;

        _last = frame.Snapshot.Timestamp;
        foreach (var value in frame.Values)
        {
            if (_byId.TryGetValue(value.Definition.Id, out var row))
                row.Value = value.Text;
        }
        OnPropertyChanged(nameof(UpdatedText));
    }

    private IReadOnlyList<FieldGroupVm> BuildGroups()
    {
        var definitions = new (string Group, string Title)[]
        {
            ("station1", "一站数据 · 自动供料"),
            ("station2", "二站数据 · 智能分拣"),
            ("station3", "三站数据 · 智能仓储"),
            ("order", "订单数据"),
        };

        var groups = new List<FieldGroupVm>(definitions.Length);
        foreach (var (group, title) in definitions)
        {
            var fields = _mapping.Document.Fields
                .Where(f => f.Group == group)
                .OrderBy(f => f.Offset)
                .ToList();

            var rows = fields.Select(f =>
            {
                var row = new FieldRowVm(f);
                if (f.Id.Length > 0) _byId[f.Id] = row;
                return row;
            }).ToList();

            int start = fields.Count > 0 ? fields[0].Offset : 0;
            int end = fields.Count > 0 ? fields.Max(f => f.Offset + Math.Max(f.Bytes, 1)) : 0;
            var caption = $"{fields.Count} 字段 · 偏移 {start} ~ {end - 1}（{end - start} 字节）";

            groups.Add(new FieldGroupVm(title, caption, rows));
        }
        return groups;
    }
}
