using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Input;
using System.Windows.Interop;

namespace DLDS532.App;

public partial class MainWindow : Window
{
    private bool _isFullscreen;
    private WindowState _stateBeforeFullscreen = WindowState.Normal;

    public MainWindow()
    {
        InitializeComponent();

        SourceInitialized += (_, _) => TryEnableDarkTitleBar();

        PreviewKeyDown += (_, e) =>
        {
            switch (e.Key)
            {
                case Key.F11:
                    ToggleFullscreen();
                    e.Handled = true;
                    break;
                case Key.Escape when _isFullscreen:
                    ToggleFullscreen();
                    e.Handled = true;
                    break;
            }
        };
    }

    /// <summary>F11 进入无边框全屏（大屏模式），Esc 退出。</summary>
    private void ToggleFullscreen()
    {
        if (!_isFullscreen)
        {
            _stateBeforeFullscreen = WindowState;
            WindowState = WindowState.Normal;
            WindowStyle = WindowStyle.None;
            ResizeMode = ResizeMode.NoResize;
            WindowState = WindowState.Maximized;
            _isFullscreen = true;
        }
        else
        {
            WindowState = WindowState.Normal;
            WindowStyle = WindowStyle.SingleBorderWindow;
            ResizeMode = ResizeMode.CanResize;
            WindowState = _stateBeforeFullscreen == WindowState.Maximized
                ? WindowState.Maximized
                : WindowState.Normal;
            _isFullscreen = false;
        }
    }

    private const int DwmwaUseImmersiveDarkMode = 20;
    private const int DwmwaUseImmersiveDarkModeLegacy = 19;

    [DllImport("dwmapi.dll", PreserveSig = true)]
    private static extern int DwmSetWindowAttribute(IntPtr hwnd, int attribute, ref int value, int size);

    /// <summary>把系统标题栏切换为深色，避免浅色标题栏破坏大屏观感（失败不影响功能）。</summary>
    private void TryEnableDarkTitleBar()
    {
        try
        {
            var handle = new WindowInteropHelper(this).Handle;
            int enabled = 1;
            if (DwmSetWindowAttribute(handle, DwmwaUseImmersiveDarkMode, ref enabled, sizeof(int)) != 0)
                DwmSetWindowAttribute(handle, DwmwaUseImmersiveDarkModeLegacy, ref enabled, sizeof(int));
        }
        catch
        {
            // 旧系统不支持则保持系统默认
        }
    }
}
