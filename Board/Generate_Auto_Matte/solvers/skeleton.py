import math
import numpy as np

# ---------------------------------------------------------------------------
# Skeleton-based line cleanup (dependency-free)
#
# Instead of clustering *strokes* (which cannot tell a crossing tick from a real
# line and always leaves strays), this works on the *ink*: rasterise every
# selected stroke into a mask, thin it to a 1px centreline (Zhang-Suen), trace
# continuous lines through the junctions and prune the short spurs (the ticks).
# The result unifies overlapping scribbles into one clean line automatically,
# with almost no parameters. Pure numpy -- Blender already ships it.
# ---------------------------------------------------------------------------


def _rasterize(polylines, minx, miny, scale, margin, H, W, dilation_px):
    # Draw thin (1px) polylines with vectorised fancy indexing...
    thin = np.zeros((H, W), np.uint8)
    for p in polylines:
        arr = np.asarray(p, dtype=float)
        cols = margin + (arr[:, 0] - minx) * scale
        rows = margin + (arr[:, 1] - miny) * scale
        for k in range(len(arr) - 1):
            n = int(max(abs(cols[k + 1] - cols[k]), abs(rows[k + 1] - rows[k]))) + 1
            cc = np.clip(np.linspace(cols[k], cols[k + 1], n).astype(int), 0, W - 1)
            rr = np.clip(np.linspace(rows[k], rows[k + 1], n).astype(int), 0, H - 1)
            thin[rr, cc] = 1
    # ...then dilate the whole mask at once with roll-OR (margin keeps it off the edges).
    r = max(1, int(round(dilation_px)))
    oy, ox = np.mgrid[-r:r + 1, -r:r + 1]
    doff = np.argwhere(ox * ox + oy * oy <= r * r) - r
    img = thin.copy()
    for dr, dc in doff:
        img |= np.roll(np.roll(thin, int(dr), 0), int(dc), 1)
    img[0, :] = img[-1, :] = img[:, 0] = img[:, -1] = 0
    return img


def _fill_holes(img, max_area_frac):
    """Fill only the SMALL interior holes of the ink mask.

    Two diverging scribbles of one line enclose a small gap; left alone, thinning
    keeps a loop around it. Filling that hole makes the line a solid blob -> one
    centreline. But large enclosed regions (the space between neighbouring lines,
    e.g. between fronds) must stay open, or the lines would merge -- so holes above
    max_area_frac of the image are left untouched. Pure numpy: flood the background
    from the border, then BFS-label the unreached holes and fill the small ones."""
    H, W = img.shape
    bg = (img == 0)
    reach = np.zeros_like(bg)
    reach[0, :] = bg[0, :]; reach[-1, :] = bg[-1, :]
    reach[:, 0] = bg[:, 0]; reach[:, -1] = bg[:, -1]
    while True:
        grown = reach.copy()
        grown[1:, :] |= reach[:-1, :]
        grown[:-1, :] |= reach[1:, :]
        grown[:, 1:] |= reach[:, :-1]
        grown[:, :-1] |= reach[:, 1:]
        grown &= bg
        if grown.sum() == reach.sum():
            break
        reach = grown

    holes = set(map(tuple, np.argwhere(bg & ~reach)))
    max_area = max_area_frac * H * W
    out = img.copy()
    seen = set()
    for hp in holes:
        if hp in seen:
            continue
        comp = []; stack = [hp]; seen.add(hp)
        while stack:
            r, c = stack.pop(); comp.append((r, c))
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                q = (r + dr, c + dc)
                if q in holes and q not in seen:
                    seen.add(q); stack.append(q)
        if len(comp) < max_area:
            for r, c in comp:
                out[r, c] = 1
    return out


def _zhang_suen(img):
    """Vectorised Zhang-Suen thinning to a 1px skeleton."""
    im = img.copy()
    while True:
        total = 0
        for step in (0, 1):
            P = im
            p2 = np.roll(P, -1, 0); p6 = np.roll(P, 1, 0)
            p4 = np.roll(P, 1, 1);  p8 = np.roll(P, -1, 1)
            p3 = np.roll(p2, 1, 1); p5 = np.roll(p6, 1, 1)
            p7 = np.roll(p6, -1, 1); p9 = np.roll(p2, -1, 1)
            B = p2 + p3 + p4 + p5 + p6 + p7 + p8 + p9
            seq = [p2, p3, p4, p5, p6, p7, p8, p9, p2]
            A = np.zeros_like(P)
            for k in range(8):
                A = A + (((seq[k] == 0) & (seq[k + 1] == 1)).astype(np.uint8))
            if step == 0:
                c1 = (p2 * p4 * p6 == 0); c2 = (p4 * p6 * p8 == 0)
            else:
                c1 = (p2 * p4 * p8 == 0); c2 = (p2 * p6 * p8 == 0)
            cond = (P == 1) & (B >= 2) & (B <= 6) & (A == 1) & c1 & c2
            cond[0, :] = cond[-1, :] = cond[:, 0] = cond[:, -1] = False
            m = int(cond.sum())
            if m:
                im[cond] = 0
                total += m
        if total == 0:
            break
    return im


