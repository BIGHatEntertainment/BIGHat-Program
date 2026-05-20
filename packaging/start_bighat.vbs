' BIG Hat Entertainment — Windows launcher (start_bighat.vbs)
'
' Boots the bundled Python backend, waits for the local FastAPI server to
' come up on 127.0.0.1:8001, then opens it in the user's default browser.
'
' This is the primary launch path for ALL shortcuts (Desktop, Start Menu,
' Auto-start) AND for file-association handoffs from BIGHat.exe (which
' forwards .bighat double-clicks here as the first argument).
'
' Default install root: C:\BIG Hat\BIGHatStandalone\
' Edit INSTALL_ROOT below ONLY if you deploy elsewhere.

Option Explicit

Dim WshShell, FSO, INSTALL_ROOT, PY, LAUNCHER, CMD
Set WshShell = WScript.CreateObject("WScript.Shell")
Set FSO      = WScript.CreateObject("Scripting.FileSystemObject")

' -------- Edit INSTALL_ROOT if your install path differs --------
INSTALL_ROOT = "C:\BIG Hat\BIGHatStandalone"
' ---------------------------------------------------------------

PY       = INSTALL_ROOT & "\python\pythonw.exe"
If Not FSO.FileExists(PY) Then PY = INSTALL_ROOT & "\python\python.exe"

LAUNCHER = INSTALL_ROOT & "\backend\launcher.py"

Dim CRASHLOG
CRASHLOG = INSTALL_ROOT & "\backend\data\logs\launcher_crash.log"

' Make sure the crash-log directory exists so launcher.py can write it.
On Error Resume Next
FSO.CreateFolder(INSTALL_ROOT & "\backend\data")
FSO.CreateFolder(INSTALL_ROOT & "\backend\data\logs")
On Error Goto 0

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

' --------- Pass through an optional file-association argument ---------
' If the user double-clicks a .bighat file, BIGHat.exe forwards it here
' as WScript.Arguments(0). We strip the path into a URL query parameter
' so the React frontend can pick it up on the dashboard.
Dim OPEN_QUERY, OPEN_PATH
OPEN_QUERY = ""
If WScript.Arguments.Count > 0 Then
    OPEN_PATH = WScript.Arguments(0)
    If Len(OPEN_PATH) > 0 Then
        ' Crude URL-encode of backslashes + spaces for the openFile= param.
        OPEN_PATH = Replace(OPEN_PATH, "\", "/")
        OPEN_PATH = Replace(OPEN_PATH, " ", "%20")
        OPEN_QUERY = "/roundmaker?openFile=" & OPEN_PATH
    End If
End If

' --------- Single-instance: if backend already running, just open URL ---------
Dim http, alreadyUp
alreadyUp = False
On Error Resume Next
Set http = CreateObject("MSXML2.XMLHTTP.6.0")
http.open "GET", "http://127.0.0.1:8001/", False
http.send
If Err.Number = 0 And http.Status > 0 Then alreadyUp = True
Err.Clear
On Error Goto 0

If alreadyUp Then
    WshShell.Run "http://127.0.0.1:8001" & OPEN_QUERY, 1, False
    WScript.Quit 0
End If

' --------- Spawn the backend (hidden, with --no-browser) ---------
CMD = """" & PY & """ """ & LAUNCHER & """ --no-browser"
' 0 = hide window, False = don't wait for exit (server stays running)
WshShell.Run CMD, 0, False

' --------- Health check: wait up to 25 seconds for port 8001 to bind ---------
Dim ok, attempt
ok = False
For attempt = 1 To 25
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
    msg = "BIG Hat Entertainment didn't start within 25 seconds." & vbCrLf & vbCrLf
    If FSO.FileExists(CRASHLOG) Then
        msg = msg & "A crash log was written to:" & vbCrLf & CRASHLOG & vbCrLf & vbCrLf & _
                    "Please email that file to support@bighat.live."
    Else
        msg = msg & "No crash log was produced - Python may have failed to start " & _
                    "(antivirus quarantine, missing files, or permissions)." & vbCrLf & vbCrLf & _
                    "Try running the app once as Administrator, then email " & _
                    "support@bighat.live if it still doesn't open."
    End If
    MsgBox msg, vbExclamation, "BIG Hat Entertainment"
    WScript.Quit 1
End If

' --------- Open the user's default browser at the local app URL ---------
' (1 = show normal window; False = don't wait for browser exit so this VBS
' returns immediately and the user gets snappy feedback.)
WshShell.Run "http://127.0.0.1:8001" & OPEN_QUERY, 1, False
WScript.Quit 0
