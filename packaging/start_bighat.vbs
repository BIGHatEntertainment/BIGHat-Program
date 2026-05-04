' BIG Hat Standalone V31 — Windows silent-start launcher
' Runs the Python launcher without a visible console window.
'
' Place this file alongside BIG Hat Standalone\ on the target machine
' (typical install root: C:\BIG Hat\BIGHatStandalone\). Double-click to
' launch; right-click -> "Create shortcut" for a Start-menu entry.
'
' Expects:
'   C:\BIG Hat\BIGHatStandalone\python\python.exe
'   C:\BIG Hat\BIGHatStandalone\backend\launcher.py
' Edit INSTALL_ROOT below if you deploy elsewhere.

Option Explicit

Dim WshShell, FSO, INSTALL_ROOT, PY, LAUNCHER, CMD
Set WshShell = WScript.CreateObject("WScript.Shell")
Set FSO = WScript.CreateObject("Scripting.FileSystemObject")

' -------- Edit INSTALL_ROOT if your install path differs --------
INSTALL_ROOT = "C:\BIG Hat\BIGHatStandalone"
' ---------------------------------------------------------------

PY       = INSTALL_ROOT & "\python\python.exe"
LAUNCHER = INSTALL_ROOT & "\backend\launcher.py"

If Not FSO.FileExists(PY) Then
    MsgBox "BIG Hat Standalone: python runtime not found at " & PY & vbCrLf & _
           "Re-run the installer or edit start_bighat.vbs to point at the correct path.", _
           vbCritical, "BIG Hat Standalone"
    WScript.Quit 1
End If
If Not FSO.FileExists(LAUNCHER) Then
    MsgBox "BIG Hat Standalone: launcher not found at " & LAUNCHER, _
           vbCritical, "BIG Hat Standalone"
    WScript.Quit 1
End If

CMD = """" & PY & """ """ & LAUNCHER & """"

' 0 = hide window, False = don't wait for exit (server stays running)
WshShell.Run CMD, 0, False
