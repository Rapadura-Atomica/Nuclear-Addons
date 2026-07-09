import heapq
import numpy as np
from mathutils import geometry

# ---------------------------------------------------------------------------
# Dependency-free line-fitting solver
#
# Ported from nijiGPen's "Single-Line Fit" (operators/operator_line.py +
# solvers/graph.py + solvers/fit.py by chsh2), but rewritten so it needs **no
# SciPy**. The original pipeline is:
#     1. Delaunay triangulation              -> kept (Blender-native geometry)
#     2. Euclidean minimum spanning tree      -> Prim's, pure Python (was scipy.sparse.csgraph)
#     3. Longest path in the tree (the spine) -> double BFS over the tree
#     4. Offset towards neighbours            -> done by the operator (mathutils.kdtree)
#     5. B-spline fit + smooth                -> Laplacian + Chaikin + arc-length
#                                                resample (was scipy.interpolate.splprep)
#
# Steps 1-3 and 5 live here as plain numpy/mathutils functions so the add-on
# keeps the same zero-dependency philosophy as the rest of Auto Matte.
# ---------------------------------------------------------------------------


def triangulate_2d(points_2d):
    """Constrained Delaunay triangulation of a 2D point cloud.

    Returns (verts, tris) where verts is a list of (x, y) and tris a list of
    (a, b, c) index triples. Coincident input points are merged by the solver,
    so verts may be shorter than points_2d."""
    verts, _, tris, _, _, _ = geometry.delaunay_2d_cdt(
        [(float(p[0]), float(p[1])) for p in points_2d], [], [], 0, 1e-9)
    return verts, tris


def _edge_weights_from_triangles(verts, tris):
    """Undirected adjacency {i: {j: dist}} from the triangle edge set."""
    V = np.asarray(verts, dtype=float)
    adj = {}

    def add(i, j):
        if i == j:
            return
        d = float(np.hypot(V[j][0] - V[i][0], V[j][1] - V[i][1]))
        d = d if d > 1e-9 else 1e-9
        adj.setdefault(i, {})[j] = d
        adj.setdefault(j, {})[i] = d

    for t in tris:
        add(t[0], t[1])
        add(t[1], t[2])
        add(t[2], t[0])
    return adj


def _prim_mst(adj):
    """Minimum spanning tree of a connected weighted graph via Prim's algorithm.

    A Delaunay triangulation is always connected, so a single seed reaches every
    vertex. Returns the tree as an adjacency map {i: {j: dist}}."""
    start = next(iter(adj))
    visited = {start}
    tree = {}
    heap = [(w, start, v) for v, w in adj[start].items()]
    heapq.heapify(heap)
    while heap:
        w, u, v = heapq.heappop(heap)
        if v in visited:
            continue
        visited.add(v)
        tree.setdefault(u, {})[v] = w
        tree.setdefault(v, {})[u] = w
        for nb, nw in adj[v].items():
            if nb not in visited:
                heapq.heappush(heap, (nw, v, nb))
    return tree


def _tree_farthest(tree, src):
    """Farthest node from src in a tree (BFS), with predecessor map and distance."""
    dist = {src: 0.0}
    pred = {src: None}
    far, far_dist = src, 0.0
    stack = [src]
    while stack:
        node = stack.pop()
        for nb, w in tree.get(node, {}).items():
            if nb not in dist:
                dist[nb] = dist[node] + w
                pred[nb] = node
                if dist[nb] > far_dist:
                    far_dist, far = dist[nb], nb
                stack.append(nb)
    return far, far_dist, pred


def longest_path_spine(points_2d):
    """Extract the centreline ('spine') that runs through a sketchy point cloud.

    Triangulates the points, builds the Euclidean MST and returns its longest
    path -- the chain of points that best represents the overall stroke
    direction. Returns (spine_co, total_length) where spine_co is an ordered
    list of (x, y). Returns ([], 0.0) when the input is too small to fit."""
    if len(points_2d) < 4:
        return [], 0.0
    verts, tris = triangulate_2d(points_2d)
    if len(verts) < 4 or len(tris) < 1:
        return [], 0.0

    adj = _edge_weights_from_triangles(verts, tris)
    if not adj:
        return [], 0.0
    tree = _prim_mst(adj)

    # Tree diameter via double BFS: farthest-from-arbitrary, then farthest-from-that.
    a, _, _ = _tree_farthest(tree, next(iter(tree)))
    b, total_length, pred = _tree_farthest(tree, a)

    path = []
    node = b
    while node is not None:
        path.append(node)
        node = pred[node]
    path.reverse()
    if len(path) < 4:
        return [], 0.0
    return [(float(verts[i][0]), float(verts[i][1])) for i in path], total_length


