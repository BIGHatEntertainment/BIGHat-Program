Set WshShell = CreateObject("WScript.Shell")
intAnswer = MsgBox("Are you sure you want to completely uninstall the BIG Hat Entertainment Hub and all local data?", 36, "BIG Hat Uninstall Wizard")

If intAnswer = 6 Then
    ' 1. Clean up Desktop Shortcut
    strDesktop = WshShell.SpecialFolders("Desktop")
    Set fso = CreateObject("Scripting.FileSystemObject")
    
    If fso.FileExists(strDesktop & "\BIG Hat Hub.lnk") Then
        fso.DeleteFile(strDesktop & "\BIG Hat Hub.lnk")
    End If

    ' 2. Try to stop any running instances
    On Error Resume Next
    WshShell.Run "taskkill /F /IM python.exe /T", 0, True
    WshShell.Run "taskkill /F /IM msedge.exe /FI ""WINDOWTITLE eq BIG Hat*""", 0, True
    On Error GoTo 0

    MsgBox "Desktop shortcut and background processes have been cleared." & vbCrLf & vbCrLf & "To complete the uninstallation, simply delete the 'C:\BIG Hat' folder.", 64, "Uninstall Successful"
End If
