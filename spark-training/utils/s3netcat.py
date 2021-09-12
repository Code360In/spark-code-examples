#!/usr/bin/python

import logging
import optparse
import select
import socket
import tempfile
import time
from datetime import datetime

import boto3
from urlparse import urlparse


def parse_options():
    """
    Parses all command line options and returns an approprate Options object
    :return:
    """
    parser = optparse.OptionParser(description='S3 NetCat Server.')
    parser.add_option(
        '-P',
        '--port',
        action='store',
        dest='port',
        nargs=1,
        default=9977,
        help='Port to listen on',
    )
    parser.add_option(
        '-H',
        '--host',
        action='store',
        dest='host',
        nargs=1,
        default='0.0.0.0',
        help='Host to listen on',
    )
    parser.add_option(
        '-I',
        '--interval',
        action='store',
        dest='interval',
        nargs=1,
        default=1,
        help='Interval between batches',
    )
    parser.add_option(
        '-B',
        '--batch',
        action='store',
        dest='batch',
        nargs=1,
        default=5,
        help='Batch size (number of lines)',
    )
    parser.add_option(
        '-T',
        '--timestamp',
        action='store_const',
        dest='timestamp',
        const=True,
        default=False,
        help='Add Timestamp Column',
    )

    (opts, args) = parser.parse_args()

    return (opts, args)


class Server(object):
    logger = logging.getLogger("Server")

    def __init__(self, host, port, interval, max_batchsize, timestamp):
        self.clients = []
        self.host = host
        self.port = port
        self.interval = interval
        self.max_batchsize = max_batchsize
        self.timestamp = timestamp
        self.s3client = boto3.resource('s3')

    def _open_socket(self):
        self.logger.info("Listening on %s:%d" % (self.host, self.port))
        self.serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.serversocket.bind((self.host, self.port))
        self.serversocket.listen(5)

    def _close_socket(self):
        self.serversocket.close()

    def _handle_clients(self):
        input = [self.serversocket]
        input_ready, output_ready, except_ready = select.select(
            input + self.clients, [], [], 0
        )

        for s in input_ready:
            if s == self.serversocket:
                # handle the server socket
                client, address = self.serversocket.accept()
                self.logger.info("Accepting client connection %s", address)
                self.clients.append(client)

            else:
                # handle all other sockets
                data = s.recv(4096)
                if not data:
                    self.logger.info("Closing client connection %s", s.getpeername())
                    s.close()
                    self.clients.remove(s)

    def _process_lines(self, source):
        current_batch = 0

        for line in source:
            if self.timestamp:
                line = str(datetime.now()) + "\t" + line

            current_batch += 1
            for c in self.clients:
                c.sendall(line)

            if current_batch > self.max_batchsize:
                current_batch = 0
                time.sleep(self.interval)

            self._handle_clients()

    def _process_file(self, s3object):
        self.logger.info("Reading file s3://%s/%s", s3object.bucket_name, s3object.key)
        with tempfile.SpooledTemporaryFile() as source:
            s3object.download_fileobj(source)
            source.seek(0)
            self._process_lines(source)

    def _process_dir(self, dir):
        url = urlparse(dir)
        bucket_name = url.hostname
        prefix = url.path[1:]

        self.logger.info("Processing bucket %s prefixes %s", bucket_name, prefix)

        s3bucket = self.s3client.Bucket(bucket_name)
        files = s3bucket.objects.filter(Prefix=prefix)
        for file in files:
            s3object = self.s3client.Object(file.bucket_name, file.key)
            self._process_file(s3object)

    def run(self, files):
        self._open_socket()

        try:
            for dir in files:
                self._process_dir(dir)
        finally:
            self._close_socket()


def run_server(opts, files):
    logging.basicConfig(
        format='%(asctime)s %(levelname)s:%(message)s', level=logging.INFO
    )

    host = opts.host
    port = int(opts.port)
    interval = int(opts.interval)
    max_batch = int(opts.batch)
    timestamp = opts.timestamp

    # boto3.set_stream_logger('boto3.resources', logging.INFO)

    server = Server(host, port, interval, max_batch, timestamp)
    try:
        server.run(files)
    except KeyboardInterrupt:
        pass
    except RuntimeError as error:
        print(error)


def main():
    """Main method of wordcount start script"""
    opts, files = parse_options()

    run_server(opts, files)


main()
