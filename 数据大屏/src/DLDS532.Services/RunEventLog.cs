using System.Text;
using System.Text.Encodings.Web;
using System.Text.Json;
using DLDS532.DataModels;

namespace DLDS532.Services;

/// <summary>
/// 运行事件环形缓冲（固定容量，永不无限增长）。
/// 可选追加写入 JSONL 文件，供后续阶段导入 SQLite / 导出报表；写失败不影响采集。
/// </summary>
public sealed class RunEventLog : IDisposable
{
    /// <summary>内存中最多保留的事件条数。</summary>
    public const int Capacity = 300;

    private const long MaxFileBytes = 4 * 1024 * 1024;

    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
    };

    private readonly object _gate = new();
    private readonly LinkedList<RunEventRecord> _items = new();
    private readonly StreamWriter? _writer;
    private long _total;

    public RunEventLog(string? persistPath = null)
    {
        if (string.IsNullOrWhiteSpace(persistPath)) return;

        try
        {
            var dir = Path.GetDirectoryName(persistPath);
            if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);

            if (File.Exists(persistPath) && new FileInfo(persistPath).Length > MaxFileBytes)
                File.Move(persistPath, persistPath + ".old", overwrite: true);

            LoadTail(persistPath, 12);

            var stream = new FileStream(persistPath, FileMode.Append, FileAccess.Write, FileShare.Read);
            _writer = new StreamWriter(stream, new UTF8Encoding(false)) { AutoFlush = true };
        }
        catch
        {
            // 落盘失败只影响历史留存，不影响界面事件
            _writer = null;
        }
    }

    public bool IsPersisting => _writer is not null;

    /// <summary>启动时把上次运行的最后若干条真实事件读回界面，避免一开机事件区是空的。</summary>
    private void LoadTail(string path, int count)
    {
        try
        {
            if (!File.Exists(path)) return;

            using var fs = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite);
            int take = (int)Math.Min(fs.Length, 16 * 1024);
            if (take <= 0) return;

            fs.Seek(-take, SeekOrigin.End);
            var buffer = new byte[take];
            fs.ReadExactly(buffer);

            var lines = Encoding.UTF8.GetString(buffer)
                .Split('\n', StringSplitOptions.RemoveEmptyEntries);

            var records = new List<RunEventRecord>();
            foreach (var line in lines)
            {
                var trimmed = line.Trim();
                if (!trimmed.StartsWith('{')) continue;   // 首行可能被截断
                try
                {
                    using var doc = JsonDocument.Parse(trimmed);
                    var root = doc.RootElement;
                    var time = DateTime.TryParse(root.GetProperty("t").GetString(), out var t) ? t : DateTime.Now;
                    var level = Enum.TryParse<RunEventLevel>(root.GetProperty("l").GetString(), out var lv)
                        ? lv
                        : RunEventLevel.Info;
                    records.Add(new RunEventRecord(time, root.GetProperty("u").GetString() ?? "",
                        root.GetProperty("m").GetString() ?? "", level));
                }
                catch
                {
                    // 跳过损坏行
                }
            }

            foreach (var record in records.TakeLast(count))
            {
                _items.AddLast(record);
                _total++;
            }
        }
        catch
        {
            // 读取历史失败不影响本次运行
        }
    }

    public long TotalCount
    {
        get { lock (_gate) return _total; }
    }

    public void Add(RunEventRecord record)
    {
        lock (_gate)
        {
            _items.AddLast(record);
            while (_items.Count > Capacity) _items.RemoveFirst();
            _total++;

            if (_writer is null) return;
            try
            {
                _writer.WriteLine(JsonSerializer.Serialize(new
                {
                    t = record.Time.ToString("yyyy-MM-dd HH:mm:ss"),
                    u = record.Unit,
                    m = record.Message,
                    l = record.Level.ToString(),
                }, JsonOptions));
            }
            catch
            {
                // 忽略单条写失败
            }
        }
    }

    /// <summary>取最近 count 条，**最新的在前**。</summary>
    public IReadOnlyList<RunEventRecord> Recent(int count)
    {
        lock (_gate)
        {
            if (count <= 0) return Array.Empty<RunEventRecord>();
            var result = new List<RunEventRecord>(Math.Min(count, _items.Count));
            for (var node = _items.Last; node is not null && result.Count < count; node = node.Previous)
                result.Add(node.Value);
            return result;
        }
    }

    public void Dispose()
    {
        lock (_gate)
        {
            try { _writer?.Flush(); _writer?.Dispose(); } catch { /* 退出时忽略 */ }
        }
    }
}
