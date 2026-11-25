using DLDS532.DataModels;

namespace DLDS532.Services;

/// <summary>
/// 定长环形缓冲：每条曲线固定容量，运行多久都不会增长内存。
/// 默认 3600 点（1 秒一点 = 1 小时），超出后覆盖最旧点。
/// </summary>
public sealed class TrendBuffer
{
    private sealed class Ring
    {
        public Ring(int capacity)
        {
            Ts = new DateTime[capacity];
            Values = new float[capacity];
        }

        public DateTime[] Ts { get; }
        public float[] Values { get; }
        public int Start { get; private set; }
        public int Count { get; private set; }

        public void Add(DateTime ts, float value)
        {
            int index;
            if (Count < Ts.Length)
            {
                index = (Start + Count) % Ts.Length;
                Count++;
            }
            else
            {
                index = Start;
                Start = (Start + 1) % Ts.Length;
            }
            Ts[index] = ts;
            Values[index] = value;
        }

        public void Clear()
        {
            Start = 0;
            Count = 0;
        }

        public (DateTime[] Ts, float[] Values) Window(DateTime from)
        {
            var listTs = new List<DateTime>(Count);
            var listVal = new List<float>(Count);
            for (int i = 0; i < Count; i++)
            {
                int idx = (Start + i) % Ts.Length;
                if (Ts[idx] < from) continue;
                listTs.Add(Ts[idx]);
                listVal.Add(Values[idx]);
            }
            return (listTs.ToArray(), listVal.ToArray());
        }
    }

    private readonly object _gate = new();
    private readonly Dictionary<string, Ring> _rings;

    public TrendBuffer(int capacityPerSignal = 3600)
    {
        Capacity = capacityPerSignal;
        _rings = TrendSignals.All.ToDictionary(s => s.Key, _ => new Ring(capacityPerSignal));
    }

    public int Capacity { get; }

    public void Add(PlcSnapshot snapshot)
    {
        lock (_gate)
        {
            Add(TrendSignals.S1Depth, snapshot.Timestamp, snapshot.S1.Depth);
            Add(TrendSignals.S1TurnAngle, snapshot.Timestamp, snapshot.S1.TurntableAngle);
            Add(TrendSignals.S2Inject8, snapshot.Timestamp, snapshot.S2.Inject8mm);
            Add(TrendSignals.S2Inject10, snapshot.Timestamp, snapshot.S2.Inject10mm);
            Add(TrendSignals.S3Weight, snapshot.Timestamp, snapshot.S3.Weight);
            Add(TrendSignals.S3AxisX, snapshot.Timestamp, snapshot.S3.AxisX);
            Add(TrendSignals.S3AxisY, snapshot.Timestamp, snapshot.S3.AxisY);
        }
    }

    private void Add(string key, DateTime ts, float value)
    {
        if (_rings.TryGetValue(key, out var ring)) ring.Add(ts, value);
    }

    public (DateTime[] Ts, float[] Values) Window(string key, DateTime from)
    {
        lock (_gate)
        {
            return _rings.TryGetValue(key, out var ring)
                ? ring.Window(from)
                : (Array.Empty<DateTime>(), Array.Empty<float>());
        }
    }

    public int Count(string key)
    {
        lock (_gate) return _rings.TryGetValue(key, out var ring) ? ring.Count : 0;
    }

    public void Clear()
    {
        lock (_gate)
        {
            foreach (var ring in _rings.Values) ring.Clear();
        }
    }
}

/// <summary>按「运行模式 == 自动运行」累计单元工作时间（DB120 无此字段，软件侧计时）。</summary>
public sealed class WorkingTimeTracker
{
    private TimeSpan _total;

    public TimeSpan Total => _total;

    public void Accumulate(TimeSpan delta, bool running)
    {
        if (!running || delta <= TimeSpan.Zero) return;
        if (delta > TimeSpan.FromSeconds(5)) delta = TimeSpan.FromSeconds(5); // 防止休眠/暂停造成跳变
        _total += delta;
    }

    public void Reset() => _total = TimeSpan.Zero;
}