# ---------------------------------------------------------------------------
# Smoothing / resampling (replaces the SciPy B-spline fit)
# ---------------------------------------------------------------------------

def laplacian_smooth(co, iterations=2, closed=False):
    """Iterative vertex averaging. Endpoints stay fixed for open curves so the
    line does not shrink away from where the artist started/ended it."""
    P = np.asarray(co, dtype=float)
    if len(P) < 3 or iterations < 1:
        return P
    for _ in range(iterations):
        Q = P.copy()
        Q[1:-1] = 0.25 * P[:-2] + 0.5 * P[1:-1] + 0.25 * P[2:]
        if closed:
            Q[0] = 0.25 * P[-1] + 0.5 * P[0] + 0.25 * P[1]
            Q[-1] = 0.25 * P[-2] + 0.5 * P[-1] + 0.25 * P[0]
        P = Q
    return P


def chaikin_smooth(co, iterations=2, closed=False):
    """Chaikin corner-cutting: produces a smooth quadratic-B-spline-like curve
    without any external solver. Each pass roughly doubles the point count."""
    P = np.asarray(co, dtype=float)
    if len(P) < 3 or iterations < 1:
        return P
    for _ in range(iterations):
        if closed:
            a = P
            b = np.roll(P, -1, axis=0)
            q = 0.75 * a + 0.25 * b
            r = 0.25 * a + 0.75 * b
            P = np.empty((2 * len(a), 2))
            P[0::2] = q
            P[1::2] = r
        else:
            q = 0.75 * P[:-1] + 0.25 * P[1:]
            r = 0.25 * P[:-1] + 0.75 * P[1:]
            new = np.empty((2 * (len(P) - 1), 2))
            new[0::2] = q
            new[1::2] = r
            # Keep the real endpoints so the curve still spans the full stroke.
            P = np.vstack([P[0], new, P[-1]])
    return P


def resample_by_length(co, spacing, closed=False):
    """Resample a polyline to evenly spaced points along its arc length."""
    P = np.asarray(co, dtype=float)
    if len(P) < 3 or spacing <= 0:
        return P
    pts = np.vstack([P, P[0]]) if closed else P
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    total = cum[-1]
    if total < spacing:
        return P
    n = max(2, int(round(total / spacing)) + 1)
    targets = np.linspace(0.0, total, n)
    out = np.empty((n, 2))
    out[:, 0] = np.interp(targets, cum, pts[:, 0])
    out[:, 1] = np.interp(targets, cum, pts[:, 1])
    if closed:
        out = out[:-1]
    return out


def smooth_and_resample(co, total_length, closed=False,
                        smooth_steps=2, chaikin_steps=2, resample_length=None):
    """Post-processing chain that turns the raw spine into a clean line.

    Kept intentionally light: the goal is to *unite* the sketch strokes, not to
    redraw them as a generic smooth curve. Heavy smoothing/resampling is opt-in
    via the operator so the line keeps the character of the original drawing."""
    P = laplacian_smooth(co, smooth_steps, closed)
    P = chaikin_smooth(P, chaikin_steps, closed)
    if resample_length and resample_length > 0:
        P = resample_by_length(P, resample_length, closed)
    return P


# ---------------------------------------------------------------------------
# Bézier straightening (Schneider's algorithm, dependency-free)
#
# The Ink cleanup rasterises strokes and thins them to a 1px skeleton, so its
# centrelines carry stair-step pixel noise and never read as truly straight.
# Fitting cubic Béziers to that centreline with an error tolerance collapses
# each near-straight run into a single smooth segment (splitting only at real
# corners), which is exactly what "make the lines as straight as possible" asks
# for. We then sample the fitted curve back into a Grease Pencil polyline and
# drop the collinear samples, so straight runs end up with very few points.
#
# fit_bezier is a numpy port of Philip J. Schneider's "An Algorithm for
# Automatically Fitting Digitized Curves" (Graphics Gems, 1990): least-squares
# fit of one cubic, Newton-Raphson reparameterisation, recursive split at the
# point of maximum error. No SciPy, consistent with the rest of this solver.
# ---------------------------------------------------------------------------

