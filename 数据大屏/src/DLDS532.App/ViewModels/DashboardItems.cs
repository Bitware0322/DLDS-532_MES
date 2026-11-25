using System.Windows.Media;
using DLDS532.DataModels;

namespace DLDS532.App.ViewModels;

/// <summary>仓位指示灯（三站 9 个仓位 A~I）：绿色有产品，灰色为空。</summary>
public sealed class SlotVm : ObservableObject
{
    private bool _occupied;
    private bool _unknown;

    public SlotVm(int dataIndex, string name)
    {
        DataIndex = dataIndex;
        Name = name;
    }

    /// <summary>DB120 仓位状态数组的下标（0 = 仓位 A）。与界面摆放位置无关。</summary>
    public int DataIndex { get; }
    public string Name { get; }

    /// <summary>DB120 地址：数组前 8 位落在 122.0~122.7，第 9 位（I）在 123.0。</summary>
    public string Address => DataIndex < 8 ? $"122.{DataIndex}" : "123.0";

    public bool Occupied
    {
        get => _occupied;
        set
        {
            if (!Set(ref _occupied, value)) return;
            OnPropertyChanged(nameof(Brush));
            OnPropertyChanged(nameof(StateText));
        }
    }

    /// <summary>无有效数据时置 true：显示「—」，不假装仓位是空的。</summary>
    public bool IsUnknown
    {
        get => _unknown;
        set
        {
            if (!Set(ref _unknown, value)) return;
            OnPropertyChanged(nameof(Brush));
            OnPropertyChanged(nameof(StateText));
        }
    }

    public Brush Brush => _unknown ? Palette.Gray : _occupied ? Palette.Green : Palette.Gray;

    public string StateText => _unknown ? "—" : _occupied ? "占用" : "空";
}
