/*
 * Injected only into whitelisted processes. connect() to a public address is
 * completed against the tray's loopback listener, which then opens SOCKS.
 * Every other process keeps the system connect path. This DLL never looks at
 * packets, so a process that was not injected cannot be affected.
 */
#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include <tlhelp32.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#pragma comment(lib, "ws2_32.lib")

#define ACTION_ORIGINAL 0
#define ACTION_REDIRECT 1
#define ACTION_REFUSE 2

#define HOOK_MAP_NAME L"Local\\MaintainAllAppProxyHook"

#pragma pack(push, 1)
typedef struct HookConfig {
    char magic[4];
    uint16_t v4_port;
    uint16_t v6_port;
    uint8_t ipv6_proxy;
    uint8_t pad;
} HookConfig;
#pragma pack(pop)

typedef int(WSAAPI *connect_fn)(SOCKET, const struct sockaddr *, int);
typedef int(WSAAPI *wsaconnect_fn)(
    SOCKET, const struct sockaddr *, int, LPWSABUF, LPWSABUF, LPQOS, LPQOS);
typedef BOOL(WSAAPI *connectex_fn)(
    SOCKET, const struct sockaddr *, int, PVOID, DWORD, LPDWORD, LPOVERLAPPED);
typedef int(WSAAPI *send_fn)(SOCKET, const char *, int, int);
typedef int(WSAAPI *wsasend_fn)(
    SOCKET, LPWSABUF, DWORD, LPDWORD, DWORD, LPWSAOVERLAPPED, LPWSAOVERLAPPED_COMPLETION_ROUTINE);
typedef int(WSAAPI *closesocket_fn)(SOCKET);
typedef BOOL(WINAPI *createprocessw_fn)(
    LPCWSTR, LPWSTR, LPSECURITY_ATTRIBUTES, LPSECURITY_ATTRIBUTES, BOOL, DWORD, LPVOID, LPCWSTR,
    LPSTARTUPINFOW, LPPROCESS_INFORMATION);
typedef BOOL(WINAPI *createprocessa_fn)(
    LPCSTR, LPSTR, LPSECURITY_ATTRIBUTES, LPSECURITY_ATTRIBUTES, BOOL, DWORD, LPVOID, LPCSTR,
    LPSTARTUPINFOA, LPPROCESS_INFORMATION);

static HMODULE g_module;
static volatile LONG g_installed;
static connect_fn g_connect;
static wsaconnect_fn g_wsaconnect;
static connectex_fn g_connectex;
static send_fn g_send;
static wsasend_fn g_wsasend;
static closesocket_fn g_closesocket;
static createprocessw_fn g_createw;
static createprocessa_fn g_createa;
static CRITICAL_SECTION g_slots_lock;
static uint8_t *g_tramp;
static size_t g_tramp_used;

#define SOCK_SLOTS 512
typedef struct SockSlot {
    SOCKET s;
    int off;
    int len;
    uint8_t pre[24];
    int used;
} SockSlot;
static SockSlot g_slots[SOCK_SLOTS];

static int insn_info(const uint8_t *code, int *rip_disp_off);
static int steal_len(const void *target, int minimum);
__declspec(dllexport) DWORD WINAPI HookInstall(LPVOID unused);

static uint32_t read_be32(const uint8_t *p) {
    return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) | ((uint32_t)p[2] << 8) | p[3];
}

static int v4_original(uint32_t host) {
    if ((host & 0xff000000u) == 0x00000000u) return 1;
    if ((host & 0xff000000u) == 0x0a000000u) return 1;
    if ((host & 0xffc00000u) == 0x64400000u) return 1;
    if ((host & 0xff000000u) == 0x7f000000u) return 1;
    if ((host & 0xffff0000u) == 0xa9fe0000u) return 1;
    if ((host & 0xfff00000u) == 0xac100000u) return 1;
    if ((host & 0xffff0000u) == 0xc0a80000u) return 1;
    if ((host & 0xf0000000u) == 0xe0000000u) return 1;
    return 0;
}

