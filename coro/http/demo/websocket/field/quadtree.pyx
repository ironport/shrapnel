# -*- Mode: Python; tab-width: 4 -*-

# SMR 2012: originally from dynwin, circa 1995-96.
#   modernized, replace some funs with generators
#
# Cython version.
#

#
# Quad-Tree.  A 2D spatial data structure.
#
# Used to quickly locate 'objects' within a particular region.  Each
# node in the tree represents a rectangular region, while its children
# represent that region split into four quadrants.  An 'object' is
# stored at a particular level if it is contained within that region,
# but will not fit into any of the individual quadrants inside it.
#
# If an object is inserted into a quadtree that 'overflows' the current
# boundaries, the tree is re-rooted in a larger space.

# --------------------------------------------------------------------------------
# regions
#
# do two rectangular regions intersect?
#
# +--->
# |           lb,tb-------+
# |           |           |
# |    la,ta--+-----+     |
# |   |       |     |     |
# |   |       +-----+-rb,bb
# V   |             |
#     +--------ra,ba

# a rect is (left,top,right,bottom)
# top is < bottom, left is < right

# proof: imagine all possible cases in 1 dimension,
# (there are six) and then generalize.  simplify the
# expression and you get this.  (trust me 8^)

cimport cython

from libc.stdint cimport int32_t, uint32_t

ctypedef struct rect:
    int32_t l,t,r,b

cdef bint intersects (rect * a, rect * b):
    return a.r >= b.l and b.r >= a.l and a.b >= b.t and b.b >= a.t

# does region <a> fully contain region <b>?
cdef bint contains (rect * a, rect * b):
    return a.l <= b.l and a.r >= b.r and a.t <= b.t and a.b >= b.b

cdef void union (rect * a, rect * b, rect * c):
    c.l = min (a.l, b.l)
    c.t = min (a.l, b.l)
    c.r = max (a.r, b.r)
    c.b = max (a.b, b.b)

