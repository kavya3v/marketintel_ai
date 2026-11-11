import unittest
from unittest.mock import patch
from langchain_core.messages import AIMessage
from src import discovery_agent as a

class SequenceModel:
    def __init__(self, outputs): self.outputs, self.calls = iter(outputs), 0
    def invoke(self, messages):
        self.calls += 1
        value = next(self.outputs)
        if isinstance(value, Exception): raise value
        return AIMessage(content=value)

class FireworksTests(unittest.TestCase):
    def test_permission_denied_chain_is_not_retried_and_preserved(self):
        error = RuntimeError('sensitive request')
        error.__cause__ = PermissionError(13, 'network denied')
        raw = SequenceModel([error])
        with patch.object(a.time, 'sleep') as sleep, self.assertLogs(a.logger, level='ERROR'):
            with self.assertRaisesRegex(a.DiscoveryError, 'network access denied') as caught:
                a._invoke(a.JsonResponseModel(raw, a.SearchPlan), a.SearchPlan, 'plan', {}, 'query planning')
        self.assertIs(caught.exception.__cause__, error)
        self.assertEqual(raw.calls, 1)
        sleep.assert_not_called()

    def test_transient_timeout_recovers_with_short_backoff(self):
        raw = SequenceModel([TimeoutError(), TimeoutError(), '{"queries": ["Notion alternatives"]}'])
        with patch.object(a.time, 'sleep') as sleep:
            self.assertEqual(a.JsonResponseModel(raw, a.SearchPlan).invoke([]).queries, ['Notion alternatives'])
        self.assertEqual(raw.calls, 3)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [0.5, 1.0])

    def test_transient_retries_never_exceed_two(self):
        raw = SequenceModel([TimeoutError(), TimeoutError(), TimeoutError()])
        with patch.object(a.time, 'sleep') as sleep:
            with self.assertRaises(TimeoutError):
                a.JsonResponseModel(raw, a.SearchPlan).invoke([])
        self.assertEqual(raw.calls, 3)
        self.assertEqual(sleep.call_count, 2)

    def test_http_classification_and_no_retry_for_invalid_config(self):
        for status, category in [(401, 'authentication'), (403, 'authentication'), (404, 'model'),
                                 (429, 'rate_limit'), (503, 'http_transient')]:
            error = RuntimeError('private')
            error.status_code = status
            self.assertEqual(a._failure_kind(error), category)
            if status in (401, 403, 404):
                raw = SequenceModel([error])
                with patch.object(a.time, 'sleep') as sleep:
                    with self.assertRaises(RuntimeError): a.JsonResponseModel(raw, a.SearchPlan).invoke([])
                sleep.assert_not_called()

    def test_model_must_be_explicit_instead_of_unavailable_default(self):
        with patch.dict('os.environ', {'FIREWORKS_API_KEY': 'test'}, clear=True):
            with self.assertRaisesRegex(a.DiscoveryError, 'FIREWORKS_MODEL'):
                a._configured_model(a.SearchPlan)

    def test_json_syntax_and_schema_errors_are_distinct_and_chained(self):
        for content, category in [('not-json', 'json_parse'), ('{"queries": []}', 'validation')]:
            raw = SequenceModel([content, content])
            with self.assertLogs(a.logger, level='WARNING'):
                with self.assertRaises(a.DiscoveryError) as caught:
                    a._invoke(a.JsonResponseModel(raw, a.SearchPlan), a.SearchPlan, 'plan', {}, 'query planning')
            self.assertIsInstance(caught.exception.__cause__, a.ValidationError)
            self.assertEqual(a._failure_kind(caught.exception.__cause__), category)

    def test_rate_limit_then_invalid_json_stays_within_three_total_calls(self):
        error = RuntimeError('provider rate limit')
        error.status_code = 429
        raw = SequenceModel([error, 'bad json', '{"queries": ["Notion alternatives"]}'])
        with patch.object(a.time, 'sleep'):
            self.assertEqual(len(a.JsonResponseModel(raw, a.SearchPlan).invoke([]).queries), 1)
        self.assertEqual(raw.calls, 3)

    def test_model_404_has_actionable_safe_error(self):
        error = RuntimeError('sensitive request contents')
        error.status_code = 404
        class FailingModel:
            def invoke(self, messages):
                raise error
        with self.assertLogs(a.logger, level='ERROR'):
            with self.assertRaisesRegex(a.DiscoveryError, 'HTTP 404.*FIREWORKS_MODEL') as caught:
                a._invoke(FailingModel(), a.SearchPlan, 'plan', {}, 'query planning')
        self.assertNotIn('sensitive', str(caught.exception))

    def test_json_validation_and_one_retry(self):
        raw = SequenceModel(['{"queries": []}', '{"queries": ["Notion alternatives"]}'])
        model = a.JsonResponseModel(raw, a.SearchPlan)
        self.assertEqual(model.invoke([]).queries, ['Notion alternatives'])
        self.assertEqual(raw.calls, 2)

    def test_retry_is_bounded(self):
        raw = SequenceModel(['invalid', 'invalid'])
        with self.assertRaises(ValueError): a.JsonResponseModel(raw, a.SearchPlan).invoke([])
        self.assertEqual(raw.calls, 2)

    def test_http_failure_is_not_retried(self):
        raw = SequenceModel([RuntimeError('unavailable')])
        with self.assertRaises(RuntimeError): a.JsonResponseModel(raw, a.SearchPlan).invoke([])
        self.assertEqual(raw.calls, 1)

    def test_sanitized_logging(self):
        error = RuntimeError('must never log full exception request payload')
        error.status_code = 400
        error.body = {'error': {'message': 'unsupported tool calling token-secret Authorization: Bearer xyz request payload: private data'}}
        with patch.dict('os.environ', {'FIREWORKS_API_KEY': 'token-secret'}):
            with self.assertLogs(a.logger, level='ERROR') as logs:
                a._log_provider_error(error, 'query planning')
        output = ' '.join(logs.output)
        for secret in ['token-secret', 'xyz', 'private data', 'must never log']:
            self.assertNotIn(secret, output)
        self.assertIn('400', output)
        self.assertIn('RuntimeError', output)
        self.assertIn('unsupported tool calling', output)

    def test_connection_cause_types_without_messages(self):
        error = RuntimeError('secret request')
        error.__cause__ = OSError(13, 'private host and credentials')
        with self.assertLogs(a.logger, level='ERROR') as logs:
            a._log_provider_error(error, 'query planning')
        output = ' '.join(logs.output)
        self.assertIn('PermissionError', output)
        self.assertIn('errno=13', output)
        self.assertNotIn('private host', output)
        self.assertNotIn('secret request', output)

    def test_configuration_passes_model_and_json_mode(self):
        with patch.dict('os.environ', {'FIREWORKS_API_KEY': 'test', 'FIREWORKS_MODEL': ' accounts/test/models/configured '}), patch.object(a, 'ChatFireworks') as chat:
            model = a._configured_model(a.SearchPlan)
            self.assertEqual(chat.call_args.kwargs['model'], 'accounts/test/models/configured')
            chat.return_value.bind.assert_called_once_with(response_format={'type': 'json_object'})
            self.assertIsInstance(model, a.JsonResponseModel)
