' BIG Hat Entertainment — Windows silent-start launcher (with health check)
'
' Boots the bundled Python launcher in the background, then waits up to 12s
' for the local FastAPI server to come up. If the server never answers
' (typical cause: missing Python wheel, corrupted install, antivirus quarantine),
' we surface a friendly MsgBox pointing the user at the crash log instead of
' just leaving them with a black-screen "nothing happened" experience.
'
' Default install root: C:\BIG Hat\BIGHatStandalone\
' Edit INSTALL_ROOT below if you deploy elsewhere.

Option Explicit

Dim WshShell, FSO, INSTALL_ROOT, PY, LAUNCHER, CMD
Set WshShell = WScript.CreateObject("WScript.Shell")
Set FSO = WScript.CreateObject("Scripting.FileSystemObject")

' -------- Edit INSTALL_ROOT if your install path differs --------
INSTALL_ROOT = "C:\BIG Hat\BIGHatStandalone"
' ---------------------------------------------------------------

PY       = INSTALL_ROOT & "\python\pythonw.exe"
' Fall back to python.exe if pythonw.exe somehow missing (older embeds did skip it).
If Not FSO.FileExists(PY) Then PY = INSTALL_ROOT & "\python\python.exe"

LAUNCHER = INSTALL_ROOT & "\backend\launcher.py"
Dim CRASHLOG
CRASHLOG = INSTALL_ROOT & "\backend\data\logs\launcher_crash.log"

If Not FSO.FileExists(PY) Then
    MsgBox "BIG Hat Entertainment: python runtime not found at " & PY & vbCrLf & vbCrLf & _
           "Please re-run the installer.", _
           vbCritical, "BIG Hat Entertainment"
    WScript.Quit 1
End If
If Not FSO.FileExists(LAUNCHER) Then
    MsgBox "BIG Hat Entertainment: launcher not found at " & LAUNCHER & vbCrLf & vbCrLf & _
           "Please re-run the installer.", _
           vbCritical, "BIG Hat Entertainment"
    WScript.Quit 1
End If

CMD = """" & PY & """ """ & LAUNCHER & """"

' 0 = hide window, False = don't wait for exit (server stays running)
WshShell.Run CMD, 0, False

' ---- Health check: wait up to 12 seconds for the server to bind port 8001 ----
Dim http, ok, attempt
ok = False
For attempt = 1 To 12
    WScript.Sleep 1000
    On Error Resume Next
    Set http = CreateObject("MSXML2.XMLHTTP.6.0")
    http.open "GET", "http://127.0.0.1:8001/", False
    http.send
    If Err.Number = 0 And http.Status > 0 Then
        ok = True
        Exit For
    End If
    Err.Clear
    On Error Goto 0
Next

If Not ok Then
    Dim msg
    msg = "BIG Hat Entertainment didn't start within 12 seconds." & vbCrLf & vbCrLf
    If FSO.FileExists(CRASHLOG) Then
        msg = msg & "A crash log was written to:" & vbCrLf & CRASHLOG & vbCrLf & vbCrLf & _
                    "Please email that file to support@bighat.live."
    Else
        msg = msg & "No crash log was produced — Python may have failed to start " & _
                    "(antivirus quarantine, missing files, or permissions)." & vbCrLf & vbCrLf & _
                    "Try running the app once as Administrator, then email " & _
                    "support@bighat.live if it still doesn't open."
    End If
    MsgBox msg, vbExclamation, "BIG Hat Entertainment"
End If
