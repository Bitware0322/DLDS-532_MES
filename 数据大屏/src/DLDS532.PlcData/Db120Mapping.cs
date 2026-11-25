using System.Text.Json;
using System.Text.Json.Serialization;

namespace DLDS532.PlcData;

public sealed class FieldElement
{
    public int Index { get; set; }
    public int Byte { get; set; }
    public int Bit { get; set; }
}

/// <summary>映射表中的一个字段（与 config/db120.mapping.json 对应）。</summary>
public sealed class FieldDef
{
    public string Path { get; set; } = "";
    public string Type { get; set; } = "";
    public int Offset { get; set; }
    public int? Bit { get; set; }
    public int Bytes { get; set; }
    public string Id { get; set; } = "";
    public string Label { get; set; } = "";
    public string Unit { get; set; } = "";
    public string Group { get; set; } = "";
    public int Decimals { get; set; }
    public bool Show { get; set; }
    public string Rw { get; set; } = "R";
    public string Note { get; set; } = "";
    public List<FieldElement>? Elements { get; set; }

    public bool IsArray => Elements is { Count: > 0 };
}

public sealed class MappingDocument
{
    public string SchemaVersion { get; set; } = "1.0";
    public int DbNumber { get; set; } = 120;
    public string BlockName { get; set; } = "";
    public string SourceExport { get; set; } = "";
    public int TotalBytes { get; set; }
    public string ByteOrder { get; set; } = "BigEndian";
    public List<FieldDef> Fields { get; set; } = new();
}

/// <summary>加载并校验 DB120 地址映射表。地址只来自配置文件，代码中不写死任何偏移。</summary>
public sealed class Db120Mapping
{
    private static readonly JsonSerializerOptions Options = new()
    {
        PropertyNameCaseInsensitive = true,
        ReadCommentHandling = JsonCommentHandling.Skip,
        AllowTrailingCommas = true,
        NumberHandling = JsonNumberHandling.AllowReadingFromString,
    };

    public MappingDocument Document { get; }

    private Db120Mapping(MappingDocument doc) => Document = doc;

    public static Db120Mapping Load(string path)
    {
        if (!File.Exists(path))
            throw new FileNotFoundException($"找不到 DB120 映射表：{path}", path);

        var doc = JsonSerializer.Deserialize<MappingDocument>(File.ReadAllText(path), Options)
                  ?? throw new InvalidDataException("映射表内容为空或格式不正确。");

        Validate(doc, path);
        return new Db120Mapping(doc);
    }

    /// <summary>默认路径：程序目录 config/db120.mapping.json。</summary>
    public static string DefaultPath =>
        Path.Combine(AppContext.BaseDirectory, "config", "db120.mapping.json");

    private static void Validate(MappingDocument doc, string path)
    {
        if (doc.TotalBytes <= 0)
            throw new InvalidDataException($"{path}：totalBytes 无效。");

        var dup = doc.Fields.GroupBy(f => f.Id).FirstOrDefault(g => g.Key.Length > 0 && g.Count() > 1);
        if (dup is not null)
            throw new InvalidDataException($"{path}：语义 ID 重复 {dup.Key}。");

        foreach (var f in doc.Fields)
        {
            if (f.Offset < 0 || f.Offset + Math.Max(f.Bytes, 0) > doc.TotalBytes)
                throw new InvalidDataException(
                    $"{path}：字段 {f.Path} 偏移 {f.Offset}+{f.Bytes} 超出 DB 长度 {doc.TotalBytes}。");

            if (f.Bit is < 0 or > 7)
                throw new InvalidDataException($"{path}：字段 {f.Path} 位号 {f.Bit} 非法。");

            if (f.Rw != "R")
                throw new InvalidDataException($"{path}：字段 {f.Path} 权限为 {f.Rw}，本项目只允许只读字段。");
        }
    }
}
