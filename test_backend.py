"""Backend continuation regressions; no Desktop or model calls in this suite."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
import sys
import types


class BackendCommandTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('handoff_plugin', Path(__file__).with_name('__init__.py'))
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.assertTrue(callable(getattr(self.module, 'create_handler', None)),
                        'Native command must dispatch directly to the backend, not a Desktop broadcast')

    def test_command_uses_explicit_gateway_context_without_legacy_env(self):
        calls = []
        class Service:
            def handle(inner, action, **context):
                calls.append((action, context))
                return 'No handoff has been requested in this session.'
        handler = self.module.create_handler(Service(), lambda *_: '')
        source = type('Source', (), {'profile': 'default', 'chat_id': 'stored-source'})()
        reply = handler('status', platform='local', source=source,
                        session_id='stored-source', session_key='agent:main:local:dm:stored-source')
        self.assertIn('No handoff', reply)
        self.assertEqual(calls, [('status', {'stored_id': 'stored-source', 'profile': 'default'})])

    def test_command_captures_originating_window_in_service_context(self):
        import inspect
        calls = []
        service = types.SimpleNamespace(handle=lambda *a, **kw: calls.append((a, kw)) or 'started')
        handler = self.module.create_handler(service, lambda *_: '')
        self.assertIn('desktop_window_id', inspect.signature(handler).parameters)
        window = 'b78652d0-7ec4-40de-bf21-f4970d11f5be'
        source = types.SimpleNamespace(profile='default', chat_id='source')
        self.assertEqual(handler('', platform='local', source=source, desktop_window_id=window), 'started')
        self.assertEqual(calls, [(('start',), {'stored_id': 'source', 'profile': 'default',
                                               'desktop_window_id': window})])

    def test_malformed_window_identity_never_calls_service(self):
        calls = []
        service = types.SimpleNamespace(handle=lambda *a, **kw: calls.append((a, kw)) or 'started')
        handler = self.module.create_handler(service, lambda *_: '')
        source = types.SimpleNamespace(profile='default', chat_id='source')
        valid = 'b78652d0-7ec4-40de-bf21-f4970d11f5be'
        for value in ('', valid.upper(), ' ' + valid, valid + '\n', valid.replace('-40de-', '-10de-'),
                      valid.replace('-bf21-', '-7f21-'), valid.replace('-', ''), 42, False, {}, []):
            with self.subTest(value=value):
                reply = handler('', platform='local', source=source, desktop_window_id=value)
                self.assertIn('window', reply.lower())
                self.assertEqual(calls, [])

    def test_unknown_or_messaging_surface_fails_closed(self):
        handler = self.module.create_handler(None, lambda *_: '')
        for platform in (None, 'telegram', 'discord'):
            self.assertIn('local', handler('', platform=platform).lower())

    def test_invalid_args_do_not_start_work(self):
        handler = self.module.create_handler(None, lambda *_: '')
        for arg in ('start', 'status extra', '_claim token', 'cancel extra'):
            self.assertIn('Usage:', handler(arg))

    def test_explicit_empty_identity_never_falls_back_to_ambient_env(self):
        handler = self.module.create_handler(None, lambda key, default='': {'HERMES_SESSION_ID':'foreign', 'HERMES_SESSION_PROFILE':'default'}.get(key, default))
        self.assertIn('identity', handler('status', platform='local', session_id='', source=None).lower())

    def test_dispatch_platform_supplies_missing_legacy_source(self):
        calls = []
        service = types.SimpleNamespace(handle=lambda *a, **kw: calls.append((a, kw)) or 'status result')
        env = {'HERMES_SESSION_PROFILE': 'default'}
        handler = self.module.create_handler(service, env.get)
        self.assertEqual(handler('status', platform='desktop', session_key='stored-source'), 'status result')
        self.assertEqual(calls[0][1]['stored_id'], 'stored-source')

    def test_named_profile_and_default_source_profile_fallback(self):
        for owner in ('default', 'example-alpha', 'example-beta', 'example-gamma'):
            with self.subTest(owner=owner):
                calls = []
                service = types.SimpleNamespace(handle=lambda *a, **kw: calls.append((a, kw)) or 'started')
                handler = self.module.create_handler(service, lambda *_: '', owner)
                source = types.SimpleNamespace(profile=owner if owner != 'default' else None, chat_id='source')
                self.assertEqual(handler('', platform='local', source=source), 'started')
                self.assertEqual(calls[0][1], {'stored_id':'source', 'profile':owner})

    def test_source_profile_mismatch_is_rejected_without_service_call(self):
        handler = self.module.create_handler(None, lambda *_: '', 'default')
        for profile in ('example-alpha', '../default'):
            source = types.SimpleNamespace(profile=profile, chat_id='source')
            self.assertIn('mismatched', handler('', platform='local', source=source))

    def test_service_errors_return_command_output_not_model_fallback(self):
        def fail(*a, **kw):
            raise OSError('private diagnostic must not leak')
        service = types.SimpleNamespace(handle=fail)
        handler = self.module.create_handler(service, lambda *_: '')
        result = handler('', platform='local', source=types.SimpleNamespace(profile='default', chat_id='source'))
        self.assertIn('OSError', result)
        self.assertNotIn('private diagnostic', result)

    def test_native_registration_has_backend_lifetime_cleanup(self):
        name = 'handoff_registration_test'
        spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name('__init__.py'),
                                                    submodule_search_locations=[str(Path(__file__).parent)])
        module = importlib.util.module_from_spec(spec)
        fake_backend = types.ModuleType(name + '.backend')
        closed = []
        fake_backend.BackendService = lambda home, profile: types.SimpleNamespace(
            close=lambda: closed.append(True), handle=lambda *a, **kw:'backend status')
        callbacks, commands = [], []
        ctx = types.SimpleNamespace(on_unload=callbacks.append,
                                    register_command=lambda *a, **kw: commands.append((a, kw)))
        with patch.dict(sys.modules, {name:module, name+'.backend':fake_backend}):
            spec.loader.exec_module(module)
            module.register(ctx)
        self.assertEqual(commands[0][0], ('handoff-continue',))
        self.assertTrue(callable(commands[0][1]['handler']))
        self.assertEqual(len(callbacks), 1)
        callbacks[0]()
        self.assertEqual(closed, [True])


if __name__ == '__main__':
    unittest.main()
