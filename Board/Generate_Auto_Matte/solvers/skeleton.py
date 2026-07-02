import os
import sys
import math
import numpy as np

# ---------------------------------------------------------------------------
# Skeleton-based line cleanup
#
# Works on the *ink*, not the strokes: rasterise every selected stroke into a
# mask, clean it, thin it to a 1px centreline and decompose that into graph
# branches (each frond = one branch from a tip to the crown). This unifies
# overlapping scribbles into a single clean line and drops crossing ticks --
# which stroke clustering can never do reliably.
#
# Robustness comes from SciPy + scikit-image (bundled under ./dependencias):
# scipy.ndimage for morphology / hole filling and skimage.morphology.skeletonize
# for a clean, barb-free skeleton. If they are unavailable we fall back to a
# pure-numpy Zhang-Suen thinning so the feature still runs (lower quality).
# ---------------------------------------------------------------------------

_DEPS = os.path.join(os.path.dirname(os.path.dirname(__file__)), "dependencias")
if os.path.isdir(_DEPS) and _DEPS not in sys.path:
    sys.path.insert(0, _DEPS)

try:
    from scipy import ndimage as _ndi
    from skimage.morphology import skeletonize as _skeletonize
    HAVE_SKIMAGE = True
except Exception:
    HAVE_SKIMAGE = False


# ---------------------------------------------------------------------------
# Rasterisation
# ---------------------------------------------------------------------------

def _rasterize(polylines, minx, miny, scale, margin, H, W, dilation_px):
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
    r = max(1, int(round(dilation_px)))
    oy, ox = np.mgrid[-r:r + 1, -r:r + 1]
    doff = np.argwhere(ox * ox + oy * oy <= r * r) - r
    img = thin.copy()
    for dr, dc in doff:
        img |= np.roll(np.roll(thin, int(dr), 0), int(dc), 1)
    img[0, :] = img[-1, :] = img[:, 0] = img[:, -1] = 0
    return img


# ---------------------------------------------------------------------------
# Mask cleanup + skeletonisation
# ---------------------------------------------------------------------------

def _fill_small_holes_sci(mask, max_area):
    filled = _ndi.binary_fill_holes(mask)
    holes = filled & ~mask
    lbl, n = _ndi.label(holes)
    if n == 0:
        return mask
    sizes = _ndi.sum(np.ones_like(lbl, dtype=float), lbl, index=range(1, n + 1))
    keep = np.array([0] + [1 if s < max_area else 0 for s in sizes], dtype=bool)
    return mask | keep[lbl]


def _skeleton_sci(img, close_px, max_hole_area):
    mask = img.astype(bool)
    if close_px >= 1:
        st = np.ones((2 * close_px + 1, 2 * close_px + 1), bool)
        mask = _ndi.binary_closing(mask, structure=st)
    mask = _fill_small_holes_sci(mask, max_hole_area)
    return skeletonize_wrapper(mask)


def skeletonize_wrapper(mask):
    return _skeletonize(mask).astype(np.uint8)


# --- pure-numpy fallback ----------------------------------------------------

def _fill_holes_np(img, max_area_frac):
    H, W = img.shape
    bg = (img == 0)
    reach = np.zeros_like(bg)
    reach[0, :] = bg[0, :]; reach[-1, :] = bg[-1, :]
    reach[:, 0] = bg[:, 0]; reach[:, -1] = bg[:, -1]
    while True:
        grown = reach.copy()
        grown[1:, :] |= reach[:-1, :]; grown[:-1, :] |= reach[1:, :]
        grown[:, 1:] |= reach[:, :-1]; grown[:, :-1] |= reach[:, 1:]
        grown &= bg
        if grown.sum() == reach.sum():
            break
        reach = grown
    holes = set(map(tuple, np.argwhere(bg & ~reach)))
    max_area = max_area_frac * H * W
    out = img.copy(); seen = set()
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
                im[cond] = 0; total += m
        if total == 0:
            break
    return im


# ---------------------------------------------------------------------------
# Skeleton -> clean graph branches (junction clustering)
# ---------------------------------------------------------------------------

def _neigh8(p):
    r, c = p
    return [(r + dr, c + dc) for dr in (-1, 0, 1) for dc in (-1, 0, 1)
            if not (dr == 0 and dc == 0)]


def _components(pixset):
    comps = []; seen = set()
    for s in pixset:
        if s in seen:
            continue
        comp = set(); stack = [s]; seen.add(s)
        while stack:
            p = stack.pop(); comp.add(p)
            for q in _neigh8(p):
                if q in pixset and q not in seen:
                    seen.add(q); stack.append(q)
        comps.append(comp)
    return comps


def _trace_branches(skel, min_spur_px):
    """Group junction pixels into nodes, cut them out, take the remaining
    components as branches and reattach each end to its node centroid. Prune
    short spur branches (ticks). Returns pixel paths (floats for centroids)."""
    skset = set(map(tuple, np.argwhere(skel == 1)))
    if len(skset) < 4:
        return []

    def sk_nbrs(p):
        return [q for q in _neigh8(p) if q in skset]

    deg = {p: len(sk_nbrs(p)) for p in skset}
    junc = {p for p in skset if deg[p] >= 3}

    jc_of = {}; centroids = []
    for cid, cl in enumerate(_components(junc)):
        for p in cl:
            jc_of[p] = cid
        centroids.append((sum(p[0] for p in cl) / len(cl),
                          sum(p[1] for p in cl) / len(cl)))

    arc = skset - junc

    def arc_nbrs(p, comp):
        return [q for q in _neigh8(p) if q in comp]

    def order(comp):
        ends = [p for p in comp if len(arc_nbrs(p, comp)) <= 1]
        start = ends[0] if ends else next(iter(comp))
        path = [start]; vis = {start}; cur = start
        while True:
            nx = [q for q in arc_nbrs(cur, comp) if q not in vis]
            if not nx:
                break
            nx.sort(key=lambda q: (q[0] - cur[0]) ** 2 + (q[1] - cur[1]) ** 2)
            cur = nx[0]; vis.add(cur); path.append(cur)
        return path

    def adj_node(p):
        for q in _neigh8(p):
            if q in jc_of:
                return jc_of[q]
        return None

    branches = []
    for comp in _components(arc):
        if len(comp) < 3:
            continue
        path = order(comp)
        if len(path) < 10:                       # drop crown specks
            continue
        hj, tj = adj_node(path[0]), adj_node(path[-1])
        free_tip = hj is None or tj is None
        if free_tip and len(path) < min_spur_px:
            continue
        full = ([centroids[hj]] if hj is not None else []) + path + \
               ([centroids[tj]] if tj is not None else [])
        branches.append(full)

    if not branches and skset:
        branches = [order(skset)]
    return branches


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def extract_centerlines(polylines, dilation_px=2, resolution=560,
                        min_spur_px=26, close_px=0):
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

    max_hole_area = 0.004 * H * W
    if HAVE_SKIMAGE:
        skel = _skeleton_sci(img, close_px, max_hole_area)
    else:
        img = _fill_holes_np(img, 0.004)
        skel = _zhang_suen(img)

    branches = _trace_branches(skel, min_spur_px)

    out = []
    for p in branches:
        out.append([(minx + (c - margin) / scale, miny + (r - margin) / scale)
                    for (r, c) in p])
    return out
