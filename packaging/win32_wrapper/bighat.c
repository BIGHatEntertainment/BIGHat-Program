/*
 * BIG Hat Entertainment — Windows launcher (BIGHat.exe)
 *
 * Replaces the wscript.exe + start_bighat.vbs chain with a real,
 * icon-bearing Win32 GUI executable so:
 *   - Task Manager shows "BIG Hat Entertainment" with the hat icon
 *   - The Start Menu / Desktop shortcuts have a proper app target
 *   - The installer's Finish page launches a polished EXE, not a script
 *   - .bighat files can be double-clicked in Explorer to open the round
 *
 * Argv handling:
 *   BIGHat.exe                 → just launch the app
 *   BIGHat.exe "C:\path.bighat" → launch + open this round file
 *
 * Behaviour:
 *   1. Resolve install root from GetModuleFileNameW (we live at
 *      INSTALL_ROOT\BIGHat.exe alongside python\, backend\, packaging\).
 *   2. Build the target URL — http://127.0.0.1:8001/roundmaker?openFile=<path>
 *      (or just / if no file was passed).
 *   3. Single-instance: if port 8001 is already listening, just
 *      ShellExecuteW the URL in the user's browser and exit immediately.
 *   4. Otherwise spawn `python\pythonw.exe backend\launcher.py --no-browser`
 *      with CREATE_NO_WINDOW | DETACHED_PROCESS, then poll TCP 8001 for up
 *      to 12 s, then ShellExecuteW the URL ourselves.
 *   5. On failure: surface a MessageBoxW pointing the user at
 *      backend\data\logs\launcher_crash.log so they have something
 *      concrete to send to support@bighat.live.
 */

#ifndef UNICODE
#define UNICODE
#endif
#ifndef _UNICODE
#define _UNICODE
#endif
#define WIN32_LEAN_AND_MEAN
#define _WIN32_WINNT 0x0600

#include <windows.h>
#include <winsock2.h>
#include <ws2tcpip.h>
#include <shlwapi.h>
#include <shellapi.h>
#include <strsafe.h>
#include <stdio.h>
#include <wchar.h>

#define APP_TITLE        L"BIG Hat Entertainment"
#define LAUNCHER_PORT    8001
#define LAUNCHER_HOST    L"http://127.0.0.1:8001"
#define ROUNDMAKER_PATH  L"/roundmaker"
#define HEALTHCHECK_SECS 12
#define STARTUP_GRACE_MS 800

static void path_join(wchar_t *out, size_t out_len, const wchar_t *root, const wchar_t *suffix) {
    StringCchCopyW(out, out_len, root);
    PathAppendW(out, suffix);
}

/* Percent-encode a UTF-8 byte for inclusion in a URL query parameter. */
static int is_unreserved(unsigned char c) {
    return (c >= '0' && c <= '9') || (c >= 'A' && c <= 'Z') ||
           (c >= 'a' && c <= 'z') || c == '-' || c == '_' || c == '.' || c == '~';
}

/* Convert wide string -> UTF-8 -> percent-encode. Result written into `out`
 * as a wide string suitable for ShellExecuteW. Returns 1 on success.       */
static int url_encode_w(const wchar_t *in, wchar_t *out, size_t out_len) {
    /* wide -> UTF-8 */
    int u8len = WideCharToMultiByte(CP_UTF8, 0, in, -1, NULL, 0, NULL, NULL);
    if (u8len <= 0) return 0;
    char *u8 = (char *)HeapAlloc(GetProcessHeap(), 0, (size_t)u8len);
    if (!u8) return 0;
    WideCharToMultiByte(CP_UTF8, 0, in, -1, u8, u8len, NULL, NULL);

    /* percent-encode into a temp char buffer */
    size_t cap = (size_t)u8len * 3 + 1;
    char *enc = (char *)HeapAlloc(GetProcessHeap(), 0, cap);
    if (!enc) { HeapFree(GetProcessHeap(), 0, u8); return 0; }
    size_t j = 0;
    for (size_t i = 0; i + 1 < (size_t)u8len; i++) {  /* skip terminating NUL */
        unsigned char c = (unsigned char)u8[i];
        if (is_unreserved(c)) {
            enc[j++] = (char)c;
        } else {
            static const char hex[] = "0123456789ABCDEF";
            enc[j++] = '%';
            enc[j++] = hex[(c >> 4) & 0xF];
            enc[j++] = hex[c & 0xF];
        }
    }
    enc[j] = '\0';

    /* UTF-8 (ASCII subset only, since we only emit ASCII) -> wide */
    int ok = MultiByteToWideChar(CP_UTF8, 0, enc, -1, out, (int)out_len) > 0;
    HeapFree(GetProcessHeap(), 0, enc);
    HeapFree(GetProcessHeap(), 0, u8);
    return ok;
}

