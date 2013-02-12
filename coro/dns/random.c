/*
# Copyright (c) 2002-2012 IronPort Systems and Cisco Systems
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
*/

#include <unistd.h>
#include "Python.h"

/*
  from djbdns
  this code is used to generate a random id for queries
*/

// Note: djb put djbdns into the public domain, see: http://cr.yp.to/distributors.html

#if defined (NODOCSTRINGS)
#define DOCSTRING(v) ""
#else
#define DOCSTRING(v) v
#endif

static char startup_seed[128];

static char module_doc[] = DOCSTRING (
"Used to generate random id's for dns packets.\n\
dns_random(n) - return random number.\n\
");


static unsigned int seed[32];
static unsigned int in[12];
static unsigned int out[8];
static int outleft = 0;

/*
  uint32_unpack()
  Takes a 4 byte buffer and stores an unsigned integer into u.
*/
void uint32_unpack(const char s[4],unsigned int *u)
{
  unsigned int result;

  result = (unsigned char) s[3];
  result <<= 8;
  result += (unsigned char) s[2];
  result <<= 8;
  result += (unsigned char) s[1];
  result <<= 8;
  result += (unsigned char) s[0];

  *u = result;
}

#define ROTATE(x,b) (((x) << (b)) | ((x) >> (32 - (b))))
#define MUSH(i,b) x = t[i] += (((x ^ seed[i]) + sum) ^ ROTATE(x,b));

/*
  Simple Unpredictable Random Function
*/
static void surf(void)
{
  unsigned int t[12]; unsigned int x; unsigned int sum = 0;
  int r; int i; int loop;

  for (i = 0;i < 12;++i) t[i] = in[i] ^ seed[12 + i];
  for (i = 0;i < 8;++i) out[i] = seed[24 + i];
  x = t[11];
  for (loop = 0;loop < 2;++loop) {
    for (r = 0;r < 16;++r) {
      sum += 0x9e3779b9;
      MUSH(0,5) MUSH(1,7) MUSH(2,9) MUSH(3,13)
      MUSH(4,5) MUSH(5,7) MUSH(6,9) MUSH(7,13)
      MUSH(8,5) MUSH(9,7) MUSH(10,9) MUSH(11,13)
    }
    for (i = 0;i < 8;++i) out[i] ^= t[i + 4];
  }
}

/*
  dns_random_init(char data[128])
  Call this when your program first starts.
  Give it a 128 character buffer of junk.
*/
void dns_random_init(const char data[128])
{
  int i;
  char tpack[16];
  struct timeval now;
  unsigned long long bignum;

  for (i = 0;i < 32;++i)
    uint32_unpack(data + 4 * i,seed + i);

  //Note: emulating djb's time packing
  gettimeofday(&now, NULL);
  bignum = now.tv_sec;
  tpack[7] = bignum & 255; bignum >>= 8;
  tpack[6] = bignum & 255; bignum >>= 8;
  tpack[5] = bignum & 255; bignum >>= 8;
  tpack[4] = bignum & 255; bignum >>= 8;
  tpack[3] = bignum & 255; bignum >>= 8;
  tpack[2] = bignum & 255; bignum >>= 8;
  tpack[1] = bignum & 255; bignum >>= 8;
  tpack[0] = bignum;
  bignum = 0;
  tpack[15] = bignum & 255; bignum >>= 8;
  tpack[14] = bignum & 255; bignum >>= 8;
  tpack[13] = bignum & 255; bignum >>= 8;
  tpack[12] = bignum;
  bignum = 1000 * now.tv_usec + 500;
  tpack[11] = bignum & 255; bignum >>= 8;
  tpack[10] = bignum & 255; bignum >>= 8;
  tpack[9]  = bignum & 255; bignum >>= 8;
  tpack[8]  = bignum;

  for (i = 0;i < 4;++i)
    uint32_unpack(tpack + 4 * i,in + 4 + i);

  in[8] = getpid();
  in[9] = getppid();
  /* more space in 10 and 11, but this is probably enough */
}

/*
  dns_random()
  Returns a random number modulus n.
*/
unsigned int dns_random(unsigned int n)
{
  if (!n) return 0;

  if (!outleft) {
    if (!++in[0]) if (!++in[1]) if (!++in[2]) ++in[3];
    surf();
    outleft = 8;
  }

  return out[--outleft] % n;
}

PyObject *
Py_dns_random(PyObject *self, PyObject *args)
{
    int n;

    if(!PyArg_ParseTuple(args, "i", &n)) {
        return NULL;
    }
    return PyInt_FromLong((long) dns_random((unsigned int)n));
}

static PyMethodDef dns_random_methods[] = {
  {"dns_random", Py_dns_random, METH_VARARGS, DOCSTRING ("dns_random(n) -> Returns a random int modulus n.")},
  {0, 0}
};


void initrandom(void)
{
    Py_InitModule3("random", dns_random_methods, module_doc);
    dns_random_init(startup_seed);
}
