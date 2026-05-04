Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

' --- WELCOME ---
MsgBox "Welcome to BIG Hat Entertainment." & vbCrLf & vbCrLf & "STEP 1: Mapping the Proprietary Drive.", 64, "BIGHat Installer - Step 1"

' --- SPACE CHECK (25GB) ---
dblRequiredSpace = 26843545600 
strDrive = "C:"
Set objDrive = fso.GetDrive(strDrive)

If objDrive.FreeSpace < dblRequiredSpace Then
    MsgBox "CRITICAL ERROR: Insufficient Disk Space (25GB Required)." & vbCrLf & "Setup Aborted.", 16, "BIGHat Setup"
    WScript.Quit
End If

' --- CREATE FOLDER ---
strInstallPath = "C:\BIG Hat"
If Not fso.FolderExists(strInstallPath) Then
    On Error Resume Next
    fso.CreateFolder(strInstallPath)
    If Err.Number <> 0 Then
        MsgBox "Error: Could not create C:\BIG Hat. Please run this script as Administrator.", 16, "Permission Denied"
        WScript.Quit
    End If
    On Error GoTo 0
End If

MsgBox "SUCCESS: C:\BIG Hat has been mapped." & vbCrLf & vbCrLf & "Now follow Step 2 in the INSTALL_INSTRUCTIONS.txt file.", 64, "Step 1 Complete"
