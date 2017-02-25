#! python3

import unittest
import gc
import threading
import time

class TestWorker(unittest.TestCase):
    
    def test_basic_operations(self):
        """start/pause/resume/stop/join"""
        from worker import Worker, listen, sleep
        a = 0
        
        @Worker
        def increaser():
            nonlocal a

            @listen("set")
            def _(event):
                nonlocal a
                a = event.data

            while True:
                sleep(1)
                a += 1
                
        increaser.start()
        
        with self.subTest("basic"):     
            time.sleep(5.5)
            self.assertEqual(a, 5)
        
        with self.subTest("pause"):
            increaser.pause()           
            time.sleep(2)
            self.assertEqual(a, 5)
            
        with self.subTest("event works even the thread is paused"):
            increaser.fire("set", 0)
            time.sleep(2)
            self.assertEqual(a, 0)
        
        with self.subTest("resume"):
            increaser.resume()
            time.sleep(0.5)
            self.assertEqual(a, 1)
        
        with self.subTest("keep going"):
            time.sleep(4)
            self.assertEqual(a, 5)

        with self.subTest("stop"):
            increaser.stop()
            time.sleep(2)
            self.assertEqual(a, 5)
        
        increaser.join()
        
    def test_child_thread(self):
        from worker import Worker
        parent = Worker()
        child = Worker(parent=parent)
        
        parent.start()
        child.start()
        
        parent.stop().join()
        
        self.assertFalse(parent.is_running())
        self.assertFalse(child.is_running())
        
    def test_daemon(self):
        from worker import current, Worker
        
        with self.subTest("main thread is not deamon"):
            self.assertFalse(current().is_daemon())
        
        with self.subTest("thread is not daemon by default"):
            thread = Worker().start()
            self.assertFalse(thread.is_daemon())
            thread.stop().join()
        
        with self.subTest("should inherit parent if not set"):
            a = Worker(daemon=True).start()
            self.assertTrue(a.is_daemon())
            
            b = Worker(parent=a).start()
            self.assertTrue(b.is_daemon())
            
            a.stop().join()
            
        with self.subTest("parent will wait non-daemon child thread"):
            a = Worker().start()
            b = Worker(parent=a).start()
            a.stop().join()
            self.assertFalse(b.is_running())
            
        with self.subTest("parent won't wait daemon child thread"):
            def blocker():
                time.sleep(1)
            a = Worker().start()
            b = Worker(blocker, parent=a, daemon=True).start()
            a.stop().join()
            self.assertTrue(b.is_running())
            b.join()
            
    def test_detached(self):
        """child will detached from parent when finished"""
        from worker import Worker
        a = Worker().start()
        b = Worker(parent=a).start()
        b.stop().join()
        time.sleep(1)
        self.assertNotIn(b, a.children)
        a.stop().join()
        
    def test_async(self):
        from worker import Async
        
        def long_work(timeout):
            time.sleep(timeout)
            return "Finished after {timeout} seconds".format(timeout=timeout)
        
        with self.subTest("parent wait child"):
            t = time.time()
            async = Async(long_work, 1)
            self.assertEqual(async.get(), "Finished after 1 seconds")
            self.assertAlmostEqual(time.time() - t, 1, 1)
            
        with self.subTest("child wait parent"):
            async = Async(long_work, 1)
            time.sleep(2)
            t = time.time()
            self.assertEqual(async.get(), "Finished after 1 seconds")
            self.assertAlmostEqual(time.time() - t, 0, 1)
            
    def test_event(self):
        from worker import Worker
        
        access = {}
        
        a = Worker().start()
        b = Worker(parent=a).start()
        c = Worker(parent=b).start()
        
        @a.listen("MY_BUBBLE")
        def _(event):
            access["bubble"] = event.target
            
        @c.listen("MY_BROADCAST")
        def _(event):
            access["broadcast"] = event.target
            
        a.broadcast("MY_BROADCAST")
        c.bubble("MY_BUBBLE")
        
        time.sleep(1)
        
        self.assertEqual(access, {
            "bubble": c,
            "broadcast": a
        })
        
        a.stop().join()
        
    def test_overlay(self):
        """Use start_overlay to start worker on current thread"""
        from worker import Worker, is_main
        @Worker
        def thread():
            self.assertTrue(is_main())
        thread.start_overlay()
        
    def test_thread_safe(self):
        """
        These tests are related to:
        http://stackoverflow.com/q/3752618
        
        I'm not even sure if these tests are correct.
        """
        from worker import Worker
        
        with self.subTest("one-time listener"):
            a = Worker().start()
            @a.listen("test")
            def handler(event):
                a.unlisten(handler)
            a.fire("test")
            a.stop().join()
            self.assertNotIn(handler, a.listener_pool)
            self.assertEqual(a.listeners.get("test", []), [])
            
        with self.subTest("add listener in listener callback"):
            a = Worker().start()
            @a.listen("test")
            def _(event):
                @a.listen("test")
                def _(event):
                    pass
            a.fire("test")
            a.stop().join()
            self.assertEqual(len(a.listeners.get("test", [])), 2)
            
    def test_default_parent(self):
        """When creating thread in non-main thread, the parent of the created
        thread will be set to current thread.
        """
        from worker import Worker, wait_forever
        b = None
        @Worker
        def a():
            nonlocal b
            b = Worker().start()
            wait_forever()
        a.start().stop().join()
        self.assertEqual(b.parent_node, a)
        
    def test_channel(self):
        from worker import Worker, Channel
        
        access = set()
        workers = set()
        ch = Channel()
        
        def new_worker():
            w = Worker().start()
            workers.add(w)
            @w.listen("MY_EVENT")
            def _(event):
                access.add(w)
            ch.sub(w)
        
        for i in range(10):
            new_worker()
            
        ch.pub("MY_EVENT")
        
        time.sleep(1)
        
        self.assertEqual(workers, access)
        
        for w in workers:
            w.stop().join()
            
        with self.subTest("automatically unsub after GC"):
            w = None
            workers = None
            access = None
            gc.collect()
            self.assertEqual(len(ch.pool), 0)
            
    def test_priority(self):
        from worker import Worker
        access = []
        thread = Worker().start()
        
        def register(i, priority):
            @thread.listen("MY_EVENT", priority=priority)
            def _(event):
                access.append(i)
                
        for i, p in enumerate([1, 3, 3, 1, 2]):
            register(i, p)
            
        thread.fire("MY_EVENT").stop().join()
        
        self.assertEqual(access, [1, 2, 4, 0, 3])
        
    def test_later(self):
        from worker import current, later, sleep
        
        a = 0
        b = None
        
        def add(value):
            nonlocal a
            nonlocal b
            b = current()
            a += value
            
        later(add, 2, 10)
        
        with self.subTest("not yet"):
            sleep(1)
            self.assertEqual(a, 0)
            self.assertEqual(b, None)
        
        with self.subTest("finished"):
            sleep(2)
            self.assertEqual(a, 10)
            self.assertEqual(b, current())
            
    def tearDown(self):
        from worker import WORKER_POOL, is_main
        
        bad_threads = []
        
        for ws in list(WORKER_POOL.pool.values()):
            w = ws[-1]
            if not is_main(w):
                w.stop().join()
                bad_threads.append(w)
                
        self.assertEqual(bad_threads, [])
        self.assertEqual(threading.active_count(), 1)
        
    
if __name__ == "__main__":
    unittest.main()