static int v6_direct(const uint8_t *b) {
    static const uint8_t loop[16] = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1};
    int i;
    if (memcmp(b, loop, 16) == 0) return 1;
    if (b[0] == 0xfe && (b[1] & 0xc0) == 0x80) return 1;
    if ((b[0] & 0xfe) == 0xfc) return 1;
    if (b[0] == 0xff) return 1;
    for (i = 0; i < 10; i++) {
        if (b[i] != 0) return 0;
    }
    return b[10] == 0xff && b[11] == 0xff;
}

static int classify_v6(const uint8_t *b, int ipv6_proxy);

static int classify_v4(uint32_t host, int ipv6_proxy) {
    (void)ipv6_proxy;
    return v4_original(host) ? ACTION_ORIGINAL : ACTION_REDIRECT;
}

static int classify_v6(const uint8_t *b, int ipv6_proxy) {
    int i;
    if (v6_direct(b)) {
        for (i = 0; i < 10; i++) {
            if (b[i] != 0) return ACTION_ORIGINAL;
        }
        if (b[10] == 0xff && b[11] == 0xff) {
            return classify_v4(read_be32(b + 12), ipv6_proxy);
        }
        return ACTION_ORIGINAL;
    }
    return ipv6_proxy ? ACTION_REDIRECT : ACTION_REFUSE;
}

__declspec(dllexport) int hook_action_ip(const char *ip, int ipv6_proxy) {
    struct in_addr v4;
    struct in6_addr v6;
    if (ip == NULL) return ACTION_ORIGINAL;
    if (inet_pton(AF_INET, ip, &v4) == 1) return classify_v4(ntohl(v4.s_addr), ipv6_proxy);
    if (inet_pton(AF_INET6, ip, &v6) == 1) return classify_v6(v6.s6_addr, ipv6_proxy);
    return ACTION_ORIGINAL;
}

static int encode_addr(int family, const void *addr, int port, uint8_t *out, int cap) {
    const uint8_t *b = (const uint8_t *)addr;
    if (family == AF_INET) {
        if (cap < 11) return -1;
        memcpy(out, "MAC1", 4);
        out[4] = 4;
        memcpy(out + 5, b, 4);
        out[9] = (uint8_t)((port >> 8) & 0xff);
        out[10] = (uint8_t)(port & 0xff);
        return 11;
    }
    if (v6_direct(b) && b[10] == 0xff && b[11] == 0xff) {
        return encode_addr(AF_INET, b + 12, port, out, cap);
    }
    if (cap < 23) return -1;
    memcpy(out, "MAC1", 4);
    out[4] = 6;
    memcpy(out + 5, b, 16);
    out[21] = (uint8_t)((port >> 8) & 0xff);
    out[22] = (uint8_t)(port & 0xff);
    return 23;
}

__declspec(dllexport) int hook_encode_preamble(const char *ip, int port, unsigned char *out, int cap) {
    struct in_addr v4;
    struct in6_addr v6;
    if (ip == NULL || out == NULL || port <= 0 || port > 65535) return -1;
    if (inet_pton(AF_INET, ip, &v4) == 1) return encode_addr(AF_INET, &v4.s_addr, port, out, cap);
    if (inet_pton(AF_INET6, ip, &v6) == 1) return encode_addr(AF_INET6, v6.s6_addr, port, out, cap);
    return -1;
}

static int encode_sockaddr(const struct sockaddr *name, int namelen, uint8_t *out, int cap) {
    if (name->sa_family == AF_INET && namelen >= (int)sizeof(struct sockaddr_in)) {
        const struct sockaddr_in *in = (const struct sockaddr_in *)name;
        return encode_addr(AF_INET, &in->sin_addr.s_addr, ntohs(in->sin_port), out, cap);
    }
    if (name->sa_family == AF_INET6 && namelen >= (int)sizeof(struct sockaddr_in6)) {
        const struct sockaddr_in6 *in6 = (const struct sockaddr_in6 *)name;
        return encode_addr(AF_INET6, in6->sin6_addr.s6_addr, ntohs(in6->sin6_port), out, cap);
    }
    return -1;
}

