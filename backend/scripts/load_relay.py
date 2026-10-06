"""Load test for the QR relay (alpha.84). RUN ONLY AGAINST A LOCAL TEST SERVER, never api.bighat.live.

Simulates N venues. Each venue's PC opens a karaoke night and polls for requests; phones send requests.
Needs a license the server accepts: the test server is started by scripts/load_relay.sh with one known license.

usage: python3 scripts/load_relay.py <base_url> <venues> <seconds> <poll_seconds> <phones_per_venue>
"""
import asyncio, random, statistics, sys, time
import httpx

import os
BASE, VENUES, SECONDS, POLL, PHONES = sys.argv[1], int(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4]), int(sys.argv[5])
FIRST = int(os.environ.get('FIRST_VENUE', '0'))   # lets several processes each drive a slice of the venues
assert "bighat.live" not in BASE, "refusing to load test the live site"
def key_for(i): return "BHE-%04X-%04X-%04X-%04X" % (i // 65536, i % 65536, 0xABCD, 0x1234)   # one license per venue, like real customers
lat, errs, codes = [], 0, {}
slow = {}       # url kind -> list of slow latencies (ms)


async def timed(c, method, url, **kw):
    global errs
    t = time.perf_counter()
    try:
        r = await c.request(method, BASE + url, **kw)
        ms = (time.perf_counter() - t) * 1000
        lat.append(ms)
        if ms > 1000:
            slow.setdefault(url.split('/')[-1] if 'sessions' not in url else ('pull' if url.endswith('/pull') else 'sessions'), []).append(ms)
        codes[r.status_code] = codes.get(r.status_code, 0) + 1
        return r
    except Exception:
        errs += 1


async def venue(i, c, end):
    hw = f"hw-{i}"; KEY = key_for(i)
    r = await timed(c, "POST", "/api/relay/karaoke/sessions", json={"license_key": KEY, "hwid": hw, "venue": f"Venue {i}"})
    if not r or r.status_code != 200:
        return
    sid = r.json()["session"]

    async def pc():
        while time.time() < end:
            await timed(c, "POST", f"/api/relay/karaoke/sessions/{sid}/pull", json={"license_key": KEY, "hwid": hw})
            await asyncio.sleep(POLL * random.uniform(0.9, 1.1))

    async def phone(j):
        await asyncio.sleep(random.uniform(0, 5))
        n = 0
        while time.time() < end:
            await timed(c, "POST", f"/api/relay/karaoke/{sid}/request",
                        json={"singer_name": f"S{j}", "song_title": f"Song {n}"}, headers={"X-Forwarded-For": f"10.{i%250}.{j}.{n%250}"})
            n += 1
            await asyncio.sleep(random.uniform(15, 40))

    await asyncio.gather(pc(), *[phone(j) for j in range(PHONES)])


async def main():
    end = time.time() + SECONDS
    limits = httpx.Limits(max_connections=400, max_keepalive_connections=200)
    async with httpx.AsyncClient(timeout=30, limits=limits) as c:
        await asyncio.gather(*[venue(i, c, end) for i in range(FIRST, FIRST + VENUES)])
    n = len(lat)
    if not n:
        print("no successful calls"); return
    lat.sort()
    print(f"venues={VENUES} poll={POLL}s phones/venue={PHONES} duration={SECONDS:.0f}s")
    print(f"calls={n}  rate={n/SECONDS:.0f}/s  errors={errs}  status={codes}")
    print("slow (>1s) by call:", {k: len(v) for k, v in slow.items()}, " first-10s calls:", sum(1 for _ in lat[:0]))
    print(f"latency ms: p50={lat[n//2]:.0f}  p95={lat[int(n*.95)]:.0f}  p99={lat[int(n*.99)]:.0f}  max={lat[-1]:.0f}")

asyncio.run(main())
