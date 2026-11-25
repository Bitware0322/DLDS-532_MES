using System.Globalization;
using System.Windows;
using System.Windows.Media;
using System.Windows.Threading;
using DLDS532.App.ViewModels;
using DLDS532.Services;

namespace DLDS532.App.Controls;

/// <summary>
/// 实时趋势图：自绘网格 + 多折线，时间轴固定窗口右移。
/// 只接收同一量纲的曲线（由外部按组筛选），因此纵坐标始终有明确单位。
/// </summary>
public class TrendChart : FrameworkElement
{
    private static readonly Brush PlotBg = Frozen("#FF0E1A22");
    private static readonly Brush GridBrush = Frozen("#FF1B2B36");
    private static readonly Brush AxisBrush = Frozen("#FF2A3E4C");
    private static readonly Brush TextBrush = Frozen("#FF6B7F8C");
    private static readonly Brush NowLineBrush = Frozen("#4D36A9E1");

    private readonly DispatcherTimer _timer;
    private readonly Typeface _face = new("Segoe UI");

    public TrendChart()
    {
        SnapsToDevicePixels = true;
        UseLayoutRounding = true;
        _timer = new DispatcherTimer(DispatcherPriority.Render)
        {
            Interval = TimeSpan.FromMilliseconds(300),
        };
        _timer.Tick += (_, _) =>
        {
            if (IsVisible) InvalidateVisual();
        };
    }

    public static readonly DependencyProperty BufferProperty = DependencyProperty.Register(
        nameof(Buffer), typeof(TrendBuffer), typeof(TrendChart),
        new FrameworkPropertyMetadata(null, FrameworkPropertyMetadataOptions.AffectsRender));

    public static readonly DependencyProperty SeriesProperty = DependencyProperty.Register(
        nameof(Series), typeof(IEnumerable<TrendSeriesVm>), typeof(TrendChart),
        new FrameworkPropertyMetadata(null, FrameworkPropertyMetadataOptions.AffectsRender));

    public static readonly DependencyProperty WindowMinutesProperty = DependencyProperty.Register(
        nameof(WindowMinutes), typeof(double), typeof(TrendChart),
        new FrameworkPropertyMetadata(5d, FrameworkPropertyMetadataOptions.AffectsRender));

    public static readonly DependencyProperty UnitLabelProperty = DependencyProperty.Register(
        nameof(UnitLabel), typeof(string), typeof(TrendChart),
        new FrameworkPropertyMetadata(string.Empty, FrameworkPropertyMetadataOptions.AffectsRender));

    public TrendBuffer? Buffer
    {
        get => (TrendBuffer?)GetValue(BufferProperty);
        set => SetValue(BufferProperty, value);
    }

    public IEnumerable<TrendSeriesVm>? Series
    {
        get => (IEnumerable<TrendSeriesVm>?)GetValue(SeriesProperty);
        set => SetValue(SeriesProperty, value);
    }

    public double WindowMinutes
    {
        get => (double)GetValue(WindowMinutesProperty);
        set => SetValue(WindowMinutesProperty, value);
    }

    public string UnitLabel
    {
        get => (string)GetValue(UnitLabelProperty);
        set => SetValue(UnitLabelProperty, value);
    }

