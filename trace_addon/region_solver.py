# SPDX-License-Identifier: GPL-3.0-or-later
"""
Dependency-free region solver for the Tracer Plus addon.

The pure-Python region detection here is ported from the Generate Auto Matte
addon (operators/operator_automatte.py), which in turn descends from nijiGPen.
Auto Matte solves regions from *hand-drawn line art* in 3D; here we feed it the
2D contours extracted from an image, so the whole 3D machinery (transformation
matrices, working plane, depth trees) is dropped and we triangulate the 2D
polylines directly. `solve_regions` is unchanged in spirit from Auto Matte's
`solve_matte_regions`.
"""

from collections import deque
from mathutils import geometry


def _edge_key(a, b):
    return (a, b) if a < b else (b, a)


def _simplify_collinear(co, eps=1e-6):
    """Drop near-collinear interior points to keep generated strokes light."""
    if len(co) < 3:
        return co
    out = []
    n = len(co)
    for i in range(n):
        p0 = co[(i - 1) % n]
        p1 = co[i]
        p2 = co[(i + 1) % n]
        cross = (p1[0] - p0[0]) * (p2[1] - p0[1]) - (p2[0] - p0[0]) * (p1[1] - p0[1])
        seg = max((p2[0] - p0[0]) ** 2 + (p2[1] - p0[1]) ** 2, 1e-12)
        if (cross * cross) / seg > eps:
            out.append(p1)
    return out if len(out) >= 3 else co


def triangulate_polylines(poly_list, precision):
    """Constrained Delaunay triangulation of a set of 2D polylines (the 'walls').

    poly_list : list of polylines, each a list of (x, y) tuples. Every polyline
                is treated as a closed loop (its boundary is a wall).
    precision : quantization factor. Points whose (int(x*p), int(y*p)) coincide
                are merged into one vertex, which closes gaps in the line art.
                Smaller precision -> coarser bins -> closes larger gaps.

    Returns a tr_output dict (vertices/segments/triangles/orig_edges) or None.
    """
    co_idx = {}
    verts = []
    segments = []
    xs, ys = [], []

    def key_of(co):
        return (int(co[0] * precision), int(co[1] * precision))

    for co_list in poly_list:
        if len(co_list) < 2:
            continue
        for j, co in enumerate(co_list):
            xs.append(co[0])
            ys.append(co[1])
            key = key_of(co)
            if key not in co_idx:
                co_idx[key] = len(co_idx)
                verts.append((float(co[0]), float(co[1])))
            if j > 0:
                kp = key_of(co_list[j - 1])
                if co_idx[key] != co_idx[kp]:
                    segments.append((co_idx[key], co_idx[kp]))
        # Close the loop
        k0 = key_of(co_list[0])
        kl = key_of(co_list[-1])
        if co_idx[k0] != co_idx[kl]:
            segments.append((co_idx[kl], co_idx[k0]))

    if len(verts) < 3 or not segments:
        return None

    # Padding rings so the exterior region is unambiguous
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    bw, bh = (xmax - xmin) or 1.0, (ymax - ymin) or 1.0
    for ratio in (0.1, 0.3, 0.5):
        verts += [
            (xmin - ratio * bw, ymin - ratio * bh),
            (xmin - ratio * bw, ymax + ratio * bh),
            (xmax + ratio * bw, ymin - ratio * bh),
            (xmax + ratio * bw, ymax + ratio * bh),
        ]

    out = {}
    (out['vertices'], out['segments'], out['triangles'],
     _, out['orig_edges'], _) = geometry.delaunay_2d_cdt(verts, segments, [], 0, 1e-9)
    return out


def solve_regions(tr_output, keep_holes=True):
    """Detect the regions to fill from a triangulated line art.

    Ported from Auto Matte's solve_matte_regions. Groups triangles into regions
    over non-wall edges, seeds the exterior geometrically, then BFS the
    region-adjacency graph counting wall depth.

    keep_holes=True  -> even-odd rule (rings/windows stay empty).
    keep_holes=False -> fill every enclosed region solid.

    Returns a list of (loop_co, is_hole), one per boundary loop, in the same 2D
    coords that were fed to the triangulation.
    """
    vertices = tr_output['vertices']
    segments = tr_output['segments']
    triangles = tr_output['triangles']
    orig_edges = tr_output['orig_edges']
    n_tri = len(triangles)
    if n_tri == 0:
        return []

    solid = set()
    for i, seg in enumerate(segments):
        if len(orig_edges[i]) > 0:
            solid.add(_edge_key(seg[0], seg[1]))

    edge_tris = {}
    for ti, tri in enumerate(triangles):
        for e in (_edge_key(tri[0], tri[1]), _edge_key(tri[1], tri[2]), _edge_key(tri[2], tri[0])):
            edge_tris.setdefault(e, []).append(ti)

    parent = list(range(n_tri))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for e, tris in edge_tris.items():
        if e not in solid and len(tris) == 2:
            parent[find(tris[0])] = find(tris[1])

    region_adj = {}
    for e, tris in edge_tris.items():
        if e in solid and len(tris) == 2:
            ra, rb = find(tris[0]), find(tris[1])
            if ra != rb:
                region_adj.setdefault(ra, set()).add(rb)
                region_adj.setdefault(rb, set()).add(ra)

    ext_tri = min(range(n_tri), key=lambda t: min(vertices[v][0] for v in triangles[t]))
    ext_region = find(ext_tri)
    level = {ext_region: 0}
    queue = deque([ext_region])
    while queue:
        r = queue.popleft()
        for nb in region_adj.get(r, ()):
            if nb not in level:
                level[nb] = level[r] + 1
                queue.append(nb)

    if keep_holes:
        fill_mask = [(level.get(find(t), 1) % 2) == 1 for t in range(n_tri)]
    else:
        fill_mask = [level.get(find(t), 1) >= 1 for t in range(n_tri)]

    adj = {}
    for ti, tri in enumerate(triangles):
        if not fill_mask[ti]:
            continue
        a, b, c = tri
        area2 = ((vertices[b][0] - vertices[a][0]) * (vertices[c][1] - vertices[a][1])
                 - (vertices[c][0] - vertices[a][0]) * (vertices[b][1] - vertices[a][1]))
        seq = (a, b, c) if area2 >= 0 else (a, c, b)
        for k in range(3):
            u, v = seq[k], seq[(k + 1) % 3]
            opp = None
            for t in edge_tris[_edge_key(u, v)]:
                if t != ti:
                    opp = t
                    break
            if opp is None or not fill_mask[opp]:
                adj.setdefault(u, []).append(v)

    loops = []
    remaining = sum(len(v) for v in adj.values())
    while remaining > 0:
        start = next((k for k, v in adj.items() if v), None)
        if start is None:
            break
        loop = [start]
        cur = start
        while adj.get(cur):
            nv = adj[cur].pop()
            remaining -= 1
            if nv == start:
                break
            loop.append(nv)
            cur = nv
        if len(loop) >= 3:
            loops.append(loop)

    result = []
    for loop in loops:
        co = [vertices[i] for i in loop]
        area2 = 0.0
        for i in range(len(co)):
            x1, y1 = co[i]
            x2, y2 = co[(i + 1) % len(co)]
            area2 += x1 * y2 - x2 * y1
        is_hole = area2 < 0
        result.append((_simplify_collinear(co), is_hole))
    return result
