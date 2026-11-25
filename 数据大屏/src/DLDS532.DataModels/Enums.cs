namespace DLDS532.DataModels;

/// <summary>与 PLC 的连接状态（通信层状态，不代表 CPU 是否 RUN）。</summary>
public enum ConnectionState
{
    Disconnected,
    Connecting,
    Connected,
    Faulted,
}

/// <summary>数据新鲜度：界面必须能区分「实时」与「旧数据」。</summary>
public enum DataFreshness
{
    /// <summary>最近一个刷新周期内取到有效数据。</summary>
    Live,

    /// <summary>通信仍在线，但数据超过 2 个周期未更新（或 CPU 处于 STOP）。</summary>
    Stale,

    /// <summary>连接断开 / 读取失败，界面显示 --。</summary>
    Offline,
}

/// <summary>CPU 运行状态，用于区分「通信正常但数据冻结」。</summary>
public enum PlcCpuState
{
    Unknown,
    Run,
    Stop,
}

/// <summary>监控项的视觉严重级别。</summary>
public enum MetricSeverity
{
    /// <summary>正常，青色数值。</summary>
    Normal,

    /// <summary>空闲/未启用，灰蓝。</summary>
    Idle,

    /// <summary>数据过期或超出正常范围，琥珀色。</summary>
    Warning,

    /// <summary>故障，红色。</summary>
    Fault,

    /// <summary>离线，灰色。</summary>
    Offline,
}

/// <summary>
/// PLC 中的运行模式原始值，按**现场实测定义**：
/// <c>0 = 未知 / 1 = 手动模式 / 2 = 自动待机模式 / 3 = 自动运行模式</c>。
/// <para>
/// 注意：DB120 SCL 导出里的行注释写的是「0 手动 / 1 自动待机 / 2 自动运行」，与现场不一致，
/// 以现场定义为准（同一段注释在导出文件里三站都一样，属导出遗留文字）。
/// </para>
/// </summary>
public static class RunModeText
{
    public const int Unknown = 0;
    public const int Manual = 1;
    public const int AutoStandby = 2;
    public const int AutoRun = 3;

    public static string Describe(int runMode) => runMode switch
    {
        AutoRun => "自动运行",
        AutoStandby => "自动待机",
        Manual => "手动",
        Unknown => "未知",
        _ => $"未知({runMode})",
    };

    /// <summary>只有「自动运行」（=3）才计入单元工作时间；自动待机不算。</summary>
    public static bool IsRunning(int runMode) => runMode == AutoRun;
}

/// <summary>忙碌状态原始值：0 空闲 / 1 忙碌。</summary>
public static class BusyText
{
    public static string Describe(int busy) => busy switch
    {
        0 => "空闲",
        1 => "忙碌",
        _ => $"未定义({busy})",
    };
}
