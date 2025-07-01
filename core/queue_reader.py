import pika
import json

class QueueReader():
    ###
    # cfg.QUEUES.EVENTS.IP, cfg.QUEUES.EVENTS.PORT, cfg.QUEUES.EVENTS.USER,
    # cfg.QUEUES.EVENTS.PASS, cfg.QUEUES.EVENTS.QUEUE, cfg.QUEUES.EVENTS.EX_NAME,
    # cfg.QUEUES.EVENTS.EX_TYPE, cfg.QUEUES.EVENTS.ROUTE_KEY
    ###
    def __init__(self, cfg):
        self.ip = cfg.QUEUES.EVENTS.IP
        self.port = cfg.QUEUES.EVENTS.PORT
        self.username = cfg.QUEUES.EVENTS.USER
        self.password = cfg.QUEUES.EVENTS.PASS
        self.queue = cfg.QUEUES.EVENTS.QUEUE
        self.exchange_name = cfg.QUEUES.EVENTS.EX_NAME
        self.exchange_type = cfg.QUEUES.EVENTS.EX_TYPE
        self.routing_key = cfg.QUEUES.EVENTS.ROUTE_KEY
        self.durable = cfg.QUEUES.EVENTS.DURABLE
        self.recorder = None
        #self.parameters = pika.ConnectionParameters(self.ip, self.port, '/', 
        #                               credentials=pika.credentials.PlainCredentials(self.username, self.password))
        self.parameters = pika.ConnectionParameters(self.ip, self.port)
        self.connection = pika.BlockingConnection(parameters=self.parameters)
        self.channel = self.connection.channel()

        # Declare exchange
        #self.channel.exchange_declare(exchange=self.exchange_name,
        #                               exchange_type=self.exchange_type)
        #self.channel.exchange_declare()

        # Declare queue 
        # TODO Check Durability, I might need to set it to False
        #result = self.channel.queue_declare(self.queue, durable=self.durable)
        result = self.channel.queue_declare(self.queue)
        self.queue_name = result.method.queue

        # Bind queue to exchange
        #self.channel.queue_bind(exchange=self.exchange_name, queue=self.queue_name, routing_key=self.routing_key)
        #self.channel.queue_bind(exchange='', queue=self.queue_name, routing_key=self.routing_key)

    def start(self):
        self.channel.basic_consume(queue=self.queue_name, on_message_callback=self.callback, auto_ack=True)
        print('Waiting for messages...')
        self.channel.start_consuming()

    def callback(self, ch, method, properties, body):
        print("Received %r" % body)
        json_message = body.decode()
        payload = json.loads(json_message)
        self.recorder.create_recording_event(payload)

