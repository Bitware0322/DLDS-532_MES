using System.Buffers.Binary;
using System.Text;
using DLDS532.DataModels;

namespace DLDS532.PlcData;

/// <summary>单个字段的解码结果，供「单元详细监控」等页面按 DB120 原始结构展示。</summary>
public sealed record FieldValue(FieldDef Definition, string Text, double Numeric);

public sealed class DecodedFrame
{
    public required PlcSnapshot Snapshot { get; init; }
    public required IReadOnlyList<FieldValue> Values { get; init; }
}

/// <summary>
/// DB120 解码器：把 190 字节原始帧按映射表解析为强类型快照。
/// 全部偏移来自映射表；此处只负责字节序、对齐与类型转换。
/// </summary>
public sealed class Db120Decoder
{
    private readonly Db120Mapping _mapping;
    private readonly Dictionary<string, FieldDef> _byId;
    private readonly List<FieldDef> _fields;

    public Db120Decoder(Db120Mapping mapping)
    {
        _mapping = mapping;
        _fields = mapping.Document.Fields;
        _byId = _fields.Where(f => f.Id.Length > 0).ToDictionary(f => f.Id);
    }

    public int ExpectedLength => _mapping.Document.TotalBytes;

    public DecodedFrame Decode(ReadOnlySpan<byte> frame, DateTime timestamp, PlcCpuState cpu)
    {
        if (frame.Length < ExpectedLength)
            throw new InvalidDataException(
                $"DB120 长度不足：需要 {ExpectedLength} 字节，实际 {frame.Length} 字节。");

        var s1 = new Station1Snapshot
        {
            Online = Int32Of(frame, "s1.online"),
            RunMode = Int32Of(frame, "s1.runMode"),
            Busy = Int32Of(frame, "s1.busy"),
            Fault = Int32Of(frame, "s1.fault"),
            OrderId = Int32Of(frame, "s1.orderId"),
            Step = RealOf(frame, "s1.step"),
            Heartbeat = Int32Of(frame, "s1.heartbeat"),
            Done = BoolOf(frame, "s1.done"),
            Received = BoolOf(frame, "s1.received"),
            ScanCode = Int32Of(frame, "s1.scanCode"),
            TurntableAngle = RealOf(frame, "s1.turntableAngle"),
            RobotPosition = RealOf(frame, "s1.robotPos"),
            Depth = RealOf(frame, "s1.depth"),
            BoxUsed = Int32Of(frame, "s1.boxUsed"),
            MaterialA = Int32Of(frame, "s1.matA"),
            MaterialB = Int32Of(frame, "s1.matB"),
        };

        var s2 = new Station2Snapshot
        {
            Online = Int32Of(frame, "s2.online"),
            RunMode = Int32Of(frame, "s2.runMode"),
            Busy = Int32Of(frame, "s2.busy"),
            Fault = Int32Of(frame, "s2.fault"),
            OrderId = Int32Of(frame, "s2.orderId"),
            Step = RealOf(frame, "s2.step"),
            Heartbeat = Int32Of(frame, "s2.heartbeat"),
            Done = BoolOf(frame, "s2.done"),
            Received = BoolOf(frame, "s2.received"),
            ScanCode = Int32Of(frame, "s2.scanCode"),
            Inject8mm = Int32Of(frame, "s2.inject8"),
            Inject10mm = Int32Of(frame, "s2.inject10"),
            Hopper8mmPresent = BoolOf(frame, "s2.hopper8"),
            Hopper10mmPresent = BoolOf(frame, "s2.hopper10"),
        };

        // 仓位状态按数据顺序返回：数组[0] = 仓位 A …… 数组[8] = 仓位 I。
        // 界面 3×3 的摆放位置（A 在右下角）由 Station3Snapshot.SlotDisplayOrder 决定，不在这里翻转。
        var slots = BoolsOf(frame, "s3.slots", Station3Snapshot.SlotNames.Length);

        var s3 = new Station3Snapshot
        {
            Online = Int32Of(frame, "s3.online"),
            RunMode = Int32Of(frame, "s3.runMode"),
            Busy = Int32Of(frame, "s3.busy"),
            Fault = Int32Of(frame, "s3.fault"),
            OrderId = Int32Of(frame, "s3.orderId"),
            Step = RealOf(frame, "s3.step"),
            Heartbeat = Int32Of(frame, "s3.heartbeat"),
            Done = BoolOf(frame, "s3.done"),
            Received = BoolOf(frame, "s3.received"),
            InboundScan = Int32Of(frame, "s3.inboundScan"),
            StorageScan = Int32Of(frame, "s3.storageScan"),
            Weight = Int32Of(frame, "s3.weight"),
            QualityState = Int32Of(frame, "s3.qualityState"),
            QualifiedCount = Int32Of(frame, "s3.qualifiedCount"),
            UnqualifiedCount = Int32Of(frame, "s3.unqualifiedCount"),
            AxisX = RealOf(frame, "s3.axisX"),
            AxisY = RealOf(frame, "s3.axisY"),
            Slots = slots,
        };

        var order = new OrderSnapshot
        {
            Id = Int32Of(frame, "order.id"),
            AbMaterial = Int32Of(frame, "order.abMaterial"),
            Ball8mmQty = Int32Of(frame, "order.ball8mmQty"),
            Ball10mmQty = Int32Of(frame, "order.ball10mmQty"),
            Slot = Int32Of(frame, "order.slot"),
            Done = BoolOf(frame, "order.done"),
            StartSignal = Int32Of(frame, "order.startSignal"),
            ResetSignal = Int32Of(frame, "order.resetSignal"),
        };

        var snapshot = new PlcSnapshot
        {
            Timestamp = timestamp,
            FrameBytes = frame.Length,
            Cpu = cpu,
            S1 = s1,
            S2 = s2,
            S3 = s3,
            Order = order,
        };

        var values = new List<FieldValue>(_fields.Count);
        foreach (var f in _fields)
        {
            if (f.Id.Length == 0) continue;
            var (text, numeric) = Describe(frame, f);
            values.Add(new FieldValue(f, text, numeric));
        }

        return new DecodedFrame { Snapshot = snapshot, Values = values };
    }

