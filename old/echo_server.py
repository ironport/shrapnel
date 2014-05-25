# -*- Mode: Python -*-

# a clone of coro_in_c's 't2.c'

import coro
import coro_bench
import socket

the_timer = coro_bench.real_timer()

def service_client (conn, addr):
    while True:
        try:
            data = coro.with_timeout (10, conn.recv, 8192)
        except coro.TimeoutError:
            conn.send ('too slow, moe.  good-bye!\r\n')
            data = None
        if not data:
            conn.close()
            break
        else:
            if data[0] == '!':
                # a command
                if data == '!quit\r\n':
                    conn.send ('ok\r\n')
                    conn.close()
                    break
                elif data == '!shutdown\r\n':
                    coro.set_exit()
                    conn.send ('ok\r\n')
                    conn.close()
                    break
                elif data == '!mark\r\n':
                    the_timer.mark()
                    conn.send ('ok\r\n')
                elif data == '!bench\r\n':
                    conn.send (
                        coro_bench.format_rusage (
                            the_timer.bench()
                        ) + '\r\n\000'
                    )
                elif data == '!stats\r\n':
                    conn.send ('ok\r\n')
                    coro_bench.dump_stats()
                else:
                    conn.send ('huh?\r\n')
            else:
                conn.send (data)

def serve (port):
    s = coro.make_socket (socket.AF_INET, socket.SOCK_STREAM)
    s.set_reuse_addr()
    s.bind (('', port))
    s.listen (8192)
    while True:
        conn, addr = s.accept()
        coro.spawn (service_client, conn, addr)

if __name__ == '__main__':
    import backdoor
    coro.spawn (backdoor.serve)
    coro.spawn (serve, 9001)
    coro.event_loop (30.0)
