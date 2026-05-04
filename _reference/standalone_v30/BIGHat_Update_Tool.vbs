Set WshShell = CreateObject("WScript.Shell")
intAnswer = MsgBox("The BIGHat Update Tool will now check for the latest proprietary patches. Proceed?", 36, "BIG Hat Update Tool")

If intAnswer = 6 Then
    ' In a real scenario, this would run a background python script to fetch and swap files
    MsgBox "Checking for updates... BIGHat Hub is currently up to date (Version 1.0.0).", 64, "System Up To Date"
End If