    // ---------------------------------------------------------------- 取值

    private int Int32Of(ReadOnlySpan<byte> frame, string id) =>
        _byId.TryGetValue(id, out var f) ? BinaryPrimitives.ReadInt16BigEndian(frame[f.Offset..]) : 0;

    private float RealOf(ReadOnlySpan<byte> frame, string id) =>
        _byId.TryGetValue(id, out var f) ? BinaryPrimitives.ReadSingleBigEndian(frame[f.Offset..]) : 0f;

    private bool BoolOf(ReadOnlySpan<byte> frame, string id) =>
        _byId.TryGetValue(id, out var f) && f.Bit is { } bit && (frame[f.Offset] & (1 << bit)) != 0;

    private bool[] BoolsOf(ReadOnlySpan<byte> frame, string id, int count)
    {
        var result = new bool[count];
        if (!_byId.TryGetValue(id, out var f) || f.Elements is null)
            return result;

        foreach (var e in f.Elements)
        {
            if (e.Index >= 0 && e.Index < count)
                result[e.Index] = (frame[e.Byte] & (1 << e.Bit)) != 0;
        }
        return result;
    }

    private static (string Text, double Numeric) Describe(ReadOnlySpan<byte> frame, FieldDef f)
    {
        switch (f.Type)
        {
            case "Int":
            {
                var v = BinaryPrimitives.ReadInt16BigEndian(frame[f.Offset..]);
                return (v.ToString(), v);
            }
            case "Real":
            {
                var v = BinaryPrimitives.ReadSingleBigEndian(frame[f.Offset..]);
                return (v.ToString("F" + Math.Clamp(f.Decimals, 0, 4)), v);
            }
            case "Bool":
            {
                var on = f.Bit is { } bit && (frame[f.Offset] & (1 << bit)) != 0;
                return (on ? "TRUE" : "FALSE", on ? 1 : 0);
            }
            default:
            {
                if (f.Type.StartsWith("Bool[", StringComparison.Ordinal) && f.Elements is not null)
                {
                    var sb = new StringBuilder("[");
                    foreach (var e in f.Elements.OrderBy(e => e.Index))
                    {
                        if (sb.Length > 1) sb.Append(',');
                        sb.Append((frame[e.Byte] & (1 << e.Bit)) != 0 ? '1' : '0');
                    }
                    sb.Append(']');
                    return (sb.ToString(), 0);
                }

                if (f.Type.StartsWith("Int[", StringComparison.Ordinal) && f.Elements is not null)
                {
                    var sb2 = new StringBuilder("[");
                    foreach (var e in f.Elements.OrderBy(e => e.Index))
                    {
                        if (sb2.Length > 1) sb2.Append(',');
                        sb2.Append(BinaryPrimitives.ReadInt16BigEndian(frame[e.Byte..]));
                    }
                    sb2.Append(']');
                    return (sb2.ToString(), 0);
                }

                return ("—", 0);
            }
        }
    }
}
