# -*- Mode: Python -*-
# companion to t0.py that uses amqplib
from amqplib import client_0_8 as amqp
conn = amqp.Connection (userid='guest', password='guest', host='localhost', virtual_host='/')
ch = conn.channel()
msg = amqp.Message ('howdy there!', content_type='text/fnord')
ch.basic_publish (msg, 'ething', 'notification')
