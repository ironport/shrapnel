#include <libaio.h>

int main()
{
  io_context_t ctx;
  int ret;
  ctx = 0;
  ret = io_setup(128, &ctx);
  if (ret < 0) {
    return -1;
  }
  ret = io_destroy(ctx);
  return 0;
}