# split a rect into four quadrants
@cython.cdivision (True)
cdef split (rect * x, rect * p):
    cdef int32_t w2 = ((x.r - x.l) // 2) + x.l
    cdef int32_t h2 = ((x.b - x.t) // 2) + x.t
    p[0].l = x.l; p[0].t = x.t; p[0].r = w2;  p[0].b = h2
    p[1].l = w2;  p[1].t = x.t; p[1].r = x.r; p[1].b = h2
    p[2].l = x.l; p[2].t = h2;  p[2].r = w2;  p[2].b = x.b
    p[3].l = w2;  p[3].t = h2;  p[3].r = x.r; p[3].b = x.b

cdef inline set_rect (rect * x, int32_t l, int32_t t, int32_t r, int32_t b):
    x.l = l; x.t = t; x.r = r; x.b = b

import sys
W = sys.stderr.write

cdef rect_repr (rect * r):
    return '(%d,%d,%d,%d)' % (r.l, r.t, r.r, r.b)

class QuadtreeError (Exception):
    pass

cdef class node:
    cdef list quads
    cdef set obs

    def __init__ (self, quads=None):
        if quads is None:
            self.quads = [None, None, None, None]
        else:
            self.quads = quads
        self.obs = set()

    cdef insert (self, rect * r, ob ob):
        cdef rect parts[4]
        cdef node q
        if r.r - r.l <= 16:
            # degenerate rectangle, store here
            self.obs.add (ob)
        else:
            split (r, parts)
            for i in range (4):
                q = self.quads[i]
                if contains (&parts[i], &ob.rect):
                    if q is None:
                        self.quads[i] = q = node()
                    q.insert (&parts[i], ob)
                    return
        self.obs.add (ob)

    # delete a particular object from the tree.
    cdef delete (self, rect * r, ob ob):
        cdef rect parts[4]
        cdef node q
        if self.obs:
            try:
                self.obs.remove (ob)
                return self.obs or any (self.quads)
            except KeyError:
                # object not stored here
                pass
        split (r, parts)
        for i in range (4):
            q = self.quads[i]
            if q is not None and intersects (&parts[i], &ob.rect):
                if not q.delete (&parts[i], ob):
                    self.quads[i] = None
                    return self.obs or any (self.quads)
        return self.obs or any (self.quads)

    def gen_all (self):
        cdef node x
        if self.obs is not None:
            for ob in self.obs:
                yield ob
        for i in range (4):
            if self.quads[i] is not None:
                x = self.quads[i]
                for y in x.gen_all():
                    yield y

    cdef search (self, rect * tree_rect, rect * search_rect, list result):
        cdef rect parts[4], x
        cdef node q
        cdef ob ob
        split (tree_rect, parts)
        # copy the set to avoid 'set changed size during iteration'
        for ob in list (self.obs):
            if intersects (search_rect, &ob.rect):
                result.append (ob)
        for i in range (4):
            if self.quads[i] is not None and intersects (&parts[i], search_rect):
                q = self.quads[i]
                q.search (&parts[i], search_rect, result)

cdef class ob:
    "base class for objects to be stored in the quad tree"
    cdef rect rect
    def set_rect (self, int32_t l, int32_t t, int32_t r, int32_t b):
        "set this object's bounding rectangle"
        set_rect (&self.rect, l, t, r, b)
    def get_rect (self):
        return (self.rect.l, self.rect.t, self.rect.r, self.rect.b)
    property rect:
        def __get__ (self):
            return (self.rect.l, self.rect.t, self.rect.r, self.rect.b)
        def __set__ (self, value):
            l,t,r,b = value
            set_rect (&self.rect, l, t, r, b)
    property upper_left:
        def __get__ (self):
            return self.rect.l, self.rect.t
    property width:
        def __get__ (self):
            return self.rect.r - self.rect.l
    property height:
        def __get__ (self):
            return self.rect.b - self.rect.t
    def range_check (self, int32_t l, int32_t t, int32_t r, int32_t b):
        return self.rect.l >= l and self.rect.r <= r and self.rect.t >= t and self.rect.b <= b

cdef class quadtree:

    cdef node tree
    cdef rect rect
    cdef uint32_t num_obs

    def __init__ (self, rect=(0,0,16,16)):
        set_rect (&self.rect, rect[0], rect[1], rect[2], rect[3])
        self.tree = node()
        self.num_obs = 0

    def __repr__ (self):
        return '<quad tree (objects:%d)  rect:(%d,%d,%d,%d)>' % (
            self.num_obs,
            self.rect.l,
            self.rect.t,
            self.rect.r,
            self.rect.b,
            )

    def insert (self, ob ob):
        cdef int32_t w, h
        cdef node new_root
        while not contains (&self.rect, &ob.rect):
            w = self.rect.r - self.rect.l
            h = self.rect.b - self.rect.t
            # favor growing right and down
            if (ob.rect.r > self.rect.r) or (ob.rect.b > self.rect.b):
                # resize, placing original in the upper left
                self.rect.r += w
                self.rect.b += h
                self.tree = node ([self.tree, None, None, None])
            elif (ob.rect.l < self.rect.l) or (ob.rect.t < self.rect.t):
                # resize, placing original in the lower right
                self.rect.l -= w
                self.rect.t -= h
                self.tree = node ([None, None, None, self.tree])
        # we know the target rect fits in our space
        self.tree.insert (&self.rect, ob)
        self.num_obs += 1

    def gen_all (self):
        for ob in self.tree.gen_all():
            yield ob

    def search (self, search_rect):
        cdef list result
        cdef rect r
        r.l, r.t, r.r, r.b = search_rect
        result = []
        self.tree.search (&self.rect, &r, result)
        return result

    def delete (self, ob ob):
        cdef rect r
        self.tree.delete (&self.rect, ob)
        # XXX this is bad, it assumes the object was deleted
        self.num_obs -= 1
