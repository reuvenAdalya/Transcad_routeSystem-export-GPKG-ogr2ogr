# SPDX-License-Identifier: GPL-3.0-or-later
# Convert a TransCAD route system (Streets.dbd + Bus Routes.rts) to CSV-with-WKT, without TransCAD.
# Reverse-engineered: Streets.dln (Raima line records: ID, pts offset/12, npts, bbox) + Streets.pts (int32 lon/lat *1e6),
# Bus Routes.rtg (routes: link sequence + direction; then per-route-link geometry cache).
# usage: python transcad_export.py <src_dir> <out_dir> [ogr2ogr.exe]
#   e.g. python transcad_export.py "C:\data\transcad_input" "C:\data\output"
#
# DATUM FIX (see github.com/eithanwes/israel_trancsad_fix):
# TransCAD's Israel TM has no datum shift (plain GRS80), so the lon/lat stored in the files are really
# Israel 1993 geographic (EPSG:4141), not WGS84. Read as WGS84 they are ~70-80 m off.
# The CSVs keep the raw TransCAD coordinates; the GeoPackage is built with -s_srs EPSG:4141 -t_srs EPSG:4326,
# which equals the plugin's chain (TransCAD TM -> treat as ITM EPSG:2039 -> WGS84).
import sys, os, struct, csv, math, heapq, subprocess
import numpy as np

SRC, OUT = sys.argv[1], sys.argv[2]
def find_ogr2ogr():
    # ogr2ogr from PATH, else the newest QGIS install under Program Files
    import shutil, glob
    p = shutil.which('ogr2ogr')
    if p: return p
    c = sorted(glob.glob(os.path.join(os.environ.get('ProgramFiles', r'C:\Program Files'), 'QGIS*', 'bin', 'ogr2ogr.exe')))
    if c: return c[-1]
    sys.exit('ogr2ogr not found: install QGIS or pass the path to ogr2ogr.exe as the 3rd argument')
OGR = sys.argv[3] if len(sys.argv) > 3 else find_ogr2ogr()
os.makedirs(OUT, exist_ok=True)
NULL_I, NULL_S, NULL_R = -2147483647, -32767, -1.7976931348623157e308

def read_ffb(base):
    dcb = None
    for ext in ('.DCB', '.dcb'):
        if os.path.exists(base + ext): dcb = base + ext
    binf = [base + e for e in ('.bin', '.BIN') if os.path.exists(base + e)][0]
    lines = open(dcb, encoding='cp1255').read().splitlines()
    reclen = int(lines[1].split(',')[0])
    fields = []
    for ln in lines[2:]:
        if not ln.strip(): continue
        p = next(csv.reader([ln]))
        fields.append((p[0], p[1], int(p[2]) - 1, int(p[3])))
    raw = open(binf, 'rb').read()
    n = len(raw) // reclen
    rows = []
    for i in range(n):
        r = raw[i * reclen:(i + 1) * reclen]
        d = {}
        for name, t, off, w in fields:
            s = r[off:off + w]
            if t == 'I':
                v = struct.unpack('<i', s)[0]; v = None if v == NULL_I else v
            elif t == 'S':
                v = struct.unpack('<h', s)[0]; v = None if v == NULL_S else v
            elif t == 'R':
                v = struct.unpack('<d', s)[0]; v = None if v <= NULL_R or math.isnan(v) else v
            elif t == 'F':
                v = struct.unpack('<f', s)[0]
            else:
                v = s.split(b'\x00')[0].decode('cp1255', 'replace').strip()
            d[name] = v
        rows.append(d)
    return [f[0] for f in fields], rows

def wkt_line(parts):
    parts = [p for p in parts if len(p) >= 2]
    f = lambda a: ','.join('%.6f %.6f' % (x / 1e6, y / 1e6) for x, y in a)
    if not parts: return ''
    if len(parts) == 1: return 'LINESTRING(%s)' % f(parts[0])
    return 'MULTILINESTRING(%s)' % ','.join('(%s)' % f(p) for p in parts)

