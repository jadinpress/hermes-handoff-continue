"""Service lifecycle tests: real disk state and OS locks, no network/model calls."""
import asyncio
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from filelock import FileLock
from test_protocol import backend


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.home=Path(self.tmp.name).resolve()
        self.service=backend.BackendService(self.home,'default')
        self.release=threading.Event()
        self.started=threading.Event()

    def tearDown(self):
        self.release.set()
        self.service.close()
        for thread in list(self.service._threads): thread.join(timeout=3)
        self.tmp.cleanup()

    async def held_worker(self,state):
        self.started.set()
        await asyncio.to_thread(self.release.wait,2)
        state['phase']='cancelled' if self.service._cancelled(state) else 'complete'
        self.service._save(state)

    def test_origin_window_is_persisted_once_and_never_rebound(self):
        window = 'b78652d0-7ec4-40de-bf21-f4970d11f5be'
        other = 'c78652d0-7ec4-40de-bf21-f4970d11f5be'
        with patch.object(self.service, '_connected_workflow', self.held_worker):
            try:
                result = self.service.handle('start', 'source', 'default', desktop_window_id=window)
            except TypeError:
                result = 'origin window context unsupported'
            self.assertIn('started', result)
            self.assertTrue(self.started.wait(2))
            before = self.service._read_state('source')
            self.assertEqual(before['desktop_window_id'], window)
            for action in ('status', 'start', 'cancel'):
                self.service.handle(action, 'source', 'default', desktop_window_id=other)
                state = self.service._read_state('source')
                self.assertEqual(state['desktop_window_id'], window)
                self.assertEqual(state['token'], before['token'])
            self.release.set()
            for thread in list(self.service._threads): thread.join(timeout=3)
            self.assertIn('prior handoff', self.service.handle('start', 'source', 'default', desktop_window_id=other))
            self.assertEqual(self.service._read_state('source')['desktop_window_id'], window)

    def test_notification_failure_keeps_complete_state_and_never_replays(self):
        from test_protocol import CanonicalGateway
        notifications, clients = [], []
        def fail_notification(*args):
            notifications.append(args)
            raise OSError('presentation unavailable')
        self.service = backend.BackendService(self.home, 'default', publish_event=fail_notification)
        async def connected(state):
            client = CanonicalGateway(self.home, state)
            clients.append(client)
            await self.service.run_workflow(state, client)
        window = 'b78652d0-7ec4-40de-bf21-f4970d11f5be'
        with patch.object(self.service, '_connected_workflow', connected):
            self.service.handle('start', 'source-1', 'default', desktop_window_id=window)
            for thread in list(self.service._threads): thread.join(timeout=10)
        state = self.service._read_state('source-1')
        self.assertEqual(state['phase'], 'complete')
        self.assertEqual(state['successor_id'], 'successor-1')
        self.assertEqual(state['successor_admission_id'], 'next-admission')
        self.assertEqual(state['desktop_window_id'], window)
        before = dict(state)
        for action in ('status', 'cancel', 'start'):
            self.service.handle(action, 'source-1', 'default')
        self.assertEqual(self.service._read_state('source-1'), before)
        self.assertEqual(len(notifications), 1)
        self.assertEqual(len(clients), 1)
        self.assertEqual(len([1 for m, p in clients[0].calls if m == 'prompt.submit']), 2)

    def test_status_has_no_side_effect_without_job(self):
        self.assertIn('No handoff',self.service.handle('status','source','default'))
        self.assertFalse(self.service.jobs_dir.exists())

    def test_os_lock_prevents_duplicate_even_from_another_service_instance(self):
        with patch.object(self.service,'_connected_workflow',self.held_worker):
            self.assertIn('started',self.service.handle('start','source','default'))
            self.assertTrue(self.started.wait(2))
            other=backend.BackendService(self.home,'default')
            self.assertIn('already active',other.handle('start','source','default'))
            self.assertNotIn('interrupted',other.handle('status','source','default'))

    def test_cancel_is_source_scoped_and_does_not_erase_newer_handles(self):
        with patch.object(self.service,'_connected_workflow',self.held_worker):
            self.service.handle('start','source','default')
            self.assertTrue(self.started.wait(2))
            self.assertIn('No active',self.service.handle('cancel','other','default'))
            state=self.service._read_state('source')
            state['successor_id']='known-successor'
            self.service._save(state)
            self.assertIn('cancellation recorded',self.service.handle('cancel','source','default'))
            self.assertEqual(self.service._read_state('source')['successor_id'],'known-successor')

    def test_unload_disarms_active_worker_without_interrupt_rpc(self):
        with patch.object(self.service,'_connected_workflow',self.held_worker):
            self.service.handle('start','source','default')
            self.assertTrue(self.started.wait(2))
            self.service.close()
            self.assertTrue(self.service._cancelled(self.service._read_state('source')))
            self.assertIn('shutting down',self.service.handle('start','other','default'))

    def test_corrupt_state_never_starts_or_replays(self):
        path=self.service._paths('source')[0];path.parent.mkdir(parents=True)
        path.write_text('{broken')
        with self.assertRaises(ValueError):self.service.handle('start','source','default')
        self.assertEqual(len(self.service._threads),0)

    def test_stale_worker_state_becomes_interrupted_and_keeps_successor(self):
        state={'stored_id':'source','profile':'default','token':'t','phase':'creating','successor_id':'known'}
        self.service._save(state)
        status=self.service.handle('status','source','default')
        self.assertIn('Worker stopped',status)
        self.assertIn('known',status)
        self.assertIn('prior handoff',self.service.handle('start','source','default'))

    def test_failure_after_uncertain_source_submission_is_recorded_and_never_replayed(self):
        async def fail(state):
            state['source_submit_attempted']=True
            self.service._save(state)
            raise ConnectionError('lost acknowledgement')
        with patch.object(self.service,'_connected_workflow',fail):
            self.service.handle('start','source','default')
            for thread in list(self.service._threads):thread.join(timeout=3)
        state=self.service._read_state('source')
        self.assertEqual(state['phase'],'interrupted')
        self.assertIn('prior handoff',self.service.handle('start','source','default'))

    def test_worker_failure_releases_os_lock(self):
        async def fail(state):raise ConnectionError('offline')
        with patch.object(self.service,'_connected_workflow',fail):
            self.service.handle('start','source','default')
            for thread in list(self.service._threads):thread.join(timeout=3)
        lock=FileLock(str(self.service._paths('source')[1]),thread_local=False)
        with lock.acquire(timeout=0):pass

if __name__=='__main__':unittest.main()