static int classify_sockaddr(const struct sockaddr *name, int namelen, int ipv6_proxy) {
    if (name->sa_family == AF_INET && namelen >= (int)sizeof(struct sockaddr_in)) {
        const struct sockaddr_in *in = (const struct sockaddr_in *)name;
        return classify_v4(ntohl(in->sin_addr.s_addr), ipv6_proxy);
    }
    if (name->sa_family == AF_INET6 && namelen >= (int)sizeof(struct sockaddr_in6)) {
        const struct sockaddr_in6 *in6 = (const struct sockaddr_in6 *)name;
        return classify_v6(in6->sin6_addr.s6_addr, ipv6_proxy);
    }
    return ACTION_ORIGINAL;
}

static int read_config(HookConfig *cfg) {
    HANDLE map;
    void *view;
    int ok = 0;
    map = OpenFileMappingW(FILE_MAP_READ, FALSE, HOOK_MAP_NAME);
    if (map == NULL) return 0;
    view = MapViewOfFile(map, FILE_MAP_READ, 0, 0, sizeof(*cfg));
    if (view != NULL) {
        memcpy(cfg, view, sizeof(*cfg));
        UnmapViewOfFile(view);
        ok = memcmp(cfg->magic, "MAC1", 4) == 0 && cfg->v4_port != 0;
    }
    CloseHandle(map);
    return ok;
}

static int send_all(SOCKET s, const uint8_t *buf, int len) {
    int off = 0;
    while (off < len) {
        int n = g_send(s, (const char *)buf + off, len - off, 0);
        if (n == 0 || (n < 0 && WSAGetLastError() != WSAEWOULDBLOCK)) return -1;
        if (n < 0) return off;
        off += n;
    }
    return off;
}

static SockSlot *slot_find(SOCKET s) {
    int i;
    for (i = 0; i < SOCK_SLOTS; i++) {
        if (g_slots[i].used && g_slots[i].s == s) return &g_slots[i];
    }
    return NULL;
}

static void slot_drop(SOCKET s) {
    SockSlot *slot;
    EnterCriticalSection(&g_slots_lock);
    slot = slot_find(s);
    if (slot != NULL) slot->used = 0;
    LeaveCriticalSection(&g_slots_lock);
}

static void slot_store(SOCKET s, const uint8_t *pre, int len, int off) {
    int i;
    SockSlot *slot;
    if (len <= 0 || len > (int)sizeof(g_slots[0].pre)) return;
    EnterCriticalSection(&g_slots_lock);
    slot = slot_find(s);
    if (slot == NULL) {
        for (i = 0; i < SOCK_SLOTS; i++) {
            if (!g_slots[i].used) {
                slot = &g_slots[i];
                break;
            }
        }
    }
    if (slot != NULL) {
        slot->used = 1;
        slot->s = s;
        slot->off = off;
        slot->len = len;
        memcpy(slot->pre, pre, (size_t)len);
    }
    LeaveCriticalSection(&g_slots_lock);
}

static void flush_preamble(SOCKET s) {
    uint8_t pre[24];
    int off;
    int len;
    EnterCriticalSection(&g_slots_lock);
    {
        SockSlot *slot = slot_find(s);
        if (slot == NULL) {
            LeaveCriticalSection(&g_slots_lock);
            return;
        }
        off = slot->off;
        len = slot->len;
        memcpy(pre, slot->pre, (size_t)len);
    }
    LeaveCriticalSection(&g_slots_lock);
    while (off < len) {
        int n = g_send(s, (const char *)pre + off, len - off, 0);
        if (n <= 0) {
            slot_store(s, pre, len, off);
            return;
        }
        off += n;
    }
    slot_drop(s);
}

