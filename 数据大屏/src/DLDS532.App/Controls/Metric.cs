using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;

namespace DLDS532.App.Controls;

/// <summary>指标单元：上方标签、下方数值 + 单位。数值颜色由状态决定。</summary>
public class Metric : Control
{
    static Metric()
    {
        DefaultStyleKeyProperty.OverrideMetadata(typeof(Metric),
            new FrameworkPropertyMetadata(typeof(Metric)));
    }

    public static readonly DependencyProperty LabelProperty = DependencyProperty.Register(
        nameof(Label), typeof(string), typeof(Metric), new PropertyMetadata(string.Empty));

    public static readonly DependencyProperty ValueProperty = DependencyProperty.Register(
        nameof(Value), typeof(string), typeof(Metric), new PropertyMetadata("--"));

    public static readonly DependencyProperty UnitProperty = DependencyProperty.Register(
        nameof(Unit), typeof(string), typeof(Metric), new PropertyMetadata(string.Empty));

    public static readonly DependencyProperty ValueBrushProperty = DependencyProperty.Register(
        nameof(ValueBrush), typeof(Brush), typeof(Metric),
        new PropertyMetadata(Palette.Value));

    public static readonly DependencyProperty ValueSizeProperty = DependencyProperty.Register(
        nameof(ValueSize), typeof(double), typeof(Metric), new PropertyMetadata(18d));

    public static readonly DependencyProperty EmphasisProperty = DependencyProperty.Register(
        nameof(Emphasis), typeof(bool), typeof(Metric), new PropertyMetadata(false));

    /// <summary>关键数据：加粗并放大到 26px，用于订单号、深度值等需要一眼看到的指标。</summary>
    public bool Emphasis
    {
        get => (bool)GetValue(EmphasisProperty);
        set => SetValue(EmphasisProperty, value);
    }

    public string Label
    {
        get => (string)GetValue(LabelProperty);
        set => SetValue(LabelProperty, value);
    }

    public string Value
    {
        get => (string)GetValue(ValueProperty);
        set => SetValue(ValueProperty, value);
    }

    public string Unit
    {
        get => (string)GetValue(UnitProperty);
        set => SetValue(UnitProperty, value);
    }

    public Brush? ValueBrush
    {
        get => (Brush?)GetValue(ValueBrushProperty);
        set => SetValue(ValueBrushProperty, value);
    }

    public double ValueSize
    {
        get => (double)GetValue(ValueSizeProperty);
        set => SetValue(ValueSizeProperty, value);
    }
}

/// <summary>状态碎片：小圆灯 + 文字，用于面板标题右侧的模式/忙碌/故障。</summary>
public class StatusChip : Control
{
    static StatusChip()
    {
        DefaultStyleKeyProperty.OverrideMetadata(typeof(StatusChip),
            new FrameworkPropertyMetadata(typeof(StatusChip)));
    }

    public static readonly DependencyProperty TextProperty = DependencyProperty.Register(
        nameof(Text), typeof(string), typeof(StatusChip), new PropertyMetadata(string.Empty));

    public static readonly DependencyProperty ColorProperty = DependencyProperty.Register(
        nameof(Color), typeof(Brush), typeof(StatusChip), new PropertyMetadata(Palette.TextLabel));

    public string Text
    {
        get => (string)GetValue(TextProperty);
        set => SetValue(TextProperty, value);
    }

    public Brush? Color
    {
        get => (Brush?)GetValue(ColorProperty);
        set => SetValue(ColorProperty, value);
    }

    public static readonly DependencyProperty PulseProperty = DependencyProperty.Register(
        nameof(Pulse), typeof(bool), typeof(StatusChip), new PropertyMetadata(false));

    /// <summary>故障态让圆灯轻微呼吸，提示需要关注。</summary>
    public bool Pulse
    {
        get => (bool)GetValue(PulseProperty);
        set => SetValue(PulseProperty, value);
    }
}
