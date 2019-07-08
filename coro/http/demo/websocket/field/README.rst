MMO-ish demo
============

This demo creates a large field of objects (5000 rectangles), randomly
distributed.  It then spawns 1000 threads, each representing a
'non-player character', a small colored circle, that wanders drunkenly
around the space.

Each browser has its own independent viewport to the field, 1024x1024 pixels.

Quadtrees are used to manage the display of the background objects
(rectangles), the moving objects (the circles), and the browser
viewports.

The display is done via an html5 2d canvas support, and has been
tested on Chrome, Firefox, Safari.  It also works on iOS.  [I've
tested it on my iPhone over 3G as well].

Changes to each 'viewport' are sent via websocket.

Quadtree
========

The original quadtree implementation (some really old code of mine) was able to handle the 1000 objects, but the CPU load was rather high (80% @ 2.3GHz), so I've pushed that code into Cython.

So in order to run this you'll need to build the Cython extension thus::

    $ python setup.py build_ext --inplace

Running
=======

Start the server::

    $ python3 field.py

In a browser, grab::

    http://hostname:9001/field.html
