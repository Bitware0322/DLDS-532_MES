using System.Text.Json;
using DLDS532.DataModels;

namespace DLDS532.Services;

/// <summary>
/// 通信参数的本地持久化（%LOCALAPPDATA%\DLDS532\settings.json）。
/// 只保存配置，不保存任何 PLC 数据；读写失败一律回退到默认值，不影响启动。
/// </summary>
public static class AppSettingsStore
{
    private static readonly JsonSerializerOptions Options = new()
    {
        WriteIndented = true,
        PropertyNameCaseInsensitive = true,
    };

    public static string FilePath => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "DLDS532", "settings.json");

    public static PlcConnectionSettings Load()
    {
        try
        {
            if (!File.Exists(FilePath)) return new PlcConnectionSettings();
            var json = File.ReadAllText(FilePath);
            return JsonSerializer.Deserialize<PlcConnectionSettings>(json, Options) ?? new PlcConnectionSettings();
        }
        catch
        {
            return new PlcConnectionSettings();
        }
    }

    public static bool Save(PlcConnectionSettings settings, out string? error)
    {
        error = null;
        try
        {
            var dir = Path.GetDirectoryName(FilePath);
            if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);
            File.WriteAllText(FilePath, JsonSerializer.Serialize(settings, Options));
            return true;
        }
        catch (Exception ex)
        {
            error = ex.Message;
            return false;
        }
    }
}
