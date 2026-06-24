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
    """Full post-processing chain that turns the raw spine into a clean line."""
    P = laplacian_smooth(co, smooth_steps, closed)
    P = chaikin_smooth(P, chaikin_steps, closed)
    if resample_length and resample_length > 0:
        P = resample_by_length(P, resample_length, closed)
    return P
