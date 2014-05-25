# -*- Mode: Python; tab-width: 4 -*-

# SMR 2012: originally from dynwin, circa 1995

###########################################################################
# regions
###########################################################################

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

def region_intersect_p (a, b):
    return (a[2] >= b[0]) and \
           (b[2] >= a[0]) and \
           (a[3] >= b[1]) and \
           (b[3] >= a[1])

def point_in_region_p (x, y, r):
    return (r[0] <= x <= r[2]) and (r[1] <= y <= r[3])

# does region <a> fully contain region <b>?
def region_contains_region_p (a, b):
    return (a[0] <= b[0]) and \
           (a[2] >= b[2]) and \
           (a[1] <= b[1]) and \
           (a[3] >= b[3])

def union (a, b):
    x0, y0, x1, y1 = a
    x2, y2, x3, y3 = b
    return (
        min (x0, x2),
        min (y0, y2),
        max (x1, x3),
        max (y1, y3)
    )
