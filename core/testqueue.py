import pika
from threading import Thread

class QueueReader():
    def __init__(self, server_ip, server_port, username, 
                 passwd, queue, ex_name, ex_type, routing_key,
                 durable=False):
        self.ip = server_ip
        self.port = server_port
        self.username = username
        self.password = passwd
        self.queue = queue
        self.exchange_name = ex_name
        self.exchange_type = ex_type
        self.routing_key = routing_key
        self.durable = durable
        
        self.parameters = pika.ConnectionParameters(self.ip, self.port, '/', 
                                       credentials=pika.credentials.PlainCredentials(self.username, self.password))
        self.connection = pika.BlockingConnection(parameters=self.parameters)
        self.channel = self.connection.channel()

        # Declare exchange
        self.channel.exchange_declare(exchange=self.exchange_name,
                                       exchange_type=self.exchange_type)

        # Declare queue 
        # TODO Check Durability, I might need to set it to False
        result = self.channel.queue_declare(self.queue, durable=self.durable)
        self.queue_name = result.method.queue

        # Bind queue to exchange
        self.channel.queue_bind(exchange=self.exchange_name, queue=self.queue_name, routing_key=self.routing_key)

    def start(self):
        self.channel.basic_consume(queue=self.queue_name, on_message_callback=self.callback, auto_ack=True)
        print('Waiting for messages...')
        self.channel.start_consuming()    

    def callback(self, ch, method, properties, body):
        print("Received %r" % body)


# Initialization Code
consumerthread = QueueReader('172.16.128.67', '5672', 'test', '123', 'events_queue',
                              'marked_events', 'topic', 'events.create')

Thread(target=consumerthread.start).start()

