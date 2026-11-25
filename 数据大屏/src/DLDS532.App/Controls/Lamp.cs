using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Animation;

namespace DLDS532.App.Controls;

/// <summary>状态指示灯：外圈淡光晕 + 内圈实心，颜色由绑定决定（绿正常 / 红故障 / 灰离线 / 黄过期）。</summary>
public class Lamp : FrameworkElement
{
    public static readonly DependencyProperty ColorProperty = DependencyProperty.Register(
        nameof(Color), typeof(Brush), typeof(Lamp),
        new FrameworkPropertyMetadata(Brushes.Gray, FrameworkPropertyMetadataOptions.AffectsRender));

    public static readonly DependencyProperty DiameterProperty = DependencyProperty.Register(
        nameof(Diameter), typeof(double), typeof(Lamp),
        new FrameworkPropertyMetadata(10d, FrameworkPropertyMetadataOptions.AffectsMeasure | FrameworkPropertyMetadataOptions.AffectsRender));

    public static readonly DependencyProperty PulseProperty = DependencyProperty.Register(
        nameof(Pulse), typeof(bool), typeof(Lamp),
        new PropertyMetadata(false, OnPulseChanged));

    private static readonly DependencyProperty HaloOpacityProperty = DependencyProperty.Register(
        nameof(HaloOpacity), typeof(double), typeof(Lamp),
        new FrameworkPropertyMetadata(0.18, FrameworkPropertyMetadataOptions.AffectsRender));

    private double HaloOpacity
    {
        get => (double)GetValue(HaloOpacityProperty);
        set => SetValue(HaloOpacityProperty, value);
    }

    private static void OnPulseChanged(DependencyObject d, DependencyPropertyChangedEventArgs e)
    {
        var lamp = (Lamp)d;
        if ((bool)e.NewValue)
        {
            var breathe = new DoubleAnimation(0.42, 0.10, TimeSpan.FromSeconds(1.5))
            {
                AutoReverse = true,
                RepeatBehavior = RepeatBehavior.Forever,
                EasingFunction = new SineEase { EasingMode = EasingMode.EaseInOut },
            };
            lamp.BeginAnimation(HaloOpacityProperty, breathe);
        }
        else
        {
            lamp.BeginAnimation(HaloOpacityProperty, null);
            lamp.HaloOpacity = 0.18;
        }
    }

    /// <summary>故障/离线时呼吸闪烁；正常状态保持常亮，避免频繁闪烁干扰。</summary>
    public bool Pulse
    {
        get => (bool)GetValue(PulseProperty);
        set => SetValue(PulseProperty, value);
    }

    public Brush Color
    {
        get => (Brush)GetValue(ColorProperty);
        set => SetValue(ColorProperty, value);
    }

    public double Diameter
    {
        get => (double)GetValue(DiameterProperty);
        set => SetValue(DiameterProperty, value);
    }

    protected override Size MeasureOverride(Size availableSize) =>
        new(double.IsInfinity(availableSize.Width) ? Diameter : Math.Min(availableSize.Width, Diameter),
            double.IsInfinity(availableSize.Height) ? Diameter : Math.Min(availableSize.Height, Diameter));

    protected override void OnRender(DrawingContext dc)
    {
        double d = Diameter;
        var center = new Point(d / 2, d / 2);

        Brush halo = Color is SolidColorBrush solid
            ? new SolidColorBrush(solid.Color) { Opacity = HaloOpacity }
            : Brushes.Transparent;

        dc.DrawEllipse(halo, null, center, d / 2, d / 2);
        dc.DrawEllipse(Color, null, center, d * 0.29, d * 0.29);
    }
}
