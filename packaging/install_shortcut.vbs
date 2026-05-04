' BIG Hat Standalone V31 — Desktop-shortcut installer
' Drops a shortcut to start_bighat.vbs on the current user's Desktop.
' Run this once after install. Safe to re-run (it will overwrite).

Option Explicit

Dim WshShell, FSO, INSTALL_ROOT, DESKTOP, LNK, TARGET, ICON
Set WshShell = WScript.CreateObject("WScript.Shell")
Set FSO = WScript.CreateObject("Scripting.FileSystemObject")

' Edit this if you deploy elsewhere:
INSTALL_ROOT = "C:\BIG Hat\BIGHatStandalone"
TARGET       = INSTALL_ROOT & "\packaging\start_bighat.vbs"
ICON         = INSTALL_ROOT & "\packaging\bighat.ico"   ' optional; harmless if missing

If Not FSO.FileExists(TARGET) Then
    MsgBox "Cannot create shortcut — start_bighat.vbs not found at:" & vbCrLf & TARGET, _
           vbCritical, "BIG Hat Standalone"
    WScript.Quit 1
End If

DESKTOP = WshShell.SpecialFolders("Desktop")
Dim lnkPath
lnkPath = DESKTOP & "\BIG Hat Standalone.lnk"

Set LNK = WshShell.CreateShortcut(lnkPath)
LNK.TargetPath       = TARGET
LNK.WorkingDirectory = INSTALL_ROOT
LNK.WindowStyle      = 1
LNK.Description      = "BIG Hat Standalone V31 — Local Trivia Host"
If FSO.FileExists(ICON) Then LNK.IconLocation = ICON
LNK.Save

MsgBox "Shortcut created on your Desktop: BIG Hat Standalone.lnk", _
       vbInformation, "BIG Hat Standalone"
