using DLDS532.DataModels;

namespace DLDS532.Communication;

/// <summary>
/// 原始帧来源抽象：无论模拟器还是真实 S7 连接，都只向上提供「一帧 DB120 字节」。
/// 解码路径因此完全一致，阶段二用模拟帧即可验证整条链路。
/// 注意：接口只暴露读取，本项目不存在写 PLC 的代码路径。
/// </summary>
public interface IPlcFrameSource : IDisposable
{
    string DisplayName { get; }

    /// <summary>true 表示模拟数据源；界面必须明确标注，不允许把模拟数据当实时数据。</summary>
    bool IsSimulation { get; }

    ConnectionState State { get; }

    PlcCpuState Cpu { get; }

    /// <summary>最近一次读取耗时。</summary>
    TimeSpan LastLatency { get; }

    /// <summary>建立连接（同步，内部自带超时）。</summary>
    bool Connect(PlcConnectionSettings settings, out string? error);

    void Disconnect();

    /// <summary>读取一帧；失败抛异常，由上层统一处理。</summary>
    byte[] Read(int dbNumber, int start, int length);
}