static int redirect_sync(SOCKET s, const struct sockaddr *name, int namelen, connect_fn real) {
    HookConfig cfg;
    uint8_t pre[24];
    int action;
    int n;
    int sent;
    if (!read_config(&cfg)) return real(s, name, namelen);
    action = classify_sockaddr(name, namelen, cfg.ipv6_proxy);
    if (action == ACTION_ORIGINAL) return real(s, name, namelen);
    if (action == ACTION_REFUSE) {
        WSASetLastError(WSAECONNREFUSED);
        return SOCKET_ERROR;
    }
    n = encode_sockaddr(name, namelen, pre, (int)sizeof(pre));
    if (n <= 0) return real(s, name, namelen);
    {
        int pending = 0;
        int rc;
        if (name->sa_family == AF_INET6) {
            struct sockaddr_in6 local;
            if (cfg.v6_port == 0) return real(s, name, namelen);
            memset(&local, 0, sizeof(local));
            local.sin6_family = AF_INET6;
            local.sin6_addr = in6addr_loopback;
            local.sin6_port = htons(cfg.v6_port);
            rc = real(s, (struct sockaddr *)&local, (int)sizeof(local));
        } else {
            struct sockaddr_in local;
            memset(&local, 0, sizeof(local));
            local.sin_family = AF_INET;
            local.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
            local.sin_port = htons(cfg.v4_port);
            rc = real(s, (struct sockaddr *)&local, (int)sizeof(local));
        }
        if (rc != 0) {
            if (WSAGetLastError() != WSAEWOULDBLOCK) return SOCKET_ERROR;
            pending = 1;
        }
        sent = pending ? 0 : send_all(s, pre, n);
        if (!pending && sent < 0) {
            WSASetLastError(WSAECONNRESET);
            return SOCKET_ERROR;
        }
        if (pending || sent < n) slot_store(s, pre, n, sent);
        if (pending) {
            WSASetLastError(WSAEWOULDBLOCK);
            return SOCKET_ERROR;
        }
    }
    return 0;
}

static int WSAAPI detour_connect(SOCKET s, const struct sockaddr *name, int namelen) {
    if (name == NULL || g_connect == NULL) return SOCKET_ERROR;
    return redirect_sync(s, name, namelen, g_connect);
}

static int WSAAPI detour_wsaconnect(
    SOCKET s, const struct sockaddr *name, int namelen, LPWSABUF caller, LPWSABUF callee, LPQOS sqos,
    LPQOS gqos) {
    (void)caller;
    (void)callee;
    (void)sqos;
    (void)gqos;
    if (name == NULL || g_connect == NULL) return SOCKET_ERROR;
    return redirect_sync(s, name, namelen, g_connect);
}

static BOOL WSAAPI detour_connectex(
    SOCKET s, const struct sockaddr *name, int namelen, PVOID buffer, DWORD length, LPDWORD sent,
    LPOVERLAPPED overlapped) {
    HookConfig cfg;
    uint8_t pre[24];
    int action;
    int n;
    struct sockaddr_storage local;
    int local_len;
    if (g_connectex == NULL || name == NULL) return FALSE;
    if (!read_config(&cfg)) return g_connectex(s, name, namelen, buffer, length, sent, overlapped);
    action = classify_sockaddr(name, namelen, cfg.ipv6_proxy);
    if (action == ACTION_ORIGINAL) return g_connectex(s, name, namelen, buffer, length, sent, overlapped);
    if (action == ACTION_REFUSE) {
        WSASetLastError(WSAECONNREFUSED);
        return FALSE;
    }
    n = encode_sockaddr(name, namelen, pre, (int)sizeof(pre));
    if (n <= 0) return g_connectex(s, name, namelen, buffer, length, sent, overlapped);
    memset(&local, 0, sizeof(local));
    if (name->sa_family == AF_INET6) {
        struct sockaddr_in6 *in6 = (struct sockaddr_in6 *)&local;
        if (cfg.v6_port == 0) return g_connectex(s, name, namelen, buffer, length, sent, overlapped);
        in6->sin6_family = AF_INET6;
        in6->sin6_addr = in6addr_loopback;
        in6->sin6_port = htons(cfg.v6_port);
        local_len = (int)sizeof(*in6);
    } else {
        struct sockaddr_in *in = (struct sockaddr_in *)&local;
        in->sin_family = AF_INET;
        in->sin_addr.s_addr = htonl(INADDR_LOOPBACK);
        in->sin_port = htons(cfg.v4_port);
        local_len = (int)sizeof(*in);
    }
    if (buffer != NULL && length > 0) {
        uint8_t *combined = (uint8_t *)HeapAlloc(GetProcessHeap(), 0, (SIZE_T)n + length);
        if (combined == NULL) {
            WSASetLastError(WSAENOBUFS);
            return FALSE;
        }
        memcpy(combined, pre, (size_t)n);
        memcpy(combined + n, buffer, length);
        return g_connectex(s, (struct sockaddr *)&local, local_len, combined, (DWORD)n + length, sent, overlapped);
    }
    slot_store(s, pre, n, 0);
    return g_connectex(s, (struct sockaddr *)&local, local_len, NULL, 0, sent, overlapped);
}

