using System.Windows.Media;

namespace DLDS532.App;

/// <summary>
/// 第二轮视觉体系：现代工业 SCADA 配色。
/// 原则：普通文字灰白，蓝色只用于信息/通信/位置，绿色运行、橙色等待、红色故障、青色测量、紫色趋势。
/// </summary>
public static class Palette
{
    // 背景层次
    public static readonly Brush Bg = Freeze("#FF101820");
    public static readonly Brush BgDeep = Freeze("#FF0B1117");
    public static readonly Brush PanelBg = Freeze("#FF182632");
    public static readonly Brush PanelBgAlt = Freeze("#FF203442");
    public static readonly Brush HeaderBg = Freeze("#FF1E2E3A");

    // 线条
    public static readonly Brush Border = Freeze("#FF344956");
    public static readonly Brush BorderSoft = Freeze("#FF2A3E4C");

    // 文字
    public static readonly Brush TextValue = Freeze("#FFE6EDF3");
    public static readonly Brush TextLabel = Freeze("#FF9BAEBB");
    public static readonly Brush TextMuted = Freeze("#FF6B7F8C");

    // 功能色
    public static readonly Brush Accent = Freeze("#FF36A9E1");     // 品牌蓝：信息 / 通信 / 位置
    public static readonly Brush AccentDim = Freeze("#FF2A7EA8");
    public static readonly Brush Green = Freeze("#FF36C98F");      // 运行正常 / 完成 / 有料
    public static readonly Brush Amber = Freeze("#FFF2B45B");      // 等待 / 处理中 / 注意
    public static readonly Brush Red = Freeze("#FFEF6262");        // 故障 / 报警 / 不合格
    public static readonly Brush Purple = Freeze("#FFA78BFA");     // 趋势 / 工艺
    public static readonly Brush Pink = Freeze("#FFE58FB8");
    public static readonly Brush Cyan = Freeze("#FF42C6C5");       // 实时测量值
    public static readonly Brush Yellow = Freeze("#FFE3C558");     // X 轴等辅助量
    public static readonly Brush Gray = Freeze("#FF55676F");       // 离线 / 空

    // 兼容旧引用
    public static readonly Brush Value = TextValue;
    public static readonly Brush Label = TextLabel;
    public static readonly Brush Muted = TextMuted;

    public static Brush ForSeverity(DataModels.MetricSeverity severity) => severity switch
    {
        DataModels.MetricSeverity.Normal => Cyan,
        DataModels.MetricSeverity.Idle => TextMuted,
        DataModels.MetricSeverity.Warning => Amber,
        DataModels.MetricSeverity.Fault => Red,
        DataModels.MetricSeverity.Offline => Gray,
        _ => TextValue,
    };

    /// <summary>由十六进制颜色生成冻结画刷（供趋势图例等动态颜色使用）。</summary>
    public static Brush FromHex(string hex)
    {
        var brush = new SolidColorBrush((Color)ColorConverter.ConvertFromString(hex)!);
        brush.Freeze();
        return brush;
    }

    private static Brush Freeze(string hex) => FromHex(hex);
}
