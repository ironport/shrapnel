# -*- Mode: Python; tab-width: 4 -*-

# SMR 2012: originally from dynwin, circa 1995-96.
#   modernized, replace some funs with generators

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

import region

contains = region.region_contains_region_p
intersects = region.region_intersect_p

# split a rect into four quadrants

def split (rect):
    l, t, r, b = rect
    w2 = ((r - l) / 2) + l
    h2 = ((b - t) / 2) + t
    return (
        (l, t, w2, h2),
        (w2, t, r, h2),
        (l, h2, w2, b),
        (w2, h2, r, b)
    )

# insert an object into the tree.  The object must have a
# 'get_rect()' method in order to support searching.

def insert (tree, tree_rect, ob, ob_rect):
    quads = split(tree_rect)
    # If tree_rect is in quads, then we've shrunk down to a
    # degenerate rectangle, and we will store the object at
    # this level without splitting further.
    if tree_rect not in quads:
        for i in range(4):
            if contains (quads[i], ob_rect):
                if not tree[i]:
                    tree[i] = [None, None, None, None, set()]
                insert (tree[i], quads[i], ob, ob_rect)
                return
    tree[4].add (ob)

# generate all the objects intersecting with <search_rect>
def search_gen (tree, tree_rect, search_rect):
    quads = split (tree_rect)
    # copy the set to avoid 'set changed size during iteration'
    for ob in list (tree[4]):
        if intersects (ob.get_rect(), search_rect):
            yield ob
    for i in range(4):
        if tree[i] and intersects (quads[i], search_rect):
            for ob in search_gen (tree[i], quads[i], search_rect):
                yield ob

# delete a particular object from the tree.

def delete (tree, tree_rect, ob, ob_rect):
    if tree[4]:
        try:
            tree[4].remove (ob)
            return any (tree)
        except KeyError:
            # object not stored here
            pass
    quads = split (tree_rect)
    for i in range(4):
        if tree[i] and intersects (quads[i], ob_rect):
            if not delete (tree[i], quads[i], ob, ob_rect):
                tree[i] = None
                # equivalent to "tree != [None,None,None,None,[]]"
                return any (tree)
    return any (tree)

def gen_all (tree):
    if tree[4]:
        for ob in tree[4]:
            yield ob
    for quad in tree[:4]:
        if quad:
            for x in gen_all (quad):
                yield x

def dump (rect, tree, depth=0):
    print '  ' * depth, rect, tree[4]
    quads = split (rect)
    for i in range (4):
        if tree[i]:
            dump (quads[i], tree[i], depth + 1)

# wrapper for a quadtree, maintains bounds, keeps track of the
# number of objects, etc...

class quadtree:
    def __init__ (self, rect=(0, 0, 16, 16)):
        self.rect = rect
        self.tree = [None, None, None, None, set()]
        self.num_obs = 0
        self.bounds = (0, 0, 0, 0)

    def __repr__ (self):
        return '<quad tree (objects:%d) bounds:%s >' % (
            self.num_obs,
            repr(self.bounds)
        )

    def check_bounds (self, rect):
        l, t, r, b = self.bounds
        L, T, R, B = rect
        if L < l:
            l = L
        if T < t:
            t = T
        if R > r:
            r = R
        if B > b:
            b = B
        self.bounds = l, t, r, b

    def get_bounds (self):
        return self.bounds

    def insert (self, ob):
        rect = ob.get_rect()
        while not contains (self.rect, rect):
            l, t, r, b = self.rect
            w, h = r - l, b - t
            # favor growing right and down
            if (rect[2] > r) or (rect[3] > b):
                # resize, placing original in the upper left
                self.rect = l, t, (r + w), (b + h)
                self.tree = [self.tree, None, None, None, set()]
            elif (rect[0] < l) or (rect[1] < t):
                # resize, placing original in lower right
                self.rect = (l - w, t - h, r, b)
                self.tree = [None, None, None, self.tree, set()]
        # we know the target rect fits in our space
        insert (self.tree, self.rect, ob, rect)
        self.check_bounds (rect)
        self.num_obs += 1

    def gen_all (self):
        for ob in gen_all (self.tree):
            yield ob

    def search_gen (self, rect):
        for ob in search_gen (self.tree, self.rect, rect):
            yield ob

    def delete (self, ob):
        # we ignore the return, because we can't 'forget'
        # the root node.
        delete (self.tree, self.rect, ob, ob.get_rect())
        # XXX this is bad, it assumes the object was deleted
        self.num_obs -= 1

    def dump (self):
        print self
        dump (self.rect, self.tree, 0)

# sample 'box' object.
class box:
    def __init__ (self, rect):
        self.rect = rect

    def get_rect (self):
        return self.rect

    def __repr__ (self):
        return '<box (%d,%d,%d,%d)>' % self.rect
