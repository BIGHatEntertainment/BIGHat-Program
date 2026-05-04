Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
strPath = fso.GetAbsolutePathName(".")

' Create Desktop Shortcut
strDesktop = WshShell.SpecialFolders("Desktop")
Set oShellLink = WshShell.CreateShortcut(strDesktop & "\BIG Hat Hub.lnk")
oShellLink.TargetPath = chr(34) & strPath & "\BIGHat_Launcher.vbs" & chr(34)
oShellLink.WindowStyle = 1
oShellLink.IconLocation = strPath & "\backend\static\favicon.ico"
oShellLink.WorkingDirectory = strPath
oShellLink.Save

MsgBox "BIGHat Master Setup Complete!" & vbCrLf & vbCrLf & "Shortcut created on Desktop. Launching Hub...", 64, "Setup Finished"

' Launch the app
WshShell.Run "wscript.exe " & chr(34) & strPath & "\BIGHat_Launcher.vbs" & chr(34), 0, False