def _normalize(v):
    n = float(np.hypot(v[0], v[1]))
    return v / n if n > 1e-12 else np.zeros(2)


def _bezier_point(bez, t):
    mt = 1.0 - t
    return (mt * mt * mt) * bez[0] + 3 * (mt * mt * t) * bez[1] \
        + 3 * (mt * t * t) * bez[2] + (t * t * t) * bez[3]


def _bezier_prime(bez, t):
    mt = 1.0 - t
    return 3 * (mt * mt) * (bez[1] - bez[0]) + 6 * (mt * t) * (bez[2] - bez[1]) \
        + 3 * (t * t) * (bez[3] - bez[2])


def _bezier_prime2(bez, t):
    mt = 1.0 - t
    return 6 * mt * (bez[2] - 2 * bez[1] + bez[0]) + 6 * t * (bez[3] - 2 * bez[2] + bez[1])


def _bezier_arclen(bez, samples=16):
    ts = np.linspace(0.0, 1.0, samples)
    pts = np.array([_bezier_point(bez, t) for t in ts])
    return float(np.linalg.norm(np.diff(pts, axis=0), axis=1).sum())


def _chord_length_parameterize(points):
    d = np.linalg.norm(np.diff(points, axis=0), axis=1)
    u = np.concatenate([[0.0], np.cumsum(d)])
    if u[-1] <= 1e-12:
        return np.linspace(0.0, 1.0, len(points))
    return u / u[-1]


def _generate_bezier(points, u, left_tan, right_tan):
    """Least-squares fit of a single cubic to points at parameters u, with the
    two endpoint tangents fixed."""
    first, last = points[0], points[-1]
    A = np.zeros((len(u), 2, 2))
    A[:, 0] = np.outer(3 * (1 - u) ** 2 * u, left_tan)
    A[:, 1] = np.outer(3 * (1 - u) * u ** 2, right_tan)

    C = np.zeros((2, 2))
    X = np.zeros(2)
    line = [first, first, last, last]
    for i, (pt, ui) in enumerate(zip(points, u)):
        C[0, 0] += np.dot(A[i, 0], A[i, 0])
        C[0, 1] += np.dot(A[i, 0], A[i, 1])
        C[1, 0] = C[0, 1]
        C[1, 1] += np.dot(A[i, 1], A[i, 1])
        tmp = pt - _bezier_point(line, ui)
        X[0] += np.dot(A[i, 0], tmp)
        X[1] += np.dot(A[i, 1], tmp)

    det_C0_C1 = C[0, 0] * C[1, 1] - C[1, 0] * C[0, 1]
    det_C0_X = C[0, 0] * X[1] - C[1, 0] * X[0]
    det_X_C1 = X[0] * C[1, 1] - X[1] * C[0, 1]
    alpha_l = 0.0 if abs(det_C0_C1) < 1e-12 else det_X_C1 / det_C0_C1
    alpha_r = 0.0 if abs(det_C0_C1) < 1e-12 else det_C0_X / det_C0_C1

    seg_len = float(np.linalg.norm(first - last))
    eps = 1e-6 * seg_len
    if alpha_l < eps or alpha_r < eps:
        # Fallback: place the handles a third of the chord length along the tangents.
        third = seg_len / 3.0
        return [first, first + left_tan * third, last + right_tan * third, last]
    return [first, first + left_tan * alpha_l, last + right_tan * alpha_r, last]


def _reparameterize(bez, points, u):
    out = u.copy()
    for i, (pt, ui) in enumerate(zip(points, u)):
        d = _bezier_point(bez, ui) - pt
        num = float(np.dot(d, _bezier_prime(bez, ui)))
        den = float(np.dot(_bezier_prime(bez, ui), _bezier_prime(bez, ui))
                    + np.dot(d, _bezier_prime2(bez, ui)))
        out[i] = ui if abs(den) < 1e-12 else ui - num / den
    return np.clip(out, 0.0, 1.0)


def _max_error(points, bez, u):
    dist = np.array([np.linalg.norm(_bezier_point(bez, ui) - pt)
                     for pt, ui in zip(points, u)])
    split = int(np.argmax(dist))
    return float(dist[split]), split


