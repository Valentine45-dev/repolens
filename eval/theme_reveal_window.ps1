# For eval/theme_reveal_evidence.mjs: sizes the TEST Firefox window (found by its throwaway profile
# path, never any other window) to fill this PC's screen like a maximised window, without activating
# it or changing the window order, so it never comes in front of the owner's own windows.
param([int]$ProcId, [string]$Action, [string]$Out, [string]$Profile = "repolens-reveal-firefox")
Add-Type @"
using System; using System.Runtime.InteropServices;
public static class W {
  [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int cx, int cy, uint f);
}
"@
if ($Action -ne "size") { throw "only -Action size is supported" }
$h = [IntPtr]::Zero
if ($ProcId -gt 0) { $h = (Get-Process -Id $ProcId -ErrorAction SilentlyContinue).MainWindowHandle }
if (-not $h -or $h -eq [IntPtr]::Zero) {
  # Firefox's launcher hands over to a child process: find the window by the throwaway profile path.
  $ids = Get-CimInstance Win32_Process -Filter "Name='firefox.exe'" | Where-Object { $_.CommandLine -like "*$Profile*" } | ForEach-Object { $_.ProcessId }
  $p = Get-Process -Id $ids -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne [IntPtr]::Zero } | Select-Object -First 1
  if ($p) { $h = $p.MainWindowHandle }
}
if (-not $h -or $h -eq [IntPtr]::Zero) { throw "no test window found" }
# 1380x727 at (-7, 0): the 1366x720 work area plus the invisible resize borders. 0x14 = NOACTIVATE|NOZORDER.
[W]::SetWindowPos($h, [IntPtr]::Zero, -7, 0, 1380, 727, 0x14) | Out-Null
