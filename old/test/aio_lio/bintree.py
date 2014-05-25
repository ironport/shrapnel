# -*- Mode: Python -*-
# Copyright (c) 2002-2011 IronPort Systems and Cisco Systems
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

def split (xxx_todo_changeme):
    (lo, hi) = xxx_todo_changeme
    w2 = (hi - lo) / 2
    return ((lo, lo + w2), (lo + w2, hi))

def contains (xxx_todo_changeme1, xxx_todo_changeme2):
    (la, ra) = xxx_todo_changeme1
    (lb, rb) = xxx_todo_changeme2
    return la <= lb and ra >= rb

def intersects (xxx_todo_changeme3, xxx_todo_changeme4):
    (la, ra) = xxx_todo_changeme3
    (lb, rb) = xxx_todo_changeme4
    return ra >= lb and rb >= la

# L,T,R,B

class node (object):

    __slots__ = ('l', 'r', 'objects')

    def __init__ (self):
        self.l = None
        self.r = None
        self.objects = None

    def get (self, i):
        if i == 0:
            if self.l is None:
                self.l = node()
            return self.l
        else:
            if self.r is None:
                self.r = node()
            return self.r

    def insert (self, seg, needle):
        segs = split (seg)
        for i in (0, 1):
            s = segs[i]
            if contains (s, needle):
                return self.get(i).insert (s, needle)
        if self.objects is None:
            self.objects = [needle]
        else:
            self.objects.append (needle)

    def delete (self, seg, needle):
        segs = split (seg)
        for i in (0, 1):
            s = segs[i]
            if contains (s, needle):
                return self.get(i).delete (s, needle)
        try:
            self.objects.remove (needle)
            return True
        except ValueError:
            pass

    def search_apply (self, seg, needle, fun):
        if self.objects is not None:
            for ob in self.objects:
                if intersects (ob, needle):
                    fun (ob)
        segs = split (seg)
        for i in (0, 1):
            s = segs[i]
            if contains (s, needle):
                return self.get(i).search_apply (s, needle, fun)

    def dump (self, line, depth):
        print '  ' * depth, line,
        if self.objects:
            print self.objects
        else:
            print
        l, r = split (line)
        if self.l:
            self.l.dump (l, depth + 1)
        if self.r:
            self.r.dump (r, depth + 1)

class bintree:

    def __init__ (self, line=(0, 1024)):
        self.tree = node()
        self.line = line
        self.size = 0

    def __repr__ (self):
        return '<bintree tree (objects:%d) line:%r >' % (
            self.size,
            self.line
        )

    def dump (self):
        self.tree.dump (self.line, 0)

    def insert (self, line):
        while True:
            if contains (self.line, line):
                self.tree.insert (self.line, line)
                break
            else:
                n = node()
                ll, lr = line
                sl, sr = self.line
                w = sr - sl
                if ll < sl:
                    # outside to the left
                    self.line = sl - w, sr
                    n.r, self.tree = self.tree, n
                else:
                    self.line = sl, sr + w
                    n.l, self.tree = self.tree, n
        self.size += 1

    def delete (self, needle):
        return self.tree.delete (self.line, needle)

    def search (self, needle):
        r = []
        self.tree.search_apply (self.line, needle, r.append)
        return r

    def search_apply (self, needle, fun):
        self.tree.search_apply (self.line, needle, fun)

def t0():
    t = bintree()
    t.insert ((0, 200))
    t.insert ((180, 280))
    t.insert ((3000, 4000))
    t.insert ((3050, 3060))
    t.insert ((1000, 1500))
    t.insert ((1400, 1800))
    t.dump()
    t.delete ((3050, 3060))
    t.delete ((180, 280))
    t.dump()
    return t
