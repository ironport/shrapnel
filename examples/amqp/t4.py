# -*- Mode: Python -*-
# companion to t0.py that uses pika
import pika

connection = pika.BlockingConnection(pika.ConnectionParameters(host='localhost'))
channel = connection.channel()
channel.basic_publish (exchange='ething', routing_key='notification', body='Hello World!')
connection.close()
