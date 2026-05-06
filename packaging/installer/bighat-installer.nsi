; BIG Hat Standalone V31 — NSIS Installer
;
; Produces a signed, modern Windows installer (.exe) that supersedes the
; legacy zip-and-copy distribution.
;
; Build (Linux/macOS dev box, requires `nsis` package):
;   makensis -DAPP_VERSION=31.0.0 \
;            -DSOURCE_ROOT=/app/dist/payload \
;            -DOUTPUT_FILE=/app/dist/BIGHatStandalone-Setup-31.0.0.exe \
;            packaging/installer/bighat-installer.nsi
;
; Or use scripts/build_installer.py which orchestrates payload assembly +
; makensis + (optional) Authenticode signing in one command.
;
; Required preprocessor symbols (-D...):
;   APP_VERSION   semver string written into the file metadata + registry
;   SOURCE_ROOT   absolute path to the prepared payload (python\, backend\, packaging\)
;   OUTPUT_FILE   absolute path of the .exe to produce
;
; Optional preprocessor symbols:
;   APP_PUBLISHER  defaults to "BH Entertainment"
;   APP_URL        defaults to "https://bighat.example"
;   PYTHON_DIRNAME directory name under SOURCE_ROOT that holds python.exe; default "python"

!ifndef APP_VERSION
  !error "APP_VERSION not provided. Use -DAPP_VERSION=31.0.0"
!endif
!ifndef SOURCE_ROOT
  !error "SOURCE_ROOT not provided. Use -DSOURCE_ROOT=/path/to/payload"
!endif
!ifndef OUTPUT_FILE
  !error "OUTPUT_FILE not provided. Use -DOUTPUT_FILE=/path/to/setup.exe"
!endif
!ifndef APP_PUBLISHER
  !define APP_PUBLISHER "BH Entertainment"
!endif
!ifndef APP_URL
  !define APP_URL "https://bighat.example"
!endif
!ifndef PYTHON_DIRNAME
  !define PYTHON_DIRNAME "python"
!endif

!define APP_NAME       "BIG Hat Standalone"
!define APP_INTERNAL   "BIGHatStandalone"
!define APP_REGKEY     "Software\${APP_PUBLISHER}\${APP_INTERNAL}"
!define APP_UNINSTKEY  "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_INTERNAL}"

; ===== Modern UI 2 =====
!include "MUI2.nsh"
!include "FileFunc.nsh"
!include "WordFunc.nsh"
!include "LogicLib.nsh"

; ===== Compression & metadata =====
SetCompressor /SOLID lzma
Name "${APP_NAME} ${APP_VERSION}"
OutFile "${OUTPUT_FILE}"
InstallDir "C:\BIG Hat\${APP_INTERNAL}"
InstallDirRegKey HKCU "${APP_REGKEY}" "InstallDir"
RequestExecutionLevel admin
ShowInstDetails show
ShowUninstDetails show
Unicode true

VIProductVersion "${APP_VERSION}.0"
VIAddVersionKey "ProductName"      "${APP_NAME}"
VIAddVersionKey "CompanyName"      "${APP_PUBLISHER}"
VIAddVersionKey "FileDescription"  "${APP_NAME} Installer"
VIAddVersionKey "FileVersion"      "${APP_VERSION}"
VIAddVersionKey "ProductVersion"   "${APP_VERSION}"
VIAddVersionKey "LegalCopyright"   "(c) ${APP_PUBLISHER}"
VIAddVersionKey "InternalName"     "${APP_INTERNAL}"
VIAddVersionKey "OriginalFilename" "BIGHatStandalone-Setup.exe"

; ===== UI flow =====
!define MUI_ICON   "..\bighat.ico"
!define MUI_UNICON "..\bighat.ico"
!define MUI_ABORTWARNING

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_FUNCTION LaunchApp
!define MUI_FINISHPAGE_LINK "Open ${APP_URL}"
!define MUI_FINISHPAGE_LINK_LOCATION "${APP_URL}"
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_WELCOME
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_UNPAGE_FINISH

!insertmacro MUI_LANGUAGE "English"

; ===== Variables for upgrade flow =====
Var PreviousInstallDir
Var PreviousVersion
Var SkipMigrate

