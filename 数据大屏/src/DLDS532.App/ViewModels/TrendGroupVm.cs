using DLDS532.DataModels;

namespace DLDS532.App.ViewModels;

/// <summary>趋势分组页签：同一量纲的曲线共用一条纵坐标。</summary>
public sealed class TrendGroupVm : ObservableObject
{
    private bool _isSelected;

    public TrendGroupVm(TrendUnitGroup group)
    {
        Key = group.Key;
        Label = group.Label;
        Unit = group.Unit;
        Signals = group.Signals;
    }

    public string Key { get; }
    public string Label { get; }
    public string Unit { get; }
    public IReadOnlyList<TrendSignal> Signals { get; }

    public string Caption => string.IsNullOrEmpty(Unit) ? Label : $"{Label} · {Unit}";

    public bool IsSelected
    {
        get => _isSelected;
        set => Set(ref _isSelected, value);
    }
}