def _fit_cubic(points, left_tan, right_tan, error, depth=0):
    if len(points) == 2:
        third = float(np.linalg.norm(points[0] - points[1])) / 3.0
        return [[points[0], points[0] + left_tan * third,
                 points[1] + right_tan * third, points[1]]]

    u = _chord_length_parameterize(points)
    bez = _generate_bezier(points, u, left_tan, right_tan)
    max_err, split = _max_error(points, bez, u)
    if max_err < error:
        return [bez]

    # Close enough to converge: refine the parameterisation before splitting.
    if depth < 24 and max_err < error * error + error:
        for _ in range(16):
            u = _reparameterize(bez, points, u)
            bez = _generate_bezier(points, u, left_tan, right_tan)
            max_err, split = _max_error(points, bez, u)
            if max_err < error:
                return [bez]

    # Guard against pathological inputs that would not split (keeps recursion finite).
    if split <= 0 or split >= len(points) - 1:
        return [bez]

    center_tan = _normalize(points[split - 1] - points[split + 1])
    left = _fit_cubic(points[:split + 1], left_tan, center_tan, error, depth + 1)
    right = _fit_cubic(points[split:], -center_tan, right_tan, error, depth + 1)
    return left + right


def fit_bezier(points, max_error):
    """Fit a chain of cubic Bézier segments to an ordered 2D polyline.

    max_error is the largest allowed deviation, in the same units as the points.
    Returns a list of segments, each a list [P0, C1, C2, P3] of numpy (x, y);
    an empty list if there is nothing to fit."""
    P = np.asarray(points, dtype=float)
    if len(P) < 2:
        return []
    # Drop consecutive duplicates: they break chord-length parameterisation.
    keep = np.concatenate([[True], np.linalg.norm(np.diff(P, axis=0), axis=1) > 1e-9])
    P = P[keep]
    if len(P) < 2:
        return []
    if len(P) == 2:
        third = float(np.linalg.norm(P[0] - P[1])) / 3.0
        tan = _normalize(P[1] - P[0])
        return [[P[0], P[0] + tan * third, P[1] - tan * third, P[1]]]
    return _fit_cubic(P, _normalize(P[1] - P[0]), _normalize(P[-2] - P[-1]), max_error)


def rdp(points, epsilon):
    """Ramer-Douglas-Peucker simplification (iterative, so no recursion limit).

    Drops points that lie within epsilon of the line between their kept
    neighbours, so straight runs collapse to their two endpoints."""
    P = np.asarray(points, dtype=float)
    n = len(P)
    if n < 3 or epsilon <= 0:
        return P
    keep = np.zeros(n, dtype=bool)
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        s, e = stack.pop()
        if e <= s + 1:
            continue
        a, b = P[s], P[e]
        ab = b - a
        L = float(np.hypot(ab[0], ab[1]))
        seg = P[s + 1:e]
        if L < 1e-12:
            d = np.linalg.norm(seg - a, axis=1)
        else:
            d = np.abs(ab[0] * (a[1] - seg[:, 1]) - (a[0] - seg[:, 0]) * ab[1]) / L
        k = int(np.argmax(d))
        if d[k] > epsilon:
            idx = s + 1 + k
            keep[idx] = True
            stack.append((s, idx))
            stack.append((idx, e))
    return P[keep]


def bezier_to_polyline(segments, resample_length=0.02, simplify_epsilon=None):
    """Sample fitted Bézier segments back into a polyline for a GP stroke.

    Points are spaced by resample_length along each segment; simplify_epsilon
    (if given) then removes the near-collinear samples so straight runs keep
    only a handful of points."""
    if not segments:
        return np.zeros((0, 2))
    chunks = []
    for si, seg in enumerate(segments):
        bez = [np.asarray(p, dtype=float) for p in seg]
        if resample_length and resample_length > 0:
            n = max(2, int(round(_bezier_arclen(bez) / resample_length)) + 1)
        else:
            n = 12
        ts = np.linspace(0.0, 1.0, n)
        pts = np.array([_bezier_point(bez, t) for t in ts])
        chunks.append(pts[1:] if si > 0 else pts)   # skip the duplicated join point
    poly = np.vstack(chunks)
    if simplify_epsilon and simplify_epsilon > 0:
        poly = rdp(poly, simplify_epsilon)
    return poly
