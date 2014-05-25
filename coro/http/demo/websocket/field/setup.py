from distutils.core import setup
from distutils.extension import Extension
from Cython.Distutils import build_ext

setup (
    name='quadtree',
    description='Quad Tree - Spatial Search Data Structure',
    cmdclass={'build_ext': build_ext},
    ext_modules=[Extension ("quadtree", ["quadtree.pyx"],)]
)
