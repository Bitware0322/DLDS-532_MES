namespace DLDS532.DataModels;

/// <summary>可记录的实时趋势信号定义。</summary>
/// <param name="Key">语义键（与 DB120 映射表的 id 一致）。</param>
/// <param name="Label">界面显示名。</param>
/// <param name="Unit">单位（同时作为量纲分组依据）。</param>
/// <param name="ColorHex">曲线颜色。</param>
/// <param name="Decimals">显示小数位。</param>
public sealed record TrendSignal(string Key, string Label, string Unit, string ColorHex, int Decimals);

/// <summary>同量纲信号组：不同量纲不共用一个纵坐标，按组切换查看。</summary>
public sealed record TrendUnitGroup(string Key, string Label, string Unit, IReadOnlyList<TrendSignal> Signals);

public static class TrendSignals
{
    public const string S1Depth = "s1.depth";
    public const string S1TurnAngle = "s1.turntableAngle";
    public const string S2Inject8 = "s2.inject8";
    public const string S2Inject10 = "s2.inject10";
    public const string S3Weight = "s3.weight";
    public const string S3AxisX = "s3.axisX";
    public const string S3AxisY = "s3.axisY";

    public static readonly IReadOnlyList<TrendSignal> All = new[]
    {
        new TrendSignal(S1Depth, "一站深度检测", "mm", "#42C6C5", 3),
        new TrendSignal(S3AxisX, "三站 X 轴", "mm", "#E3C558", 2),
        new TrendSignal(S3AxisY, "三站 Y 轴", "mm", "#EF6262", 2),
        new TrendSignal(S1TurnAngle, "一站转盘角度", "°", "#36A9E1", 1),
        new TrendSignal(S2Inject8, "二站 8mm 灌注", "颗", "#A78BFA", 0),
        new TrendSignal(S2Inject10, "二站 10mm 灌注", "颗", "#F2B45B", 0),
        new TrendSignal(S3Weight, "三站称重", "g", "#36C98F", 0),
    };

    /// <summary>按量纲 + 工艺归属分组：同组共用一个纵坐标，避免不同量纲强行同轴。</summary>
    public static readonly IReadOnlyList<TrendUnitGroup> Groups = new[]
    {
        new TrendUnitGroup("depth", "一站深度", "mm", new[] { S1Depth }.Select(Get).ToList()),
        new TrendUnitGroup("axis", "三站坐标", "mm", new[] { S3AxisX, S3AxisY }.Select(Get).ToList()),
        new TrendUnitGroup("deg", "转盘角度", "°", new[] { S1TurnAngle }.Select(Get).ToList()),
        new TrendUnitGroup("count", "灌注数量", "颗", new[] { S2Inject8, S2Inject10 }.Select(Get).ToList()),
        new TrendUnitGroup("gram", "三站称重", "g", new[] { S3Weight }.Select(Get).ToList()),
    };

    public static TrendSignal Get(string key) =>
        All.FirstOrDefault(s => s.Key == key) ?? new TrendSignal(key, key, "", "#42C6C5", 2);
}