static int port_is_listening(int port) {
    SOCKET s = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (s == INVALID_SOCKET) return 0;
    u_long one = 1;
    ioctlsocket(s, FIONBIO, &one);

    struct sockaddr_in addr;
    ZeroMemory(&addr, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_port = htons((u_short)port);
    addr.sin_addr.s_addr = htonl(0x7F000001);

    int rc = connect(s, (struct sockaddr *)&addr, sizeof(addr));
    int connected = 0;
    if (rc == 0) {
        connected = 1;
    } else if (WSAGetLastError() == WSAEWOULDBLOCK) {
        fd_set wfds;
        FD_ZERO(&wfds);
        FD_SET(s, &wfds);
        struct timeval tv = { 0, 500 * 1000 };
        if (select(0, NULL, &wfds, NULL, &tv) > 0) {
            int err = 0;
            int err_len = sizeof(err);
            getsockopt(s, SOL_SOCKET, SO_ERROR, (char *)&err, &err_len);
            if (err == 0) connected = 1;
        }
    }
    closesocket(s);
    return connected;
}

static void show_error(const wchar_t *msg) {
    MessageBoxW(NULL, msg, APP_TITLE, MB_OK | MB_ICONERROR | MB_SETFOREGROUND);
}

/* Build the URL the browser should open: base + optional ?openFile=<path>. */
static void build_target_url(wchar_t *out, size_t out_len, const wchar_t *open_file) {
    if (open_file && open_file[0]) {
        wchar_t encoded[8192];
        if (url_encode_w(open_file, encoded, sizeof(encoded) / sizeof(encoded[0]))) {
            StringCchPrintfW(out, out_len, L"%ls%ls?openFile=%ls",
                             LAUNCHER_HOST, ROUNDMAKER_PATH, encoded);
            return;
        }
    }
    StringCchCopyW(out, out_len, LAUNCHER_HOST L"/");
}

int WINAPI wWinMain(HINSTANCE hInst, HINSTANCE hPrev, LPWSTR lpCmd, int nShow) {
    (void)hInst; (void)hPrev; (void)nShow;

    /* --- Parse argv: optional file path argument. --- */
    int argc = 0;
    LPWSTR *argv = CommandLineToArgvW(GetCommandLineW(), &argc);
    const wchar_t *open_file = NULL;
    if (argv && argc >= 2 && argv[1] && argv[1][0]) {
        open_file = argv[1];
    }
    (void)lpCmd;

    /* --- Resolve install root from this exe's path. --- */
    wchar_t exe_path[MAX_PATH];
    if (GetModuleFileNameW(NULL, exe_path, MAX_PATH) == 0) {
        show_error(L"Could not determine install location.");
        if (argv) LocalFree(argv);
        return 1;
    }
    PathRemoveFileSpecW(exe_path);  /* now == INSTALL_ROOT */

    wchar_t py[MAX_PATH], pyw[MAX_PATH], launcher[MAX_PATH], backend_dir[MAX_PATH], crashlog[MAX_PATH];
    path_join(pyw,         MAX_PATH, exe_path, L"python\\pythonw.exe");
    path_join(py,          MAX_PATH, exe_path, L"python\\python.exe");
    path_join(launcher,    MAX_PATH, exe_path, L"backend\\launcher.py");
    path_join(backend_dir, MAX_PATH, exe_path, L"backend");
    path_join(crashlog,    MAX_PATH, exe_path, L"backend\\data\\logs\\launcher_crash.log");

    /* --- Build the URL up front so we can use it in both branches. --- */
    wchar_t url[12 * 1024];
    build_target_url(url, sizeof(url) / sizeof(url[0]), open_file);

    /* --- Single-instance: if launcher already listening, just hand off to browser. --- */
    WSADATA wsa;
    WSAStartup(MAKEWORD(2, 2), &wsa);
    if (port_is_listening(LAUNCHER_PORT)) {
        ShellExecuteW(NULL, L"open", url, NULL, NULL, SW_SHOWNORMAL);
        WSACleanup();
        if (argv) LocalFree(argv);
        return 0;
    }

    /* --- Resolve python.exe — pythonw is preferred (no console). --- */
    const wchar_t *python = pyw;
    if (GetFileAttributesW(pyw) == INVALID_FILE_ATTRIBUTES) {
        python = py;
        if (GetFileAttributesW(py) == INVALID_FILE_ATTRIBUTES) {
            show_error(L"Embedded Python runtime is missing.\n"
                       L"Please re-run the BIG Hat Entertainment installer.");
            WSACleanup();
            if (argv) LocalFree(argv);
            return 1;
        }
    }
    if (GetFileAttributesW(launcher) == INVALID_FILE_ATTRIBUTES) {
        show_error(L"backend\\launcher.py is missing.\n"
                   L"Please re-run the BIG Hat Entertainment installer.");
        WSACleanup();
        if (argv) LocalFree(argv);
        return 1;
    }

    /* --- Spawn launcher with --no-browser so we control browser open. --- */
    wchar_t cmdline[2 * MAX_PATH + 32];
    StringCchPrintfW(cmdline, sizeof(cmdline) / sizeof(cmdline[0]),
                     L"\"%ls\" \"%ls\" --no-browser", python, launcher);

    STARTUPINFOW si;
    ZeroMemory(&si, sizeof(si));
    si.cb = sizeof(si);
    si.dwFlags = STARTF_USESHOWWINDOW;
    si.wShowWindow = SW_HIDE;
    PROCESS_INFORMATION pi;
    ZeroMemory(&pi, sizeof(pi));

    BOOL ok = CreateProcessW(
        python, cmdline,
        NULL, NULL, FALSE,
        CREATE_NO_WINDOW | DETACHED_PROCESS,
        NULL, backend_dir,
        &si, &pi);
    if (!ok) {
        DWORD err = GetLastError();
        wchar_t msg[512];
        StringCchPrintfW(msg, 512,
            L"Failed to start the BIG Hat Entertainment launcher.\n\n"
            L"CreateProcess error 0x%08lX.\n\n"
            L"Please re-run the installer or contact support@bighat.live.",
            err);
        show_error(msg);
        WSACleanup();
        if (argv) LocalFree(argv);
        return 1;
    }

    Sleep(STARTUP_GRACE_MS);

    int success = 0;
    for (int i = 0; i < HEALTHCHECK_SECS; i++) {
        if (port_is_listening(LAUNCHER_PORT)) {
            success = 1;
            break;
        }
        DWORD status = WaitForSingleObject(pi.hProcess, 1000);
        if (status == WAIT_OBJECT_0) {
            /* Child exited before port opened — definite crash. */
            break;
        }
    }

    CloseHandle(pi.hProcess);
    CloseHandle(pi.hThread);
    WSACleanup();
    if (argv) LocalFree(argv);

    if (!success) {
        wchar_t msg[1024];
        if (GetFileAttributesW(crashlog) != INVALID_FILE_ATTRIBUTES) {
            StringCchPrintfW(msg, 1024,
                L"BIG Hat Entertainment didn't start within %d seconds.\n\n"
                L"A crash log was written to:\n%ls\n\n"
                L"Please email that file to support@bighat.live so we can help.",
                HEALTHCHECK_SECS, crashlog);
        } else {
            StringCchPrintfW(msg, 1024,
                L"BIG Hat Entertainment didn't start within %d seconds.\n\n"
                L"No crash log was produced — Python may have failed to start "
                L"(antivirus quarantine, missing files, or permissions).\n\n"
                L"Try running the app once as Administrator, then email "
                L"support@bighat.live if it still doesn't open.",
                HEALTHCHECK_SECS);
        }
        show_error(msg);
        return 1;
    }

    /* --- Open the user's default browser at the target URL. --- */
    ShellExecuteW(NULL, L"open", url, NULL, NULL, SW_SHOWNORMAL);
    return 0;
}
