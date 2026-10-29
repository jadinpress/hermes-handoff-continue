"""Regression fixtures use the installed canonical owner wire, not Desktop mocks."""
import asyncio
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('protocol_backend', Path(__file__).with_name('backend.py'))
backend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend)


class CanonicalGateway:
    def __init__(self, home, job):
        self.home, self.job = home, job
        self.events = asyncio.Queue()
        self.calls = []
        self.bad_file = False
        self.status = 'complete'
        self.cancel_create = None
        self.lose_send = False
        self.source_running = False
        self.automation = {}
        self.successor_title = None
        self.title_conflict = False
        self.bad_title_readback = False

    async def rpc(self, method, **params):
        self.calls.append((method, params))
        if method == 'runtime.describe':
            return {'profile_id': str(self.home), 'instance_id':'owner',
                    'capabilities':['durable-admission-v1','event-replay-v1','local-cli-create-v1']}
        if method == 'session.resume':
            return {'session_id':'source-1','stored_session_id':'source-1','subscription_id':'sub-source',
                    'running':self.source_running,'pending':[], 'info':{'cwd':str(self.home),'model':'test-model',
                    'provider':'openai-codex','reasoning_effort':'medium','service_tier':'','source':'gui'}}
        if method == 'session.control.read':
            return {'control':self.automation}
        if method == 'session.control':
            kind=params['action'].split('.')[0]
            self.automation[kind]={'status':'paused'}
            return {'control':self.automation}
        if method == 'prompt.submit':
            if params['session_id'] == 'source-1':
                token = self.job['token']
                path = self.home/'handoffs'/(token+'.md')
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text(('bad' if self.bad_file else '# Synthetic handoff\n'+'Verified synthetic context. '*10+'\nHandoff-Request: '+token+'\n'),encoding='utf8')
                for sid, aid in [('other','source-admission'), ('source-1','unrelated'),('source-1','source-admission')]:
                    await self.events.put({'method':'event','params':{'type':'message.complete','session_id':sid,
                        'admission_id':aid,'payload':{'admission_id':aid,'status':self.status,
                        'text':'HERMES_HANDOFF_READY:'+token}}})
                return {'status':'queued','admission_id':'source-admission'}
            if self.lose_send:
                raise ConnectionError('lost after send')
            return {'status':'queued','admission_id':'next-admission'}
        if method == 'session.create':
            if self.cancel_create:
                self.cancel_create()
            return {'session_id':'successor-1','stored_session_id':'successor-1','subscription_id':'sub-next','messages':[], 'revision':0,
                    'info':{'cwd':str(self.home),'model':'test-model','provider':'openai-codex'}}
        if method == 'session.mutate':
            if self.title_conflict:
                raise RuntimeError('title conflict')
            self.successor_title = params['payload']['title']
            return {'session_id':'successor-1','operation':'rename','revision':1,'title':self.successor_title}
        if method == 'session.info':
            return {'title':'Wrong title' if self.bad_title_readback else self.successor_title}
        if method == 'session.detach':
            return {'detached':True}
        if method == 'prompt.receipt':
            return {'status':'started','admission_id':params['admission_id']}
        raise AssertionError('Unexpected RPC '+method)


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name).resolve()
        self.service = backend.BackendService(self.home,'default')
        self.job = {'stored_id':'source-1','profile':'default','token':'test-token','phase':'starting'}
        self.fake = CanonicalGateway(self.home,self.job)

    def tearDown(self):
        self.service.close()
        self.tmp.cleanup()

    def run_flow(self):
        with patch.object(backend,'_DEADLINE',0.2):
            asyncio.run(self.service.run_workflow(self.job,self.fake))

    def test_actual_owner_capabilities_profile_event_envelope_and_create_fields(self):
        self.run_flow()
        create = next(p for m,p in self.fake.calls if m=='session.create')
        self.assertEqual(create['reasoning'],'medium')
        self.assertEqual(create['source'],'gui')
        self.assertEqual(create['cwd_explicit'],True)
        self.assertEqual(create['request_id'],'test-token')
        self.assertNotIn('reasoning_effort',create)
        sends = [p for m,p in self.fake.calls if m=='prompt.submit']
        self.assertEqual(len(sends),2)
        self.assertIn('HERMES_HANDOFF_READY:test-token',sends[0]['text'])
        self.assertIn('Read the handoff file',sends[1]['text'])
        self.assertIn('approval',sends[1]['text'])
        self.assertEqual(sends[1]['session_id'],'successor-1')
        self.assertIn('successor-1',self.service.handle('status','source-1','default'))
        self.assertEqual(len([1 for m,p in self.fake.calls if m=='session.detach']),2)

    def test_successor_inherits_source_title_and_increments_only_trailing_handoff(self):
        cases = [
            ('Move handoff-continue to backend and fix command',
             'Move handoff-continue to backend and fix command [Handoff 1]'),
            ('Move handoff-continue to backend and fix command [Handoff 1]',
             'Move handoff-continue to backend and fix command [Handoff 2]'),
            ('Project [Handoff 9]', 'Project [Handoff 10]'),
            ('Project [Handoff 2] notes', 'Project [Handoff 2] notes [Handoff 1]'),
            ('Project [Handoff x]', 'Project [Handoff x] [Handoff 1]'),
            ('日本語 — Project', '日本語 — Project [Handoff 1]'),
            ('x' * 100, 'x' * 88 + ' [Handoff 1]'),
            ('x' * 87 + ' [Handoff 99]', 'x' * 86 + ' [Handoff 100]'),
            (None, 'Untitled session [Handoff 1]'),
            ('', 'Untitled session [Handoff 1]'),
            ('   ', 'Untitled session [Handoff 1]'),
        ]
        for title, expected in cases:
            with self.subTest(title=title):
                fake = CanonicalGateway(self.home, self.job)
                rpc = fake.rpc
                async def with_title(method, **params):
                    result = await rpc(method, **params)
                    if method == 'session.resume':
                        result['info']['title'] = title
                    return result
                self.fake = fake
                with patch.object(fake, 'rpc', with_title):
                    self.run_flow()
                create = next(p for m,p in fake.calls if m=='session.create')
                self.assertNotIn('title', create)  # Titled create can reuse unrelated history.
                rename = next(p for m,p in fake.calls if m=='session.mutate')
                self.assertEqual(rename['payload'], {'title':expected})
                self.assertEqual(rename['session_id'], 'successor-1')
                self.assertEqual(rename['operation'], 'rename')
                self.assertEqual(rename['expected_revision'], 0)
                self.assertEqual(rename['request_id'], 'test-token:title')
                self.assertEqual(self.service._read_state('source-1')['successor_title'], expected)

    def test_title_conflict_preserves_fresh_successor_and_does_not_continue(self):
        self.fake.title_conflict = True
        with self.assertRaises(RuntimeError): self.run_flow()
        self.assertEqual(self.job['successor_id'], 'successor-1')
        self.assertEqual(len([1 for m,p in self.fake.calls if m=='prompt.submit']), 1)

    def test_title_readback_mismatch_does_not_continue(self):
        self.fake.bad_title_readback = True
        with self.assertRaises(RuntimeError): self.run_flow()
        self.assertEqual(self.job['successor_id'], 'successor-1')
        self.assertEqual(len([1 for m,p in self.fake.calls if m=='prompt.submit']), 1)

    def test_cancel_while_saving_title_attempt_prevents_rename_and_continuation(self):
        with self.cancel_when_attempt_is_saved('successor_title_attempted'):
            self.run_flow()
        self.assertEqual(self.job['phase'], 'cancelled')
        self.assertEqual(self.job['successor_id'], 'successor-1')
        self.assertFalse(any(m=='session.mutate' for m,p in self.fake.calls))
        self.assertEqual(len([1 for m,p in self.fake.calls if m=='prompt.submit']), 1)

    def test_missing_status_is_not_success_even_with_ready_receipt(self):
        self.fake.status = None
        with self.assertRaises(RuntimeError): self.run_flow()
        self.assertFalse(any(m=='session.create' for m,p in self.fake.calls))

    def test_invalid_handoff_never_creates_successor(self):
        self.fake.bad_file = True
        with self.assertRaises(RuntimeError): self.run_flow()
        self.assertFalse(any(m=='session.create' for m,p in self.fake.calls))

    def test_cancel_during_create_keeps_known_successor_without_send(self):
        def cancel():
            path=self.service._paths('source-1')[2]
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(self.job['token'])
        self.fake.cancel_create=cancel
        self.run_flow()
        self.assertEqual(self.job['successor_id'],'successor-1')
        self.assertEqual(len([1 for m,p in self.fake.calls if m=='prompt.submit']),1)

    def cancel_when_attempt_is_saved(self, flag):
        save = self.service._save
        def save_and_cancel(state):
            save(state)
            if state.get(flag):
                path = self.service._paths('source-1')[2]
                path.write_text(self.job['token'], encoding='ascii')
        return patch.object(self.service, '_save', save_and_cancel)

    def test_cancel_while_saving_source_attempt_prevents_source_submit(self):
        with self.cancel_when_attempt_is_saved('source_submit_attempted'):
            try:
                self.run_flow()
            except backend.HandoffError:
                pass  # The pre-fix path notices cancellation only after sending.
        self.assertFalse(any(m=='prompt.submit' for m,p in self.fake.calls))
        self.assertEqual(self.job['phase'], 'cancelled')

    def test_cancel_while_saving_create_attempt_prevents_creation(self):
        with self.cancel_when_attempt_is_saved('create_attempted'):
            self.run_flow()
        self.assertEqual(self.job['phase'], 'cancelled')
        self.assertFalse(any(m=='session.create' for m,p in self.fake.calls))

    def test_cancel_while_saving_successor_attempt_prevents_successor_submit(self):
        with self.cancel_when_attempt_is_saved('successor_submit_attempted'):
            self.run_flow()
        self.assertEqual(self.job['phase'], 'cancelled')
        self.assertEqual(self.job['successor_id'], 'successor-1')
        self.assertEqual(len([1 for m,p in self.fake.calls if m=='prompt.submit']), 1)

    def test_cancel_after_successor_dispatch_preserves_admitted_outcome(self):
        rpc = self.fake.rpc
        async def cancel_inflight(method, **params):
            if method=='prompt.submit' and params['session_id']=='successor-1':
                path = self.service._paths('source-1')[2]
                path.write_text(self.job['token'], encoding='ascii')
            return await rpc(method, **params)
        with patch.object(self.fake, 'rpc', cancel_inflight):
            self.run_flow()
        self.assertEqual(self.job['phase'], 'complete')
        self.assertEqual(self.job['successor_id'], 'successor-1')
        self.assertEqual(self.job['successor_admission_id'], 'next-admission')
        self.assertEqual(len([1 for m,p in self.fake.calls if m=='prompt.submit']), 2)

    def test_lost_successor_send_keeps_handle_and_never_resends(self):
        self.fake.lose_send=True
        with self.assertRaises(ConnectionError): self.run_flow()
        self.assertEqual(self.job['successor_id'],'successor-1')
        self.assertEqual(len([1 for m,p in self.fake.calls if m=='session.create']),1)
        self.assertIn('prior handoff',self.service.handle('start','source-1','default').lower())

    def test_busy_source_is_refused_without_prompt(self):
        self.fake.source_running=True
        with self.assertRaises(RuntimeError): self.run_flow()
        self.assertFalse(any(m=='prompt.submit' for m,p in self.fake.calls))

    def test_binary_artifact_is_refused(self):
        path=self.home/'handoffs'/'test-token.md';path.parent.mkdir()
        path.write_bytes(b'\0'+b'x'*150+b'\nHandoff-Request: test-token\nHERMES_HANDOFF_READY')
        with self.assertRaises(RuntimeError):backend._verified_artifact(path,path.parent,'test-token')

    def test_noncanonical_submission_statuses_are_not_admitted(self):
        for status in ('streaming','accepted','submitted','unknown'):
            self.assertIsNone(backend._admission({'status':status,'admission_id':'x'}))
        for status in ('queued','started','terminal'):
            self.assertEqual(backend._admission({'status':status,'admission_id':'x'}),'x')

    def test_active_source_automation_is_paused_before_handoff_turn(self):
        self.fake.automation={'goal':{'status':'active'},'loop':{'status':'active'}}
        self.run_flow()
        before_submit=[m for m,p in self.fake.calls[:next(i for i,(m,p) in enumerate(self.fake.calls) if m=='prompt.submit')]]
        self.assertEqual(before_submit.count('session.control'),2)
        self.assertEqual(self.fake.automation['goal']['status'],'paused')
        self.assertEqual(self.job['paused_automation'],['goal','loop'])

    def test_old_cancel_token_cannot_cancel_a_new_job(self):
        path=self.service._paths('source-1')[2]
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text('old-token')
        self.assertFalse(self.service._cancelled(self.job))

if __name__=='__main__': unittest.main()
