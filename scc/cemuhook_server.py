#!/usr/bin/env python3
"""
SC-Controller - Daemon - CemuHookUDP motion provider

Accepts all connections from clients and sends data captured
by 'cemuhook' actions to them.
"""
from __future__ import unicode_literals
from scc.tools import find_library
from scc.lib.enum import IntEnum
from ctypes import c_uint32, c_int, c_bool, c_char_p, c_size_t, c_float
from ctypes import create_string_buffer
import logging, os, socket
from threading import Thread
from time import sleep
from datetime import datetime, timedelta
log = logging.getLogger("CemuHook")

BUFFER_SIZE = 1024
IP = '127.0.0.1'
PORT = 26760


class MessageType(IntEnum):
	DSUC_VERSIONREQ =	0x100000
	DSUS_VERSIONRSP =	0x100000
	DSUC_LISTPORTS =	0x100001
	DSUS_PORTINFO =		0x100001
	DSUC_PADDATAREQ =	0x100002
	DSUS_PADDATARSP =	0x100002


class CemuhookServer:
	C_DATA_T = c_float * 6
	timeout = timedelta(seconds=1)
	
	def __init__(self, daemon):
		self._lib = find_library('libcemuhook')
		self._lib.cemuhook_data_received.argtypes = [ c_int, c_char_p, c_int, c_char_p, c_size_t ]
		self._lib.cemuhook_data_received.restype = None
		self._lib.cemuhook_feed.argtypes = [ c_int, c_int, CemuhookServer.C_DATA_T ]
		self._lib.cemuhook_feed.restype = None
		self._lib.cemuhook_socket_enable.argtypes = []
		self._lib.cemuhook_socket_enable.restype = c_bool
		self.last_signal = datetime.now()
		
		if not self._lib.cemuhook_socket_enable():
			raise OSError("cemuhook_socket_enable failed")
		
		self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		
		poller = daemon.get_poller()
		daemon.poller.register(self.socket.fileno(), poller.POLLIN, self.on_data_received)
		
		server_port = int(os.getenv('SCC_SERVER_PORT') or PORT);
		server_ip = os.getenv('SCC_SERVER_IP') or IP;
		self.socket.bind((server_ip, server_port))
		log.info("Created CemuHookUDP Motion Provider")

		Thread(target=self._keepalive).start()

	
	def _keepalive(self):
		while True:
			if datetime.now() - self.last_signal >= self.timeout:
				# feed all zeroes to indicate the gyro has not changed
				self.feed((0.0, 0.0, 0.0, 0.0, 0.0, 0.0))
			sleep(1)
	
	def on_data_received(self, fd, event_type):
		if fd != self.socket.fileno(): return
		message, (ip, port) = self.socket.recvfrom(BUFFER_SIZE)
		buffer = create_string_buffer(BUFFER_SIZE)
		self._lib.cemuhook_data_received(fd, ip.encode('utf-8'), port, message, len(message), buffer)
	
	
	def feed(self, data):
		self.last_signal = datetime.now()
		c_data = CemuhookServer.C_DATA_T()
		#log.debug(data)
		c_data[0:6] = data[0:6]
		#log.debug(list(c_data))
		self._lib.cemuhook_feed(self.socket.fileno(), 0, c_data)