; ===== Sections =====
Section "Core (required)" SEC_CORE
  SectionIn RO

  ; ---- Preflight: detect prior install + offer to migrate data ----
  ReadRegStr $PreviousInstallDir HKCU "${APP_REGKEY}" "InstallDir"
  ReadRegStr $PreviousVersion    HKCU "${APP_REGKEY}" "Version"
  StrCmp "$PreviousInstallDir" "" no_prev
    DetailPrint "Detected previous install at $PreviousInstallDir (version $PreviousVersion)"
    StrCmp "$PreviousInstallDir" "$INSTDIR" same_dir 0
      ; Different dir — leave the old install alone, but copy data\ if present.
      IfFileExists "$PreviousInstallDir\backend\data\*.*" 0 no_prev
        StrCpy $SkipMigrate "0"
        DetailPrint "Will migrate data\ from previous install"
        Goto no_prev
    same_dir:
      ; Same dir — let the file overwrite handle the upgrade.
      DetailPrint "Upgrading in-place at $INSTDIR"
  no_prev:

  SetOutPath "$INSTDIR"
  SetOverwrite on
  File /r "${SOURCE_ROOT}\*.*"

  ; ---- Migrate data\ from previous install if applicable ----
  StrCmp $SkipMigrate "0" 0 skip_migrate
    IfFileExists "$INSTDIR\backend\data\system_config.json" skip_migrate 0
      IfFileExists "$PreviousInstallDir\backend\data\*.*" 0 skip_migrate
        DetailPrint "Migrating user data from $PreviousInstallDir\backend\data"
        CopyFiles /SILENT "$PreviousInstallDir\backend\data\*.*" "$INSTDIR\backend\data"
  skip_migrate:

  ; ---- Registry: install metadata + Uninstall entry ----
  WriteRegStr HKCU "${APP_REGKEY}" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "${APP_REGKEY}" "Version"    "${APP_VERSION}"

  WriteRegStr HKCU "${APP_UNINSTKEY}" "DisplayName"     "${APP_NAME}"
  WriteRegStr HKCU "${APP_UNINSTKEY}" "DisplayVersion"  "${APP_VERSION}"
  WriteRegStr HKCU "${APP_UNINSTKEY}" "DisplayIcon"     '"$INSTDIR\BIGHat.exe"'
  WriteRegStr HKCU "${APP_UNINSTKEY}" "Publisher"       "${APP_PUBLISHER}"
  WriteRegStr HKCU "${APP_UNINSTKEY}" "URLInfoAbout"    "${APP_URL}"
  WriteRegStr HKCU "${APP_UNINSTKEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${APP_UNINSTKEY}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegDWORD HKCU "${APP_UNINSTKEY}" "NoModify" 1
  WriteRegDWORD HKCU "${APP_UNINSTKEY}" "NoRepair" 1

  ; ---- Estimated size for "Programs and Features" ----
  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  IntFmt $0 "0x%08X" $0
  WriteRegDWORD HKCU "${APP_UNINSTKEY}" "EstimatedSize" "$0"

  ; ---- Uninstaller ----
  WriteUninstaller "$INSTDIR\Uninstall.exe"
SectionEnd

Section "Desktop shortcut" SEC_DESKTOP
  SetShellVarContext current
  CreateShortCut "$DESKTOP\${APP_NAME}.lnk" \
                 "$INSTDIR\BIGHat.exe" \
                 '' \
                 "$INSTDIR\BIGHat.exe" 0
SectionEnd

Section "Start Menu shortcut" SEC_STARTMENU
  SetShellVarContext current
  CreateDirectory "$SMPROGRAMS\${APP_NAME}"
  CreateShortCut "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" \
                 "$INSTDIR\BIGHat.exe" \
                 '' \
                 "$INSTDIR\BIGHat.exe" 0
  CreateShortCut "$SMPROGRAMS\${APP_NAME}\Uninstall.lnk" \
                 "$INSTDIR\Uninstall.exe"
SectionEnd

Section /o "Auto-start at login" SEC_AUTOSTART
  SetShellVarContext current
  CreateShortCut "$SMPROGRAMS\..\..\..\Microsoft\Windows\Start Menu\Programs\Startup\${APP_NAME}.lnk" \
                 "$INSTDIR\BIGHat.exe" \
                 '' \
                 "$INSTDIR\BIGHat.exe" 0
SectionEnd

; ===== Section descriptions =====
LangString DESC_CORE      ${LANG_ENGLISH} "Application files, embedded Python runtime, and registry entries."
LangString DESC_DESKTOP   ${LANG_ENGLISH} "Place a shortcut on the Desktop."
LangString DESC_STARTMENU ${LANG_ENGLISH} "Add Start Menu entries (recommended)."
LangString DESC_AUTOSTART ${LANG_ENGLISH} "Run BIG Hat Standalone in the background at every Windows login."
!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SEC_CORE}      $(DESC_CORE)
  !insertmacro MUI_DESCRIPTION_TEXT ${SEC_DESKTOP}   $(DESC_DESKTOP)
  !insertmacro MUI_DESCRIPTION_TEXT ${SEC_STARTMENU} $(DESC_STARTMENU)
  !insertmacro MUI_DESCRIPTION_TEXT ${SEC_AUTOSTART} $(DESC_AUTOSTART)
!insertmacro MUI_FUNCTION_DESCRIPTION_END

; ===== Helper to launch the app from the Finish page =====
Function LaunchApp
  ExecShell "" "$INSTDIR\BIGHat.exe"
FunctionEnd

; ===== Uninstall =====
Section "Uninstall"
  ; Remove shortcuts
  SetShellVarContext current
  Delete "$DESKTOP\${APP_NAME}.lnk"
  RMDir /r "$SMPROGRAMS\${APP_NAME}"
  Delete "$SMPROGRAMS\..\..\..\Microsoft\Windows\Start Menu\Programs\Startup\${APP_NAME}.lnk"

  ; Remove install root contents (preserve user data\ unless they tick the option)
  Delete "$INSTDIR\Uninstall.exe"
  Delete "$INSTDIR\BIGHat.exe"
  Delete "$INSTDIR\VERSION.txt"
  RMDir /r "$INSTDIR\backend\static"
  RMDir /r "$INSTDIR\backend\__pycache__"
  RMDir /r "$INSTDIR\${PYTHON_DIRNAME}"
  RMDir /r "$INSTDIR\packaging"
  ; Backend tree (data\ inside is the user's; tell them, don't nuke).
  Delete "$INSTDIR\backend\*.py"
  Delete "$INSTDIR\backend\*.pyc"
  Delete "$INSTDIR\backend\.env"
  RMDir  "$INSTDIR\backend"
  ; Try to remove the install root only if empty (data\ may still live here).
  RMDir  "$INSTDIR"

  DeleteRegKey HKCU "${APP_REGKEY}"
  DeleteRegKey HKCU "${APP_UNINSTKEY}"

  DetailPrint "User data under $INSTDIR\backend\data was preserved."
  DetailPrint "Delete that folder manually if you want a full removal."
SectionEnd
