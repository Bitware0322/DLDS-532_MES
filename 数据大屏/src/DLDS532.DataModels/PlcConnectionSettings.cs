namespace DLDS532.DataModels;

/// <summary>数据源模式。默认真实 PLC；连接失败**不会**自动切到模拟。</summary>
public enum DataSourceMode
{
    /// <summary>真实 PLC（192.168.40.115 的 DB120）。</summary>
    RealPlc = 0,

    /// <summary>模拟帧源，仅供无 PLC 环境下演示。</summary>
    Simulation = 1,
}

/// <summary>PLC 连接与采集参数（可在「系统设置」中修改）。</summary>
public sealed record PlcConnectionSettings
{
    /// <summary>数据源：真实 PLC 或模拟。</summary>
    public DataSourceMode DataSource { get; init; } = DataSourceMode.RealPlc;

    public string IpAddress { get; init; } = "192.168.40.115";
    public int Rack { get; init; } = 0;
    public int Slot { get; init; } = 1;
    public int Port { get; init; } = 102;
    public int DbNumber { get; init; } = 120;

    /// <summary>刷新周期，默认 500ms，可调整。</summary>
    public int PollIntervalMs { get; init; } = 500;

    /// <summary>连接 / 读取超时。</summary>
    public int TimeoutMs { get; init; } = 2000;

    public bool AutoReconnect { get; init; } = true;

    /// <summary>自动重连间隔。</summary>
    public int ReconnectIntervalMs { get; init; } = 3000;

    /// <summary>超过该时间无有效数据即标记为「已过期」。</summary>
    public int StaleAfterMs => Math.Max(PollIntervalMs * 2, 1200);

    /// <summary>三站心跳全部无变化超过该时间，判定为「数据冻结」（CPU STOP 或程序未刷新）。</summary>
    public int FrozenAfterMs { get; init; } = 3000;
}
