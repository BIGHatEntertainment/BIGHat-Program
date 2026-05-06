/*
 * BIG Hat Entertainment — Windows launcher (BIGHat.exe)
 *
 * Replaces the wscript.exe + start_bighat.vbs chain with a real,
 * icon-bearing Win32 GUI executable so:
 *   - Task Manager shows "BIG Hat Entertainment" with the hat icon
 *   - The Start Menu / Desktop shortcuts have a proper app target
 *   - The installer's Finish page launches a polished EXE, not a script
 *
 * Behaviour:
 *   1. Resolve install root from GetModuleFileNameW (we live at
 *      INSTALL_ROOT\BIGHat.exe alongside python\, backend\, packaging\).
 *   2. Spawn `python\pythonw.exe backend\launcher.py` with the working
 *      directory set to backend\ and STARTUPINFO::wShowWindow = SW_HIDE
 *      (and CREATE_NO_WINDOW) so no console flashes.
 *   3. Poll TCP 127.0.0.1:8001 once a second for up to 12 seconds. As
 *      soon as the port accepts a connection, success — exit cleanly.
 *   4. If the spawned process exits before the port opens, that's a
 *      launcher.py crash. Surface a MessageBoxW pointing the user at
 *      backend\data\logs\launcher_crash.log so they have something
 *      concrete to send to support@bighat.live. (launcher.py also
 *      shows its own dialog from Python via ctypes.MessageBoxW — both
 *      paths are belt-and-suspenders.)
 *
 * Build (Linux dev box, MinGW-w64 cross-toolchain):
 *
 *      x86_64-w64-mingw32-windres bighat.rc -O coff -o bighat.res
 *      x86_64-w64-mingw32-gcc -O2 -s -mwindows \
 *          -municode -DUNICODE -D_UNICODE \
 *          bighat.c bighat.res \
 *          -lws2_32 -lshlwapi \
 *          -o BIGHat.exe
 *
 * The build is wrapped by `scripts/build_installer.py` so you don't
 * call it by hand.
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
#include <strsafe.h>
#include <stdio.h>
#include <wchar.h>

#define APP_TITLE        L"BIG Hat Entertainment"
#define LAUNCHER_PORT    8001
#define HEALTHCHECK_SECS 12
#define STARTUP_GRACE_MS 800   /* wait this long before first poll (uvicorn import) */

/* Build a path under the install root: <root>\<suffix>. Caller-owned buffer. */
static void path_join(wchar_t *out, size_t out_len, const wchar_t *root, const wchar_t *suffix) {
    StringCchCopyW(out, out_len, root);
    PathAppendW(out, suffix);
}

