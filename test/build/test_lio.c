/* $Header: //prod/main/ap/shrapnel/test/build/test_lio.c#2 $

This is a test to verify that LIO exists and the kernel has the ident patch.
*/

#include <stdio.h>
#include <sys/types.h>
#include <sys/event.h>
#include <sys/time.h>
#include <aio.h>
#include <signal.h>
#include <fcntl.h>
#include <unistd.h>
#include <string.h>

int
main (int argc, char * argv[])
{
  int kqfd = kqueue();
  int fd;
  struct sigevent sig;
  struct aiocb cb;
  struct aiocb * cbl;
  struct kevent kev;
  char buffer[512];
  char buffer2[512];
  int r0, r1;

  // Just picking a file that always exists.
  fd = open ("/bin/ls", O_RDONLY|O_DIRECT);
  if (fd == -1) {
    perror ("open()");
    return -1;
  } else {
    sig.sigev_notify = SIGEV_KEVENT;
    sig.sigev_notify_kqueue = kqfd;

    memset(&cb, 0, sizeof(cb));
    cb.aio_fildes = fd;
    cb.aio_offset = 0;
    cb.aio_buf = buffer;
    cb.aio_nbytes = 512;
    cb.aio_lio_opcode = LIO_READ;

    cbl = &cb;

    r0 = lio_listio (LIO_NOWAIT, &cbl, 1, &sig);
    if (r0 == -1) {
      perror ("lio_listio()");
    } else {
      r1 = kevent (kqfd, NULL, 0, &kev, 1, NULL);
      if (r1 == -1) {
        perror ("kevent()");
      } else {
#if 0
        fprintf (stderr, "r0=%d r1=%d &cbl=%p\n", r0, r1, &cbl);
        fprintf (
          stderr,
          "kev.ident=%x\n"
          "kev.filter=%x\n"
          "kev.flags=%x\n"
          "kev.fflags=%x\n"
          "kev.data=%p\n"
          "kev.udata=%p\n",
          kev.ident,
          kev.filter,
          kev.flags,
          kev.fflags,
          (void*)kev.data,
          kev.udata
          );
#endif
        lseek (fd, 0, 0);
        read (fd, &buffer2, 512);
        if (memcmp (buffer, buffer2, 512) != 0) {
          fprintf (stderr, "lio_listio() didn't work correctly!\n");
        } else if (&cbl == (void *) kev.ident) {
          fprintf (stderr, "this kernel DOES set kev.ident correctly\n");
          return 0;
        } else {
          fprintf (stderr, "this kernel DOES NOT set kev.ident correctly\n");
          return -1;
        }
      }
    }
  }
  return -1;
}
