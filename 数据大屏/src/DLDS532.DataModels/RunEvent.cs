namespace DLDS532.DataModels;

/// <summary>运行事件级别，决定界面配色。</summary>
public enum RunEventLevel
{
    /// <summary>正常：完成、恢复（绿色）。</summary>
    Normal,

    /// <summary>提示：开始加工、接收订单（蓝色）。</summary>
    Info,

    /// <summary>警告：离线、STOP（橙色）。</summary>
    Warning,

    /// <summary>故障：故障码、通信中断（红色）。</summary>
    Fault,
}

/// <summary>
/// 一条运行事件。事件只能由**相邻两帧之间真实发生的状态跃变**产生，
/// 不允许由随机数或模拟流程凭空生成。
/// </summary>
/// <param name="Time">检测到跃变的时间（本机时间）。</param>
/// <param name="Unit">所属单元：一站/二站/三站/通信/系统。</param>
/// <param name="Message">事件描述。</param>
/// <param name="Level">事件级别。</param>
public sealed record RunEventRecord(DateTime Time, string Unit, string Message, RunEventLevel Level)
{
    public string TimeText => Time.ToString("HH:mm:ss");
}