/* Try a TCP connect to 127.0.0.1:port. Returns 1 on success, 0 on failure. */
static int port_is_listening(int port) {
    SOCKET s = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (s == INVALID_SOCKET) return 0;
    /* Make the connect non-blocking so a closed port returns fast. */
    u_long one = 1;
    ioctlsocket(s, FIONBIO, &one);

    struct sockaddr_in addr;
    ZeroMemory(&addr, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_port = htons((u_short)port);
    addr.sin_addr.s_addr = htonl(0x7F000001);  /* 127.0.0.1 */

    int rc = connect(s, (struct sockaddr *)&addr, sizeof(addr));
    int connected = 0;
    if (rc == 0) {
        connected = 1;
    } else if (WSAGetLastError() == WSAEWOULDBLOCK) {
        /* Wait up to 500ms for the connect to complete. */
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

/* Show a blocking error MessageBox. */
static void show_error(const wchar_t *msg) {
    MessageBoxW(NULL, msg, APP_TITLE, MB_OK | MB_ICONERROR | MB_SETFOREGROUND);
}

int WINAPI wWinMain(HINSTANCE hInst, HINSTANCE hPrev, LPWSTR lpCmd, int nShow) {
    (void)hInst; (void)hPrev; (void)lpCmd; (void)nShow;

    /* --- Resolve install root from this exe's path. --- */
    wchar_t exe_path[MAX_PATH];
    if (GetModuleFileNameW(NULL, exe_path, MAX_PATH) == 0) {
        show_error(L"Could not determine install location.");
        return 1;
    }
    PathRemoveFileSpecW(exe_path);  /* now == INSTALL_ROOT */

    wchar_t py[MAX_PATH], pyw[MAX_PATH], launcher[MAX_PATH], backend_dir[MAX_PATH], crashlog[MAX_PATH];
    path_join(pyw,         MAX_PATH, exe_path, L"python\\pythonw.exe");
    path_join(py,          MAX_PATH, exe_path, L"python\\python.exe");
    path_join(launcher,    MAX_PATH, exe_path, L"backend\\launcher.py");
    path_join(backend_dir, MAX_PATH, exe_path, L"backend");
    path_join(crashlog,    MAX_PATH, exe_path, L"backend\\data\\logs\\launcher_crash.log");

    /* Prefer pythonw.exe (no console). Fall back to python.exe if missing. */
    const wchar_t *python = pyw;
    if (GetFileAttributesW(pyw) == INVALID_FILE_ATTRIBUTES) {
        python = py;
        if (GetFileAttributesW(py) == INVALID_FILE_ATTRIBUTES) {
            show_error(L"Embedded Python runtime is missing.\n"
                       L"Please re-run the BIG Hat Entertainment installer.");
            return 1;
        }
    }
    if (GetFileAttributesW(launcher) == INVALID_FILE_ATTRIBUTES) {
        show_error(L"backend\\launcher.py is missing.\n"
                   L"Please re-run the BIG Hat Entertainment installer.");
        return 1;
    }

    /* --- Build command line: "<python>" "<launcher>" --- */
    wchar_t cmdline[2 * MAX_PATH + 8];
    StringCchPrintfW(cmdline, sizeof(cmdline) / sizeof(cmdline[0]),
                     L"\"%ls\" \"%ls\"", python, launcher);

    /* --- Spawn launcher.py, hidden, no console window. --- */
    STARTUPINFOW si;
    ZeroMemory(&si, sizeof(si));
    si.cb = sizeof(si);
    si.dwFlags = STARTF_USESHOWWINDOW;
    si.wShowWindow = SW_HIDE;
    PROCESS_INFORMATION pi;
    ZeroMemory(&pi, sizeof(pi));

    BOOL ok = CreateProcessW(
        python,                    /* lpApplicationName            */
        cmdline,                   /* lpCommandLine                */
        NULL, NULL,                /* security                     */
        FALSE,                     /* bInheritHandles              */
        CREATE_NO_WINDOW | DETACHED_PROCESS, /* dwCreationFlags    */
        NULL,                      /* environment (inherit)        */
        backend_dir,               /* lpCurrentDirectory           */
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
        return 1;
    }

    /* --- Wait briefly so uvicorn has time to import. --- */
    Sleep(STARTUP_GRACE_MS);

    /* --- Init winsock for the health-check probe. --- */
    WSADATA wsa;
    WSAStartup(MAKEWORD(2, 2), &wsa);

    /* --- Poll: success if port opens; failure if process exits non-zero. --- */
    int success = 0;
    for (int i = 0; i < HEALTHCHECK_SECS; i++) {
        if (port_is_listening(LAUNCHER_PORT)) {
            success = 1;
            break;
        }
        DWORD status = WaitForSingleObject(pi.hProcess, 1000);
        if (status == WAIT_OBJECT_0) {
            /* Child exited before port opened — definite crash. */
            DWORD code = 1;
            GetExitCodeProcess(pi.hProcess, &code);
            (void)code;
            break;
        }
    }

    WSACleanup();
    CloseHandle(pi.hProcess);
    CloseHandle(pi.hThread);

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
    return 0;
}
