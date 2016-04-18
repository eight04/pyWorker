#! python3

import env

from worker import Async, sleep

def long_work(t):
	sleep(t)
	return "Finished in {} second(s)".format(t)

async = Async(long_work, 5)

# Do other stuff here...

print(async.get())
