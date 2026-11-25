using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;

namespace DLDS532.App.Controls;

/// <summary>
/// 工业风面板容器：渐变底 + 1px 描边 + 四角装饰 + 标题条。标题右侧可放状态碎片。
/// </summary>
public class PanelCard : ContentControl
{
    static PanelCard()
    {
        DefaultStyleKeyProperty.OverrideMetadata(typeof(PanelCard),
            new FrameworkPropertyMetadata(typeof(PanelCard)));
    }

    public static readonly DependencyProperty TitleProperty = DependencyProperty.Register(
        nameof(Title), typeof(string), typeof(PanelCard), new PropertyMetadata(string.Empty));

    public static readonly DependencyProperty HeaderRightProperty = DependencyProperty.Register(
        nameof(HeaderRight), typeof(object), typeof(PanelCard), new PropertyMetadata(null));

    public static readonly DependencyProperty AccentBrushProperty = DependencyProperty.Register(
        nameof(AccentBrush), typeof(Brush), typeof(PanelCard),
        new PropertyMetadata(null));

    public static readonly DependencyProperty IsHighlightedProperty = DependencyProperty.Register(
        nameof(IsHighlighted), typeof(bool), typeof(PanelCard), new PropertyMetadata(false));

    /// <summary>被外部聚焦（例如从大屏点击单元卡片跳转到本模块）时高亮描边。</summary>
    public bool IsHighlighted
    {
        get => (bool)GetValue(IsHighlightedProperty);
        set => SetValue(IsHighlightedProperty, value);
    }

    public string Title
    {
        get => (string)GetValue(TitleProperty);
        set => SetValue(TitleProperty, value);
    }

    public object? HeaderRight
    {
        get => GetValue(HeaderRightProperty);
        set => SetValue(HeaderRightProperty, value);
    }

    public Brush? AccentBrush
    {
        get => (Brush?)GetValue(AccentBrushProperty);
        set => SetValue(AccentBrushProperty, value);
    }
}