def _trace_branches(skel):
    """Decompose the skeleton into graph branches.

    Nodes are pixels of degree != 2 (tips = degree 1, junctions = degree >= 3);
    a branch is the degree-2 chain between two nodes. Each frond of a palm is a
    branch from the crown junction to a tip, so emitting branches keeps every
    frond whole -- unlike a greedy tracer, which runs straight through the crown
    and merges opposite fronds. Returns (branches, tips)."""
    P = skel
    skset = set(map(tuple, np.argwhere(P == 1)))

    def nbrs(p):
        r, c = p
        return [(r + dr, c + dc) for dr in (-1, 0, 1) for dc in (-1, 0, 1)
                if not (dr == 0 and dc == 0) and (r + dr, c + dc) in skset]

    deg = {p: len(nbrs(p)) for p in skset}
    nodeset = {p for p in skset if deg[p] != 2}
    tips = {p for p in skset if deg[p] == 1}

    branches = []
    used = set()          # interior (degree-2) pixels already consumed
    for nd in nodeset:
        for nb in nbrs(nd):
            if nb in used:
                continue
            path = [nd]; prev = nd; cur = nb
            while True:
                path.append(cur)
                if cur in nodeset:
                    break
                used.add(cur)
                nxt = [q for q in nbrs(cur) if q != prev]
                if not nxt:
                    break
                prev, cur = cur, nxt[0]
            branches.append(path)

    # node-node branches get walked from both ends -> keep one of each
    seen = set(); uniq = []
    for b in branches:
        a, z = b[0], b[-1]
        key = (min(a, z), max(a, z), len(b))
        if key in seen:
            continue
        seen.add(key); uniq.append(b)
    if not uniq and skset:                       # pure loop, no nodes
        uniq = [list(skset)]
    return uniq, tips


def _tangent(path, at_start):
    """Unit direction pointing outward from the given end of the path."""
    k = min(5, len(path) - 1)
    if at_start:
        a, b = path[k], path[0]
    else:
        a, b = path[-1 - k], path[-1]
    d = (b[0] - a[0], b[1] - a[1]); n = math.hypot(*d) or 1
    return (d[0] / n, d[1] / n)


def _stitch(paths, gap, ang_cos):
    """Greedily join path endpoints that are close and roughly collinear, so the
    lines fragmented at junctions (e.g. fronds meeting a crown) become continuous."""
    paths = [list(p) for p in paths]
    while True:
        best = None
        for i in range(len(paths)):
            for si in (True, False):
                pi = paths[i][0] if si else paths[i][-1]
                ti = _tangent(paths[i], si)
                for j in range(len(paths)):
                    if j == i:
                        continue
                    for sj in (True, False):
                        pj = paths[j][0] if sj else paths[j][-1]
                        gd = math.hypot(pi[0] - pj[0], pi[1] - pj[1])
                        if gd > gap:
                            continue
                        tj = _tangent(paths[j], sj)
                        # outward tangents should be roughly opposite for a smooth join
                        if (ti[0] * tj[0] + ti[1] * tj[1]) < -ang_cos:
                            if best is None or gd < best[0]:
                                best = (gd, i, si, j, sj)
        if best is None:
            return paths
        _, i, si, j, sj = best
        A = paths[i][::-1] if si else paths[i]     # A ends at the join point
        B = paths[j] if sj else paths[j][::-1]      # B starts at the join point
        newp = A + B
        for k in sorted((i, j), reverse=True):
            paths.pop(k)
        paths.append(newp)


def extract_centerlines(polylines, dilation_px=3, resolution=520,
                        min_spur_px=25, stitch_gap_px=16, stitch_angle_deg=50,
                        fill_area_frac=0.01):
    """Return clean centrelines (each a list of (x, y) in the 2D working plane)
    from a set of sketchy input polylines (also in plane coords)."""
    pts = np.array([(float(c[0]), float(c[1])) for p in polylines for c in p])
    if len(pts) < 4:
        return []
    minx, miny = pts.min(0)
    maxx, maxy = pts.max(0)
    ext = max(maxx - minx, maxy - miny) or 1e-6
    margin = 12
    scale = (resolution - 2 * margin) / ext
    W = int((maxx - minx) * scale) + 2 * margin
    H = int((maxy - miny) * scale) + 2 * margin

    img = _rasterize(polylines, minx, miny, scale, margin, H, W, dilation_px)
    img = _fill_holes(img, fill_area_frac)
    skel = _zhang_suen(img)
    branches, tips = _trace_branches(skel)

    # Keep structural branches (junction-to-junction) whole; drop only the short
    # spurs (a branch ending at a tip that is shorter than min_spur = a tick).
    kept = []
    for b in branches:
        if len(b) < 6:
            continue
        is_spur = (b[0] in tips) or (b[-1] in tips)
        if is_spur and len(b) < min_spur_px:
            continue
        kept.append(b)

    # Reconnect branches whose endpoints are close and collinear, so a line split
    # at a junction (e.g. the trunk crossed by a frond) reads as one stroke.
    if stitch_gap_px > 0:
        kept = _stitch(kept, stitch_gap_px, math.cos(math.radians(stitch_angle_deg)))

    out = []
    for p in kept:
        out.append([(minx + (c - margin) / scale, miny + (r - margin) / scale)
                    for (r, c) in p])
    return out
