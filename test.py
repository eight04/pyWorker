#! python3
# pylint: disable=import-outside-toplevel

import unittest
import gc
import threading
import time

class TestWorker(unittest.TestCase):    
    def test_basic_operations(self):
        """start/pause/resume/stop/join"""
        from worker import async_, listen, sleep
        a = 0
        
        @async_
        def increaser():
            nonlocal a

            @listen("set")
            def _(event):
                nonlocal a
                a = event.data

            while True:
                # breakpoint()
                sleep(1)
                a += 1
                
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
        from worker import async_
        
        def long_work(timeout):
            time.sleep(timeout)
            return "Finished after {timeout} seconds".format(timeout=timeout)
        
        with self.subTest("parent wait child"):
            t = time.time()
            pending = async_(long_work, 1)
            self.assertEqual(pending.get(), "Finished after 1 seconds")
            self.assertAlmostEqual(time.time() - t, 1, 1)
            
        with self.subTest("child wait parent"):
            pending = async_(long_work, 1)
            time.sleep(2)
            t = time.time()
            self.assertEqual(pending.get(), "Finished after 1 seconds")
            self.assertAlmostEqual(time.time() - t, 0, 1)

        with self.subTest("async error"):
            @async_
            def pending():
                raise Exception("An error")

            with self.assertRaisesRegex(Exception, "An error"):
                pending.get()
            
    def test_defer(self):
        from worker import Defer, create_worker, current
        
        with self.subTest("resolve"):
            defer = Defer()
            defer.resolve("FOO")
            self.assertEqual(defer.get(), "FOO")
            
        with self.subTest("reject"):
            defer = Defer()
            defer.reject(TypeError("BAR"))
            with self.assertRaisesRegex(TypeError, "BAR"):
                defer.get()
                
        with self.subTest("resolve in another thread"):
            defer = Defer()
            @create_worker
            def _():
                defer.resolve("OK")
            self.assertEqual(defer.get(), "OK")
            
        with self.subTest("resolve before get"):
            defer = Defer()
            defer.resolve("OK")
            time.sleep(0.5)
            self.assertEqual(defer.get(), "OK")
            
        with self.subTest("resolve after get"):
            defer = Defer()
            @create_worker
            def _():
                time.sleep(0.5)
                defer.resolve("OK")
            self.assertEqual(defer.get(), "OK")

        with self.subTest("resolve after get, enter event loop"):
            defer = Defer()
            main = current()
            a = False
            b = False

            @create_worker
            def _():
                time.sleep(0.5)
                
                @main.later
                def _():
                    nonlocal a
                    a = True

                time.sleep(0.5)
                nonlocal b
                b = a
                defer.resolve("OK")
                
            self.assertEqual(defer.get(), "OK")
            self.assertTrue(a)
            self.assertTrue(b)
            
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
        
    def test_listener(self):
        from worker import listen, create_worker, wait_forever, Worker
    
        with self.subTest("once"):
            a = 0
            @create_worker
            def thread():
                @listen("COUNT", once=True)
                def _(event):
                    nonlocal a
                    a += 1
                wait_forever()
            thread.fire("COUNT")
            thread.fire("COUNT")
            time.sleep(0.5)
            self.assertEqual(a, 1)
            thread.stop().join()
            
        with self.subTest("permanent"):
            a = 0
            thread = Worker().start()
            @thread.listen("COUNT")
            def _(event):
                nonlocal a
                a += 1
            thread.fire("COUNT")
            thread.stop().join()
            thread.start()
            thread.fire("COUNT")
            time.sleep(0.5)
            self.assertEqual(a, 2)
            thread.stop().join()
            
        with self.subTest("non-permanent"):
            a = 0
            thread = Worker().start()
            @thread.listen("COUNT", permanent=False)
            def _(event):
                nonlocal a
                a += 1
            thread.fire("COUNT")
            thread.stop().join()
            thread.start()
            thread.fire("COUNT")
            time.sleep(0.5)
            self.assertEqual(a, 1)
            thread.stop().join()
        
        with self.subTest("non-permanent with listen shortcut"):
            a = 0
            @create_worker
            def thread():
                @listen("COUNT")
                def _(event):
                    nonlocal a
                    a += 1
                wait_forever()
            thread.fire("COUNT")
            thread.stop().join()
            thread.start()
            thread.fire("COUNT")
            time.sleep(0.5)
            self.assertEqual(a, 2)
            thread.stop().join()
            
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
            def handler(_event):
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
        self.assertEqual(b.parent, a)
        
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
        
        for _ in range(10):
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
            
        current().later(add, 10, timeout=2)
        
        with self.subTest("not yet"):
            sleep(1)
            self.assertEqual(a, 0)
            self.assertEqual(b, None)
        
        with self.subTest("finished"):
            sleep(2)
            self.assertEqual(a, 10)
            self.assertEqual(b, current())
            
        later(add, 10, timeout=2)
        
        with self.subTest("not yet"):
            sleep(1)
            self.assertEqual(a, 10)
            
        with self.subTest("finished"):
            sleep(2)
            self.assertEqual(a, 20)
            self.assertEqual(b, current())
            
    def test_later_cancel(self):
        from worker import later, sleep
        
        a = False
        def task():
            nonlocal a
            a = True
        pending = later(task, timeout=1)
        sleep(0.5)
        pending.stop()
        sleep(1)
        self.assertFalse(a)
        
    def test_await(self):
        from worker import await_, later
        from time import sleep
        
        a = False
        
        def blocking_task():
            sleep(1)
            
        def task():
            nonlocal a
            a = True
            
        later(task)
        # ensure await_ enter the event loop
        await_(blocking_task)
        self.assertTrue(a)
        
    def test_create_worker(self):
        from worker import create_worker, sleep
        
        a = False
        
        @create_worker
        def thread():
            nonlocal a
            sleep(1)
            a = True
            
        sleep(0.5)
        self.assertFalse(a)
        sleep(1)
        self.assertTrue(a)
        self.assertFalse(thread.is_running())
        thread.join()

    def test_native_thread(self):
        from worker import sleep
        from threading import Thread
        ok = False
        def target():
            sleep(1)
            nonlocal ok
            ok = True
        t = Thread(target=target)
        t.start()
        t.join()
        self.assertTrue(ok)
            
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
