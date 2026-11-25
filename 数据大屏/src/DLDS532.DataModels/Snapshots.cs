namespace DLDS532.DataModels;

/// <summary>一站（自动供料单元）快照，字段与 DB120 一站数据一一对应。</summary>
public sealed record Station1Snapshot
{
    public const string StationKey = "station1";
    public static string DisplayName => "自动供料单元";

    public int Online { get; init; }
    public int RunMode { get; init; }
    public int Busy { get; init; }
    public int Fault { get; init; }
    public int OrderId { get; init; }
    public float Step { get; init; }
    public int Heartbeat { get; init; }
    public bool Done { get; init; }
    public bool Received { get; init; }
    public int ScanCode { get; init; }
    public float TurntableAngle { get; init; }
    public float RobotPosition { get; init; }
    public float Depth { get; init; }
    public int BoxUsed { get; init; }
    public int MaterialA { get; init; }
    public int MaterialB { get; init; }
}

/// <summary>二站（智能分拣单元）快照。</summary>
public sealed record Station2Snapshot
{
    public const string StationKey = "station2";
    public static string DisplayName => "智能分拣单元";

    public int Online { get; init; }
    public int RunMode { get; init; }
    public int Busy { get; init; }
    public int Fault { get; init; }
    public int OrderId { get; init; }
    public float Step { get; init; }
    public int Heartbeat { get; init; }
    public bool Done { get; init; }
    public bool Received { get; init; }
    public int ScanCode { get; init; }
    public int Inject8mm { get; init; }
    public int Inject10mm { get; init; }
    public bool Hopper8mmPresent { get; init; }
    public bool Hopper10mmPresent { get; init; }
}

/// <summary>三站（智能仓储单元）快照。</summary>
public sealed record Station3Snapshot
{
    public const string StationKey = "station3";
    public static string DisplayName => "智能仓储单元";

    /// <summary>9 个仓位名称，下标 = DB120 的数组下标：0 = 仓位 A …… 8 = 仓位 I（122.0 ~ 123.0）。</summary>
    public static readonly string[] SlotNames = { "A", "B", "C", "D", "E", "F", "G", "H", "I" };

    /// <summary>
    /// 界面 3×3 仓位灯的摆放顺序（从左到右、从上到下），元素值为 <see cref="SlotNames"/> 的下标。
    /// 现场仓位物理排布是「A 在右下角」，所以按 A..I 逆序摆放：
    /// <code>
    ///   I H G
    ///   F E D
    ///   C B A
    /// </code>
    /// 只影响显示位置，不影响任何地址与解码。
    /// </summary>
    public static readonly int[] SlotDisplayOrder = { 8, 7, 6, 5, 4, 3, 2, 1, 0 };

    public int Online { get; init; }
    public int RunMode { get; init; }
    public int Busy { get; init; }
    public int Fault { get; init; }
    public int OrderId { get; init; }
    public float Step { get; init; }
    public int Heartbeat { get; init; }
    public bool Done { get; init; }
    public bool Received { get; init; }
    public int InboundScan { get; init; }
    public int StorageScan { get; init; }
    public int Weight { get; init; }
    public int QualityState { get; init; }
    public int QualifiedCount { get; init; }
    public int UnqualifiedCount { get; init; }
    public float AxisX { get; init; }
    public float AxisY { get; init; }

    /// <summary>仓位占用状态，长度固定 9。</summary>
    public IReadOnlyList<bool> Slots { get; init; } = new bool[9];

    public int OccupiedSlots => Slots.Count(s => s);
}

/// <summary>订单数据（DB120 订单区，MES 只读镜像）。</summary>
public sealed record OrderSnapshot
{
    public int Id { get; init; }
    public int AbMaterial { get; init; }
    public int Ball8mmQty { get; init; }
    public int Ball10mmQty { get; init; }
    public int Slot { get; init; }
    public bool Done { get; init; }
    public int StartSignal { get; init; }
    public int ResetSignal { get; init; }

    public string AbMaterialText => AbMaterial switch
    {
        1 => "A 料",
        2 => "B 料",
        3 => "不需要",
        _ => "—",
    };
}

/// <summary>一次完整读取的数据快照（不可变，跨线程传递）。</summary>
public sealed record PlcSnapshot
{
    /// <summary>本机取到该帧的时间。</summary>
    public DateTime Timestamp { get; init; }

    /// <summary>本帧字节数，正常应为 190。</summary>
    public int FrameBytes { get; init; }

    public PlcCpuState Cpu { get; init; } = PlcCpuState.Unknown;

    public Station1Snapshot S1 { get; init; } = new();
    public Station2Snapshot S2 { get; init; } = new();
    public Station3Snapshot S3 { get; init; } = new();
    public OrderSnapshot Order { get; init; } = new();

    /// <summary>四个区域的故障码汇总，用于报警与顶部状态灯。</summary>
    public bool HasAnyFault => S1.Fault != 0 || S2.Fault != 0 || S3.Fault != 0;

    public int BusyStationCount =>
        (S1.Busy == 1 ? 1 : 0) + (S2.Busy == 1 ? 1 : 0) + (S3.Busy == 1 ? 1 : 0);
}
