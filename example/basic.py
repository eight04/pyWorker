#! python3

import env
from worker import Worker, sleep

count = None

def increaser():
	global count
	count = 1
	while True:
		print(count)
		count += 1
		sleep(1)

thread = Worker(increaser)

while True:
	command = input("input command: ")

	if command == "pause":
		thread.pause()

	if command == "resume":
		thread.resume()

	if command == "stop":
		thread.stop()
		
	if command == "start":
		thread.start()

	if command == "exit":
		thread.stop()
		break
