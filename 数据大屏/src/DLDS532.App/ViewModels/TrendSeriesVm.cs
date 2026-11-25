using System.Windows.Media;
using DLDS532.DataModels;

namespace DLDS532.App.ViewModels;

/// <summary>趋势图图例项：可勾选，勾选后曲线出现在图上。</summary>
public sealed class TrendSeriesVm : ObservableObject
{
    private bool _isSelected;
    private string _currentText = "--";

    public TrendSeriesVm(TrendSignal signal, Action changed)
    {
        Key = signal.Key;
        Label = signal.Label;
        Unit = signal.Unit;
        Decimals = signal.Decimals;
        Stroke = Freeze(signal.ColorHex);
        Changed = changed;
    }

    public string Key { get; }
    public string Label { get; }
    public string Unit { get; }
    public int Decimals { get; }
    public Brush Stroke { get; }
    private Action Changed { get; }

    public bool IsSelected
    {
        get => _isSelected;
        set
        {
            if (Set(ref _isSelected, value)) Changed();
        }
    }

    public string CurrentText
    {
        get => _currentText;
        set => Set(ref _currentText, value);
    }

    public string Caption => string.IsNullOrEmpty(Unit) ? Label : $"{Label} / {Unit}";

    private static Brush Freeze(string hex)
    {
        var brush = new SolidColorBrush((Color)ColorConverter.ConvertFromString(hex)!);
        brush.Freeze();
        return brush;
    }
}
