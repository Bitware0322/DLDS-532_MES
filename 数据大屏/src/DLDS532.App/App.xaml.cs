using System.IO;
using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;
using DLDS532.App.ViewModels;
using DLDS532.Communication;
using DLDS532.DataModels;
using DLDS532.PlcData;
using DLDS532.Services;

namespace DLDS532.App;

/// <summary>
/// 组合根：加载映射 → 建立数据源 → 启动采集 → 打开主窗口。
/// 阶段二使用模拟帧源，阶段三把 SimulatedFrameSource 换成 S7 帧源即可，界面与解码不动。
/// </summary>
public partial class App : Application
{
    private PollingService? _polling;
    private RunEventLog? _eventLog;
    private MainViewModel? _viewModel;
    private MainWindow? _window;
    private string? _screenshotPath;

    protected override void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);

        try
        {
            StartupCore(e);
        }
        catch (Exception ex)
        {
            var log = Path.Combine(Path.GetTempPath(), "dlds532_startup_error.txt");
            try { File.WriteAllText(log, ex.ToString()); } catch { /* 忽略日志写入失败 */ }
            MessageBox.Show($"启动失败：{ex.Message}" + Environment.NewLine + Environment.NewLine +
                            $"详细信息：{log}", "DLDS-532",
                MessageBoxButton.OK, MessageBoxImage.Error);
            Shutdown(3);
        }
    }

    private void StartupCore(StartupEventArgs e)
    {

        DispatcherUnhandledException += (_, args) =>
        {
            MessageBox.Show(args.Exception.Message, "DLDS-532 运行异常",
                MessageBoxButton.OK, MessageBoxImage.Error);
            args.Handled = true;
        };

        var mappingPath = Db120Mapping.DefaultPath;
        Db120Mapping mapping;
        try
        {
            mapping = Db120Mapping.Load(mappingPath);
        }
        catch (Exception ex)
        {
            MessageBox.Show($"加载 DB120 地址映射表失败：\n{mappingPath}\n\n{ex.Message}",
                "DLDS-532", MessageBoxButton.OK, MessageBoxImage.Error);
            Shutdown(2);
            return;
        }

        // 配置持久化在 %LOCALAPPDATA%\DLDS532\settings.json，默认数据源为真实 PLC
        var settings = AppSettingsStore.Load();
        _screenshotPath = GetArg(e.Args, "--shot");
        var pageArg = GetArg(e.Args, "--page");

        // --source real|sim 可强制指定数据源（联调/出图用）；默认按配置，出图默认走模拟保证可复现
        var sourceArg = GetArg(e.Args, "--source");
        var mode = sourceArg?.ToLowerInvariant() switch
        {
            "real" => DataSourceMode.RealPlc,
            "sim" => DataSourceMode.Simulation,
            _ => _screenshotPath is not null ? DataSourceMode.Simulation : settings.DataSource,
        };

        var decoder = new Db120Decoder(mapping);
        var polling = new PollingService(CreateSource(mode, mapping), decoder, settings);
        _polling = polling;

        var eventPath = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "DLDS532", "run-events.jsonl");
        _eventLog = new RunEventLog(eventPath);

        var trend = new TrendBuffer(3600);

        // 只有模拟源才预置历史曲线；真实数据出图必须是真数据，不能掺入模拟点
        if (_screenshotPath is not null && mode == DataSourceMode.Simulation)
            SeedTrend(trend, mapping, 420);

        polling.Start();

        _viewModel = new MainViewModel(polling, trend, mapping, mappingPath, _eventLog);
        _viewModel.Settings.SourceModeChanged += newMode =>
            polling.ReplaceSource(CreateSource(newMode, mapping));
        if (int.TryParse(pageArg, out var pageIndex)) _viewModel.ShowPage(pageIndex);
        _window = new MainWindow { DataContext = _viewModel };

        if (_screenshotPath is not null)
        {
            _window.WindowStyle = WindowStyle.None;
            _window.ResizeMode = ResizeMode.NoResize;
            _window.Width = 1920;
            _window.Height = 1080;
            _window.WindowStartupLocation = WindowStartupLocation.Manual;
            _window.Left = -4000;
            _window.Top = -4000;
            _window.ShowInTaskbar = false;
        }

        _window.Show();

        if (_screenshotPath is not null)
        {
            var timer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(8500) };
            timer.Tick += (_, _) =>
            {
                timer.Stop();
                Capture(_screenshotPath);
            };
            timer.Start();
        }
    }

    private static IPlcFrameSource CreateSource(DataSourceMode mode, Db120Mapping mapping) =>
        mode == DataSourceMode.Simulation
            ? new SimulatedFrameSource(mapping)
            : new S7FrameSource();

    protected override void OnExit(ExitEventArgs e)
    {
        if (_polling is not null) AppSettingsStore.Save(_polling.Settings, out _);
        _viewModel?.Stop();
        _polling?.Dispose();
        _eventLog?.Dispose();
        base.OnExit(e);
    }

    /// <summary>截图模式：预置一段历史曲线，便于检查趋势图渲染（仅用于出图，不参与正常启动）。</summary>
    private static void SeedTrend(TrendBuffer trend, Db120Mapping mapping, int points)
    {
        var sim = new SimulatedFrameSource(mapping);
        sim.Connect(new PlcConnectionSettings(), out _);
        var decoder = new Db120Decoder(mapping);
        var now = DateTime.Now;

        for (int i = points; i > 0; i--)
        {
            var frame = sim.Read(mapping.Document.DbNumber, 0, mapping.Document.TotalBytes);
            var decoded = decoder.Decode(frame, now.AddSeconds(-i), PlcCpuState.Run);
            trend.Add(decoded.Snapshot);
        }

        sim.Dispose();
    }

    private void Capture(string path)
    {
        try
        {
            var rtb = new RenderTargetBitmap(1920, 1080, 96, 96, PixelFormats.Pbgra32);
            rtb.Render(_window!);

            var encoder = new PngBitmapEncoder();
            encoder.Frames.Add(BitmapFrame.Create(rtb));

            var dir = Path.GetDirectoryName(path);
            if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);

            using var stream = File.Create(path);
            encoder.Save(stream);
        }
        catch (Exception ex)
        {
            File.WriteAllText(path + ".error.txt", ex.ToString());
        }
        finally
        {
            Shutdown();
        }
    }

    private static string? GetArg(string[] args, string name)
    {
        for (int i = 0; i < args.Length; i++)
        {
            if (args[i].StartsWith(name + "=", StringComparison.OrdinalIgnoreCase))
                return args[i][(name.Length + 1)..];
            if (string.Equals(args[i], name, StringComparison.OrdinalIgnoreCase) && i + 1 < args.Length)
                return args[i + 1];
        }
        return null;
    }
}