    protected override void OnRender(DrawingContext dc)
    {
        base.OnRender(dc);

        double w = ActualWidth, h = ActualHeight;
        if (w < 80 || h < 60) return;

        const double gutterLeft = 52, gutterRight = 16, padTop = 26, padBottom = 26;
        var plot = new Rect(gutterLeft, padTop, Math.Max(10, w - gutterLeft - gutterRight),
            Math.Max(10, h - padTop - padBottom));

        dc.DrawRoundedRectangle(PlotBg, null, plot, 6, 6);

        var buffer = Buffer;
        var selected = Series?.Where(s => s.IsSelected).ToList() ?? new List<TrendSeriesVm>();
        var now = DateTime.Now;
        var window = TimeSpan.FromMinutes(Math.Max(1, WindowMinutes));
        var from = now - window;

        var samples = new List<(TrendSeriesVm Series, DateTime[] Ts, float[] Vs)>();
        if (buffer is not null)
        {
            foreach (var s in selected)
            {
                var (ts, vs) = buffer.Window(s.Key, from);
                if (ts.Length > 0) samples.Add((s, ts, vs));
            }
        }

        double min = double.MaxValue, max = double.MinValue;
        foreach (var (_, _, vs) in samples)
        {
            foreach (var v in vs)
            {
                if (v < min) min = v;
                if (v > max) max = v;
            }
        }
        if (min > max)
        {
            min = 0;
            max = 10;
        }
        // 取「整齐」的刻度区间，避免出现 16.23 / 14.16 这类读不出来的坐标值
        var (niceMin, niceMax) = NiceRange(min, max, 4);
        min = niceMin;
        max = niceMax;

        var gridPen = new Pen(GridBrush, 1);
        gridPen.Freeze();
        var axisPen = new Pen(AxisBrush, 1);
        axisPen.Freeze();

        // 横向网格：只留 4 条，亮度很低，不抢曲线
        for (int i = 0; i <= 4; i++)
        {
            double y = plot.Top + plot.Height * i / 4.0;
            dc.DrawLine(i == 4 ? axisPen : gridPen, new Point(plot.Left, y), new Point(plot.Right, y));

            double value = max - (max - min) * i / 4.0;
            DrawText(dc, FormatTick(value, max - min), plot.Left - 10, y - 8, 10.5, TextBrush, TextAlignment.Right);
        }

        // 纵向网格：4 条即可，避免密集
        for (int i = 0; i <= 4; i++)
        {
            double x = plot.Left + plot.Width * i / 4.0;
            dc.DrawLine(i is 0 or 4 ? axisPen : gridPen, new Point(x, plot.Top), new Point(x, plot.Bottom));

            var t = from + TimeSpan.FromTicks((long)(window.Ticks * i / 4.0));
            string label = i == 4 ? "现在" : t.ToString("HH:mm");
            DrawText(dc, label, x, plot.Bottom + 7, 10.5, TextBrush, TextAlignment.Center);
        }

        if (!string.IsNullOrEmpty(UnitLabel))
        {
            DrawText(dc, UnitLabel, plot.Left, plot.Top - 18, 10.5, TextBrush, TextAlignment.Left);
        }

        if (samples.Count == 0)
        {
            string hint = buffer is null ? "趋势缓冲未初始化"
                : selected.Count == 0 ? "请选择要查看的曲线"
                : "等待数据…";
            DrawText(dc, hint, plot.Left + plot.Width / 2, plot.Top + plot.Height / 2 - 8, 12,
                TextBrush, TextAlignment.Center);
            return;
        }

        dc.PushClip(new RectangleGeometry(plot));
        foreach (var (series, ts, vs) in samples)
        {
            var geo = new StreamGeometry();
            using (var ctx = geo.Open())
            {
                bool started = false;
                for (int i = 0; i < ts.Length; i++)
                {
                    double x = plot.Left + (ts[i] - from).TotalSeconds / window.TotalSeconds * plot.Width;
                    if (x < plot.Left - 2) continue;
                    double y = plot.Bottom - (vs[i] - min) / (max - min) * plot.Height;
                    var pt = new Point(Math.Min(x, plot.Right), y);
                    if (!started)
                    {
                        ctx.BeginFigure(pt, false, false);
                        started = true;
                    }
                    else
                    {
                        ctx.LineTo(pt, true, false);
                    }
                }
            }
            geo.Freeze();

            var pen = new Pen(series.Stroke, 1.8)
            {
                LineJoin = PenLineJoin.Round,
                StartLineCap = PenLineCap.Round,
                EndLineCap = PenLineCap.Round,
            };
            pen.Freeze();
            dc.DrawGeometry(null, pen, geo);

            if (ts.Length > 0)
            {
                double lastX = plot.Left + (ts[^1] - from).TotalSeconds / window.TotalSeconds * plot.Width;
                double lastY = plot.Bottom - (vs[^1] - min) / (max - min) * plot.Height;
                if (lastX >= plot.Left - 2)
                {
                    var dot = new Point(Math.Min(lastX, plot.Right), lastY);
                    dc.DrawEllipse(series.Stroke, null, dot, 3.2, 3.2);
                    dc.DrawEllipse(PlotBg, null, dot, 1.4, 1.4);
                }
            }
        }
        dc.Pop();

        var nowPen = new Pen(NowLineBrush, 1) { DashStyle = DashStyles.Dot };
        dc.DrawLine(nowPen, new Point(plot.Right - 0.5, plot.Top), new Point(plot.Right - 0.5, plot.Bottom));
    }

    /// <summary>把数据范围扩展到 1/2/2.5/5 × 10^n 的整数步长区间。</summary>
    private static (double Min, double Max) NiceRange(double min, double max, int ticks)
    {
        if (double.IsNaN(min) || double.IsNaN(max) || double.IsInfinity(min) || double.IsInfinity(max))
            return (0, 10);

        if (Math.Abs(max - min) < 1e-6)
        {
            double center = min;
            double pad = Math.Abs(center) > 1 ? Math.Abs(center) * 0.1 : 1;
            min = center - pad;
            max = center + pad;
        }

        double rawStep = (max - min) / ticks;
        double magnitude = Math.Pow(10, Math.Floor(Math.Log10(rawStep)));
        double normalized = rawStep / magnitude;
        double step = normalized <= 1 ? 1
            : normalized <= 2 ? 2
            : normalized <= 2.5 ? 2.5
            : normalized <= 5 ? 5
            : 10;
        step *= magnitude;

        double low = Math.Floor(min / step) * step;
        double high = Math.Ceiling(max / step) * step;
        if (Math.Abs(high - low) < step) high = low + step * ticks;
        return (low, high);
    }

    private static string FormatTick(double value, double span)
    {
        if (span >= 200) return value.ToString("F0", CultureInfo.InvariantCulture);
        if (span >= 20) return value.ToString("F1", CultureInfo.InvariantCulture);
        return value.ToString("F2", CultureInfo.InvariantCulture);
    }

    private void DrawText(DrawingContext dc, string text, double x, double y, double size, Brush brush,
        TextAlignment align)
    {
        double dpi = VisualTreeHelper.GetDpi(this).PixelsPerDip;
        var ft = new FormattedText(text, CultureInfo.InvariantCulture, FlowDirection.LeftToRight,
            _face, size, brush, dpi);

        double drawX = align switch
        {
            TextAlignment.Center => x - ft.Width / 2,
            TextAlignment.Right => x - ft.Width,
            _ => x,
        };

        dc.DrawText(ft, new Point(drawX, y));
    }

    protected override void OnVisualParentChanged(DependencyObject oldParent)
    {
        base.OnVisualParentChanged(oldParent);
        if (Parent is null) _timer.Stop();
        else _timer.Start();
    }

    private static Brush Frozen(string hex)
    {
        var brush = new SolidColorBrush((Color)ColorConverter.ConvertFromString(hex)!);
        brush.Freeze();
        return brush;
    }
}