static int WSAAPI detour_send(SOCKET s, const char *buf, int len, int flags) {
    flush_preamble(s);
    return g_send(s, buf, len, flags);
}

static int WSAAPI detour_wsasend(
    SOCKET s, LPWSABUF bufs, DWORD count, LPDWORD sent, DWORD flags, LPWSAOVERLAPPED overlapped,
    LPWSAOVERLAPPED_COMPLETION_ROUTINE routine) {
    flush_preamble(s);
    return g_wsasend(s, bufs, count, sent, flags, overlapped, routine);
}

static int WSAAPI detour_close(SOCKET s) {
    slot_drop(s);
    return g_closesocket(s);
}

static int remote_library(HANDLE process, const wchar_t *dll) {
    SIZE_T bytes = (wcslen(dll) + 1) * sizeof(wchar_t);
    void *remote;
    HANDLE thread;
    DWORD code = 0;
    HMODULE kernel = GetModuleHandleW(L"kernel32.dll");
    FARPROC load = GetProcAddress(kernel, "LoadLibraryW");
    remote = VirtualAllocEx(process, NULL, bytes, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    if (remote == NULL || load == NULL) return 0;
    if (!WriteProcessMemory(process, remote, dll, bytes, NULL)) {
        VirtualFreeEx(process, remote, 0, MEM_RELEASE);
        return 0;
    }
    thread = CreateRemoteThread(process, NULL, 0, (LPTHREAD_START_ROUTINE)load, remote, 0, NULL);
    if (thread == NULL) {
        VirtualFreeEx(process, remote, 0, MEM_RELEASE);
        return 0;
    }
    WaitForSingleObject(thread, 10000);
    GetExitCodeThread(thread, &code);
    CloseHandle(thread);
    VirtualFreeEx(process, remote, 0, MEM_RELEASE);
    return code != 0;
}

static uintptr_t module_base(DWORD pid) {
    HANDLE snap;
    MODULEENTRY32W entry;
    uintptr_t base = 0;
    snap = CreateToolhelp32Snapshot(TH32CS_SNAPMODULE, pid);
    if (snap == INVALID_HANDLE_VALUE) return 0;
    entry.dwSize = sizeof(entry);
    if (Module32FirstW(snap, &entry)) {
        do {
            if (_wcsicmp(entry.szModule, L"connect_hook.dll") == 0) {
                base = (uintptr_t)entry.modBaseAddr;
                break;
            }
        } while (Module32NextW(snap, &entry));
    }
    CloseHandle(snap);
    return base;
}

static void inject_process(HANDLE process, DWORD pid) {
    wchar_t path[MAX_PATH];
    BOOL wow = FALSE;
    uintptr_t base;
    uintptr_t remote_fn;
    HANDLE thread;
    if (process == NULL || pid == 0) return;
    if (IsWow64Process(process, &wow) && wow) return;
    if (GetModuleFileNameW(g_module, path, MAX_PATH) == 0) return;
    if (!remote_library(process, path)) return;
    base = module_base(pid);
    if (base == 0 || g_module == NULL) return;
    remote_fn = base + ((uintptr_t)HookInstall - (uintptr_t)g_module);
    thread = CreateRemoteThread(process, NULL, 0, (LPTHREAD_START_ROUTINE)remote_fn, NULL, 0, NULL);
    if (thread == NULL) return;
    WaitForSingleObject(thread, 10000);
    CloseHandle(thread);
}

static BOOL WINAPI detour_createw(
    LPCWSTR app, LPWSTR cmd, LPSECURITY_ATTRIBUTES proc_attr, LPSECURITY_ATTRIBUTES thread_attr, BOOL inherit,
    DWORD flags, LPVOID env, LPCWSTR dir, LPSTARTUPINFOW start, LPPROCESS_INFORMATION info) {
    DWORD merged = flags | CREATE_SUSPENDED;
    BOOL ok = g_createw(app, cmd, proc_attr, thread_attr, inherit, merged, env, dir, start, info);
    if (!ok) return FALSE;
    inject_process(info->hProcess, info->dwProcessId);
    if ((flags & CREATE_SUSPENDED) == 0) ResumeThread(info->hThread);
    return TRUE;
}

static BOOL WINAPI detour_createa(
    LPCSTR app, LPSTR cmd, LPSECURITY_ATTRIBUTES proc_attr, LPSECURITY_ATTRIBUTES thread_attr, BOOL inherit,
    DWORD flags, LPVOID env, LPCSTR dir, LPSTARTUPINFOA start, LPPROCESS_INFORMATION info) {
    DWORD merged = flags | CREATE_SUSPENDED;
    BOOL ok = g_createa(app, cmd, proc_attr, thread_attr, inherit, merged, env, dir, start, info);
    if (!ok) return FALSE;
    inject_process(info->hProcess, info->dwProcessId);
    if ((flags & CREATE_SUSPENDED) == 0) ResumeThread(info->hThread);
    return TRUE;
}

static int modrm_extra(const uint8_t *modrm, int *rip_disp) {
    int mod = modrm[0] >> 6;
    int rm = modrm[0] & 7;
    int len = 1;
    int sib = mod != 3 && rm == 4;
    if (sib) len += 1;
    if (mod == 1) len += 1;
    else if (mod == 2) len += 4;
    else if (mod == 0 && !sib && rm == 5) {
        *rip_disp = 1;
        len += 4;
    } else if (mod == 0 && sib && (modrm[1] & 7) == 5) {
        len += 4;
    }
    return len;
}

static int insn_info(const uint8_t *code, int *rip_disp_off) {
    int i = 0;
    uint8_t op;
    int extra;
    int rip_at = 0;
    *rip_disp_off = -1;
    for (;;) {
        uint8_t b = code[i];
        if ((b >= 0x40 && b <= 0x4f) || b == 0x66 || b == 0x67 || b == 0xf0 || b == 0xf2 || b == 0xf3 ||
            b == 0x26 || b == 0x2e || b == 0x36 || b == 0x3e || b == 0x64 || b == 0x65) {
            i++;
            if (i > 8) return 0;
            continue;
        }
        break;
    }
    op = code[i];
    if (op >= 0x50 && op <= 0x5f) return i + 1;
    if (op == 0x90) return i + 1;
    if (op == 0xc3 || op == 0xe8 || op == 0xe9 || op == 0xeb || op == 0x0f) return 0;
    if (op == 0x89 || op == 0x8b || op == 0x8d || op == 0x83 || op == 0x81 || op == 0x88 || op == 0x8a ||
        op == 0x03 || op == 0x2b || op == 0x33 || op == 0x85 || op == 0xc7) {
        extra = modrm_extra(code + i + 1, &rip_at);
        if (rip_at) *rip_disp_off = i + 1 + rip_at;
        if (op == 0x83) extra += 1;
        if (op == 0x81 || op == 0xc7) extra += 4;
        return i + 1 + extra;
    }
    return 0;
}

static int steal_len(const void *target, int minimum) {
    const uint8_t *code = (const uint8_t *)target;
    int total = 0;
    int rel = 0;
    if (target == NULL) return 0;
    while (total < minimum) {
        int n = insn_info(code + total, &rel);
        if (n <= 0) return 0;
        total += n;
        if (total > 32) return 0;
    }
    return total;
}

__declspec(dllexport) int hook_prologue_ok(void) {
    HMODULE ws;
    HMODULE kernel;
    WSADATA data;
    SOCKET sock;
    GUID connectex_id = {0x25a207b9, 0xddf3, 0x4660, {0x8e, 0xe9, 0x76, 0xe5, 0x8c, 0x74, 0x06, 0x3e}};
    DWORD ioctl = 0xC8000006;
    void *connectex = NULL;
    DWORD got = 0;
    int mask = 0;
    ws = GetModuleHandleW(L"ws2_32.dll");
    if (ws == NULL) ws = LoadLibraryW(L"ws2_32.dll");
    kernel = GetModuleHandleW(L"kernel32.dll");
    if (steal_len(GetProcAddress(ws, "connect"), 14) >= 14) mask |= 1;
    if (steal_len(GetProcAddress(ws, "WSAConnect"), 14) >= 14) mask |= 2;
    if (steal_len(GetProcAddress(ws, "send"), 14) >= 14) mask |= 4;
    if (steal_len(GetProcAddress(ws, "WSASend"), 14) >= 14) mask |= 8;
    if (steal_len(GetProcAddress(ws, "closesocket"), 14) >= 14) mask |= 16;
    if (steal_len(GetProcAddress(kernel, "CreateProcessW"), 14) >= 14) mask |= 32;
    if (steal_len(GetProcAddress(kernel, "CreateProcessA"), 14) >= 14) mask |= 64;
    if (WSAStartup(MAKEWORD(2, 2), &data) == 0) {
        sock = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
        if (sock != INVALID_SOCKET) {
            if (WSAIoctl(
                    sock, ioctl, &connectex_id, sizeof(connectex_id), &connectex, sizeof(connectex), &got, NULL,
                    NULL) == 0 &&
                steal_len(connectex, 14) >= 14) {
                mask |= 128;
            }
            closesocket(sock);
        }
    }
    return mask;
}

static uint8_t *tramp_alloc(size_t bytes, const void *near_to) {
    size_t aligned;
    if (g_tramp == NULL) {
        uintptr_t origin = ((uintptr_t)near_to) & ~(uintptr_t)65535;
        int step;
        for (step = 1; step < 2048 && g_tramp == NULL; step++) {
            uintptr_t down = origin - (uintptr_t)step * 65536;
            g_tramp = (uint8_t *)VirtualAlloc(
                (void *)down, 65536, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
            if (g_tramp != NULL) break;
            g_tramp = (uint8_t *)VirtualAlloc(
                (void *)(origin + (uintptr_t)step * 65536), 65536, MEM_COMMIT | MEM_RESERVE,
                PAGE_EXECUTE_READWRITE);
        }
        if (g_tramp == NULL) {
            g_tramp = (uint8_t *)VirtualAlloc(NULL, 65536, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
        }
        g_tramp_used = 0;
    }
    if (g_tramp == NULL) return NULL;
    aligned = (bytes + 15u) & ~15u;
    if (g_tramp_used + aligned > 65536) return NULL;
    g_tramp_used += aligned;
    return g_tramp + (g_tramp_used - aligned);
}

static void write_jmp(uint8_t *at, const void *dest) {
    at[0] = 0xff;
    at[1] = 0x25;
    memset(at + 2, 0, 4);
    memcpy(at + 6, &dest, sizeof(dest));
}

static int relocate_rip(uint8_t *tramp, const uint8_t *target, int stolen) {
    int off = 0;
    while (off < stolen) {
        int disp_off = -1;
        int n = insn_info(target + off, &disp_off);
        int32_t disp;
        intptr_t delta;
        if (n <= 0 || off + n > stolen) return 0;
        if (disp_off >= 0) {
            memcpy(&disp, tramp + off + disp_off, 4);
            delta = (intptr_t)(tramp + off + n) - (intptr_t)(target + off + n);
            if (delta > 2147483647LL || delta < -2147483648LL) return 0;
            disp -= (int32_t)delta;
            memcpy(tramp + off + disp_off, &disp, 4);
        }
        off += n;
    }
    return 1;
}

static int install_hook(void *target, void *detour, void **original) {
    int stolen;
    uint8_t *tramp;
    DWORD old = 0;
    if (target == NULL || detour == NULL || original == NULL) return 0;
    stolen = steal_len(target, 14);
    if (stolen < 14) return 0;
    tramp = tramp_alloc((size_t)stolen + 16, target);
    if (tramp == NULL) return 0;
    memcpy(tramp, target, (size_t)stolen);
    if (!relocate_rip(tramp, (const uint8_t *)target, stolen)) return 0;
    write_jmp(tramp + stolen, (uint8_t *)target + stolen);
    if (!VirtualProtect(target, (SIZE_T)stolen, PAGE_EXECUTE_READWRITE, &old)) return 0;
    write_jmp((uint8_t *)target, detour);
    if (stolen > 14) memset((uint8_t *)target + 14, 0x90, (size_t)stolen - 14);
    VirtualProtect(target, (SIZE_T)stolen, old, &old);
    FlushInstructionCache(GetCurrentProcess(), target, (SIZE_T)stolen);
    *original = tramp;
    return 1;
}

static void suspend_others(HANDLE *threads, int *count) {
    HANDLE snap;
    THREADENTRY32 entry;
    DWORD self = GetCurrentThreadId();
    DWORD pid = GetCurrentProcessId();
    *count = 0;
    snap = CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0);
    if (snap == INVALID_HANDLE_VALUE) return;
    entry.dwSize = sizeof(entry);
    if (Thread32First(snap, &entry)) {
        do {
            HANDLE thread;
            if (entry.th32OwnerProcessID != pid || entry.th32ThreadID == self) continue;
            thread = OpenThread(THREAD_SUSPEND_RESUME, FALSE, entry.th32ThreadID);
            if (thread == NULL) continue;
            if (SuspendThread(thread) == (DWORD)-1) {
                CloseHandle(thread);
                continue;
            }
            if (*count < 256) threads[(*count)++] = thread;
            else CloseHandle(thread);
        } while (Thread32Next(snap, &entry));
    }
    CloseHandle(snap);
}

static void resume_others(HANDLE *threads, int count) {
    int i;
    for (i = 0; i < count; i++) {
        ResumeThread(threads[i]);
        CloseHandle(threads[i]);
    }
}

__declspec(dllexport) DWORD WINAPI HookInstall(LPVOID unused) {
    HMODULE ws;
    HMODULE kernel;
    WSADATA data;
    SOCKET sock;
    GUID connectex_id = {0x25a207b9, 0xddf3, 0x4660, {0x8e, 0xe9, 0x76, 0xe5, 0x8c, 0x74, 0x06, 0x3e}};
    DWORD ioctl = 0xC8000006;
    void *connectex = NULL;
    DWORD got = 0;
    HANDLE paused[256];
    int paused_count = 0;
    (void)unused;
    if (InterlockedCompareExchange(&g_installed, 1, 0) != 0) return 0;
    InitializeCriticalSection(&g_slots_lock);
    WSAStartup(MAKEWORD(2, 2), &data);
    ws = GetModuleHandleW(L"ws2_32.dll");
    if (ws == NULL) ws = LoadLibraryW(L"ws2_32.dll");
    kernel = GetModuleHandleW(L"kernel32.dll");
    sock = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (sock != INVALID_SOCKET) {
        WSAIoctl(sock, ioctl, &connectex_id, sizeof(connectex_id), &connectex, sizeof(connectex), &got, NULL, NULL);
        closesocket(sock);
    }
    suspend_others(paused, &paused_count);
    install_hook(GetProcAddress(ws, "send"), (void *)detour_send, (void **)&g_send);
    install_hook(GetProcAddress(ws, "WSASend"), (void *)detour_wsasend, (void **)&g_wsasend);
    install_hook(GetProcAddress(ws, "closesocket"), (void *)detour_close, (void **)&g_closesocket);
    if (g_send != NULL) {
        install_hook(GetProcAddress(ws, "connect"), (void *)detour_connect, (void **)&g_connect);
        install_hook(GetProcAddress(ws, "WSAConnect"), (void *)detour_wsaconnect, (void **)&g_wsaconnect);
        install_hook(connectex, (void *)detour_connectex, (void **)&g_connectex);
    }
    install_hook(GetProcAddress(kernel, "CreateProcessW"), (void *)detour_createw, (void **)&g_createw);
    install_hook(GetProcAddress(kernel, "CreateProcessA"), (void *)detour_createa, (void **)&g_createa);
    resume_others(paused, paused_count);
    return 0;
}

BOOL WINAPI DllMain(HINSTANCE module, DWORD reason, LPVOID reserved) {
    (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) {
        g_module = module;
        DisableThreadLibraryCalls(module);
    }
    return TRUE;
}