# ---------- Streets geometry from .dln/.pts ----------
print('streets geometry...')
pts = np.fromfile(os.path.join(SRC, 'Streets.pts'), dtype='<i4')
b = open(os.path.join(SRC, 'Streets.dln'), 'rb').read()
SG = {}
for s in range(4):
    A = np.frombuffer(b[s:s + (len(b) - s) // 4 * 4], dtype='<i4').astype(np.int64)
    k = np.arange(8, len(A) - 8)
    ID, X, n = A[k], A[k + 1], A[k + 2]; x0, y0, x1, y1 = A[k + 3], A[k + 4], A[k + 5], A[k + 6]
    ok = (n >= 2) & (n <= 5000) & (x0 >= 34000000) & (x1 <= 36500000) & (y0 >= 29000000) & (y1 <= 33600000) \
         & (x0 <= x1) & (y0 <= y1) & (X > 0) & (X * 3 + 2 * n <= len(pts)) & (ID > 0)
    k = k[ok]; X = X[ok]; n = n[ok]
    px, py = pts[X * 3], pts[X * 3 + 1]
    ok2 = (px >= x0[ok]) & (px <= x1[ok]) & (py >= y0[ok]) & (py <= y1[ok])
    tpos = 4 * k[ok2] + s - 30
    typ = np.frombuffer(b, dtype=np.uint8)[tpos]
    for lid, xx, nn, t in zip(A[k[ok2]], X[ok2], n[ok2], typ):
        if t == 5: SG[int(lid)] = pts[xx * 3: xx * 3 + 2 * nn].reshape(-1, 2)
print(' links with geometry:', len(SG))

sf, srows = read_ffb(os.path.join(SRC, 'Streets'))
with open(os.path.join(OUT, 'streets.csv'), 'w', newline='', encoding='utf-8') as fo:
    w = csv.writer(fo); w.writerow(['WKT'] + sf)
    for r in srows:
        g = SG.get(r['ID'])
        if g is None: continue
        w.writerow([wkt_line([g])] + [r[f] for f in sf])

# ---------- street graph for filling gaps ----------
node_of = {}; adj = {}
def nid(p):
    p = (int(p[0]), int(p[1]))
    if p not in node_of: node_of[p] = len(node_of)
    return node_of[p]
def seglen(g):
    lat = math.radians(g[0, 1] / 1e6)
    d = np.diff(g.astype(np.float64), axis=0); d[:, 0] *= math.cos(lat)
    return float(np.sqrt((d ** 2).sum(1)).sum()) * 0.111
for lid, g in SG.items():
    a, z = nid(g[0]), nid(g[-1]); L = seglen(g)
    adj.setdefault(a, []).append((z, L, lid, 1)); adj.setdefault(z, []).append((a, L, lid, 0))

def shortest(A, B, limit):
    s, t = node_of.get(A), node_of.get(B)
    if s is None or t is None: return None
    dist = {s: 0.0}; prev = {}; h = [(0.0, s)]
    while h:
        d, u = heapq.heappop(h)
        if u == t: break
        if d > limit: return None
        if d > dist.get(u, 1e18): continue
        for v, L, lid, fw in adj.get(u, ()):
            nd = d + L
            if nd < dist.get(v, 1e18): dist[v] = nd; prev[v] = (u, lid, fw); heapq.heappush(h, (nd, v))
    if t not in prev and s != t: return None
    parts = []; v = t
    while v != s:
        u, lid, fw = prev[v]; g = SG[lid]; parts.append(g if fw else g[::-1]); v = u
    return parts[::-1]

# ---------- routes from .rtg ----------
print('routes...')
rb = open(os.path.join(SRC, 'Bus Routes.rtg'), 'rb').read()
nr = struct.unpack_from('<i', rb, 0x66)[0]
p = 0x6a; routes = []
for _ in range(nr):
    rid, nl = struct.unpack_from('<ii', rb, p)
    nlen = struct.unpack_from('<H', rb, p + 26)[0]
    q = p + 48 + nlen
    L = [struct.unpack_from('<iHH', rb, q + i * 40) for i in range(nl)]
    routes.append((rid, [(lid, d) for lid, u, d in L]))
    p = q + nl * 40
p += 4; RG = {}
while p + 50 <= len(rb):
    lid = struct.unpack_from('<i', rb, p)[0]; n = struct.unpack_from('<i', rb, p + 46)[0]
    if n < 1 or n > 100000: break
    RG[lid] = np.frombuffer(rb, dtype='<i4', count=2 * n, offset=p + 50).reshape(-1, 2); p += 50 + 8 * n
print(' routes', len(routes), 'route-link geometries', len(RG))

def oriented(lid, d):
    g = RG[lid]; return g[::-1] if d == 0 else g

rf, rrows = read_ffb(os.path.join(SRC, 'Bus RoutesR'))
rattr = {r['Route_ID']: r for r in rrows}
extra = ['n_links', 'n_links_no_geom', 'gaps_filled_by_streets', 'gaps_unfilled', 'geom_status']
stats = {'ok': 0, 'filled': 0, 'partial': 0}
with open(os.path.join(OUT, 'routes.csv'), 'w', newline='', encoding='utf-8') as fo:
    w = csv.writer(fo); w.writerow(['WKT'] + rf + extra)
    for rid, L in routes:
        parts = []; cur = []; nomiss = 0; filled = 0; unfilled = 0; i = 0
        while i < len(L):
            lid, d = L[i]
            if lid in RG:
                g = oriented(lid, d)
                if cur and not (cur[-1] == g[0]).all():
                    parts.append(np.array(cur)); cur = []
                cur.extend(map(tuple, g if not cur else g[1:])); i += 1; continue
            j = i
            while j < len(L) and L[j][0] not in RG: j += 1
            nomiss += j - i
            A = tuple(cur[-1]) if cur else None
            B = tuple(oriented(*L[j])[0]) if j < len(L) else None
            path = None
            if A and B:
                dd = math.hypot((A[0] - B[0]) * 0.85, A[1] - B[1]) * 0.111
                path = shortest(A, B, max(3 * dd, 1500) + 200 * (j - i))
            if path:
                filled += 1
                for g in path: cur.extend(map(tuple, g[1:]))
            else:
                unfilled += 1
                if cur: parts.append(np.array(cur)); cur = []
            i = j
        if cur: parts.append(np.array(cur))
        st = 'complete' if nomiss == 0 else ('filled_from_streets' if unfilled == 0 else 'partial')
        stats[{'complete': 'ok', 'filled_from_streets': 'filled', 'partial': 'partial'}[st]] += 1
        a = rattr.get(rid, {})
        w.writerow([wkt_line(parts)] + [a.get(f) for f in rf] + [len(L), nomiss, filled, unfilled, st])
print(' route status', stats)

# ---------- physical stops ----------
pf, prows = read_ffb(os.path.join(SRC, 'Bus RoutesP'))
with open(os.path.join(OUT, 'stops_physical.csv'), 'w', newline='', encoding='utf-8') as fo:
    w = csv.writer(fo); w.writerow(['WKT'] + pf); k = 0
    for r in prows:
        x, y = r.get('LongitudeN'), r.get('LatitudeN')
        if not x or not y: continue
        w.writerow(['POINT(%.6f %.6f)' % (x / 1e6, y / 1e6)] + [r[f] for f in pf]); k += 1
print(' physical stops', k, 'of', len(prows))

# ---------- route stops (stops assigned to routes) ----------
# Bus RoutesS.r0 is a Raima file of 76-byte point records (type 7). Offsets from the record start:
#   0x1E STOP_ID, 0x26 lon, 0x2A lat (int32 *1e6), 0x3A ROUTE_ID, 0x3E LINK_ID (Streets ID the stop sits on),
#   0x42 PASS_COUNT (int16), 0x44 MILEPOST (float32, km along the route), 0x48 PHYSICAL_STOP_ID (Bus RoutesP STOP_ID).
# Checked against a TransCAD shapefile export: ROUTE_ID, PASS_COUNT, MILEPOST and PHYSICAL_S match 100%.
# Bus RoutesS.bin also holds deleted rows (first bytes overwritten); only rows whose STOP_ID is in the .r0 are kept.
print('route stops...')
rb0 = np.fromfile(os.path.join(SRC, 'Bus RoutesS.r0'), dtype=np.uint8)
starts = []
for s in range(4):
    A = np.frombuffer(rb0[s:s + (len(rb0) - s) // 4 * 4].tobytes(), dtype='<i4')
    k = np.where((A[:-1] >= -180000000) & (A[:-1] <= 180000000) & (A[1:] >= -90000000) & (A[1:] <= 90000000) & (A[:-1] != 0))[0]
    st = 4 * k + s - 0x26
    st = st[(st >= 0) & (st + 0x4C <= len(rb0))]
    st = st[(rb0[st] == 7) & (rb0[st + 1] == 0)]
    starts.append(st)
st = np.unique(np.concatenate(starts))
def i32(o): return rb0[o[:, None] + np.arange(4)].copy().view('<i4').ravel()
def i16(o): return rb0[o[:, None] + np.arange(2)].copy().view('<i2').ravel()
def f32(o): return rb0[o[:, None] + np.arange(4)].copy().view('<f4').ravel()
RS = dict(STOP_ID=i32(st + 0x1E), lon=i32(st + 0x26), lat=i32(st + 0x2A), ROUTE_ID=i32(st + 0x3A),
          LINK_ID=i32(st + 0x3E), PASS_COUNT=i16(st + 0x42), MILEPOST=f32(st + 0x44), PHYSICAL_STOP_ID=i32(st + 0x48))
ok = np.isin(RS['ROUTE_ID'], list(rattr.keys()))          # drop false positives: route must exist
RS = {k: v[ok] for k, v in RS.items()}
_, first = np.unique(RS['STOP_ID'], return_index=True)    # one record per stop id
RS = {k: v[np.sort(first)] for k, v in RS.items()}
print(' route stops in .r0:', len(RS['STOP_ID']))

sf_, srows_ = read_ffb(os.path.join(SRC, 'Bus RoutesS'))
ids_ok = set(RS['STOP_ID'].tolist())
sattr = {r['STOP_ID']: r for r in srows_ if r['STOP_ID'] in ids_ok}
print(' stop table rows matched:', len(sattr), 'of', len(srows_), '(the rest are deleted rows)')
sextra = [f for f in sf_ if f != 'STOP_ID']
rkeep = [f for f in ('Route_Name', 'Makat', 'Shilut', 'Direction', 'Alt', 'OpName') if f in rf]

order = np.lexsort((RS['MILEPOST'], RS['ROUTE_ID']))
seq = np.zeros(len(order), int); dist = [None] * len(order)
prev_r = None; n = 0
for pos, i in enumerate(order):
    r = RS['ROUTE_ID'][i]
    n = n + 1 if r == prev_r else 1; prev_r = r; seq[i] = n
    if pos + 1 < len(order) and RS['ROUTE_ID'][order[pos + 1]] == r:
        dist[i] = round(float(RS['MILEPOST'][order[pos + 1]] - RS['MILEPOST'][i]), 3)
with open(os.path.join(OUT, 'route_stops.csv'), 'w', newline='', encoding='utf-8') as fo:
    w = csv.writer(fo)
    w.writerow(['WKT', 'STOP_ID', 'ROUTE_ID', 'SEQ', 'MILEPOST', 'DIST_TO_NEXT', 'PASS_COUNT', 'PHYSICAL_STOP_ID', 'LINK_ID']
               + ['route_' + f for f in rkeep] + sextra)
    for i in order:
        a = sattr.get(int(RS['STOP_ID'][i]), {}); ra = rattr.get(int(RS['ROUTE_ID'][i]), {})
        w.writerow(['POINT(%.6f %.6f)' % (RS['lon'][i] / 1e6, RS['lat'][i] / 1e6), int(RS['STOP_ID'][i]), int(RS['ROUTE_ID'][i]),
                    int(seq[i]), round(float(RS['MILEPOST'][i]), 4), dist[i], int(RS['PASS_COUNT'][i]),
                    int(RS['PHYSICAL_STOP_ID'][i]), int(RS['LINK_ID'][i])]
                   + [ra.get(f) for f in rkeep] + [a.get(f) for f in sextra])

# ---------- GeoPackage (datum-corrected to true WGS84) ----------
gpkg = os.path.join(OUT, 'RS_corrected_WGS84.gpkg')
if os.path.exists(gpkg): os.remove(gpkg)
oo = ['-oo', 'GEOM_POSSIBLE_NAMES=WKT', '-oo', 'KEEP_GEOM_COLUMNS=NO', '-oo', 'AUTODETECT_TYPE=YES',
      '-oo', 'AUTODETECT_SIZE_LIMIT=0', '-s_srs', 'EPSG:4141', '-t_srs', 'EPSG:4326']
for i, (name, gt) in enumerate([('routes', 'MULTILINESTRING'), ('route_stops', 'POINT'), ('stops_physical', 'POINT'), ('streets', 'MULTILINESTRING')]):
    cmd = [OGR] + (['-f', 'GPKG'] if i == 0 else ['-update']) + [gpkg, os.path.join(OUT, name + '.csv'), '-nln', name, '-nlt', gt] + oo
    subprocess.run(cmd, check=True)
print('gpkg:', gpkg)
