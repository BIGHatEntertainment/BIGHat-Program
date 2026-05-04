Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
strCurrentDir = fso.GetAbsolutePathName(".")

' --- 1. CHECK IF SYSTEM IS INITIALIZED ---
strConfigPath = strCurrentDir & "\backend\system_config.json"
blnSetupNeeded = Not fso.FileExists(strConfigPath)

If blnSetupNeeded Then
    ' --- 2. RUN INTEGRATED SETUP WIZARD ---
    MsgBox "Welcome to BIG Hat Entertainment." & vbCrLf & vbCrLf & "Initializing Proprietary Standalone Environment...", 64, "BIGHat Setup"
    
    ' Check for 25GB Free Space
    dblRequiredSpace = 26843545600 
    strDrive = fso.GetDriveName(strCurrentDir)
    Set objDrive = fso.GetDrive(strDrive)

    If objDrive.FreeSpace < dblRequiredSpace Then
        MsgBox "CRITICAL ERROR: Insufficient Disk Space." & vbCrLf & "25GB required for proprietary game data." & vbCrLf & "Available: " & FormatNumber(objDrive.FreeSpace / 1073741824, 2) & " GB", 16, "Setup Aborted"
        WScript.Quit
    End If

    ' Map the Drive
    strDefaultPath = "C:\BIG Hat"
    strInstallPath = InputBox("Please confirm your installation directory:", "Mapping BIG Hat Drive", strDefaultPath)
    If strInstallPath = "" Then WScript.Quit
    
    ' Create Desktop Shortcut with BIG Hat Logo
    strDesktop = WshShell.SpecialFolders("Desktop")
    Set oShellLink = WshShell.CreateShortcut(strDesktop & "\BIG Hat Hub.lnk")
    oShellLink.TargetPath = chr(34) & strCurrentDir & "\BIGHat_Launcher.vbs" & chr(34)
    oShellLink.WindowStyle = 1
    oShellLink.IconLocation = strCurrentDir & "\backend\static\favicon.ico"
    oShellLink.WorkingDirectory = strCurrentDir
    oShellLink.Save
    
    MsgBox "System Mapped & Shortcut Created!" & vbCrLf & "The Hub will now launch for Account Activation.", 64, "Setup Complete"
End If

' --- 3. SILENTLY LAUNCH ENGINE ---
WshShell.Run chr(34) & strCurrentDir & "\launch.bat" & chr(34), 0, False
