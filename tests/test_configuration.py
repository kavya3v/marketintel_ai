import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
from src import configuration as config
from src import discovery_agent as agent


class ConfigurationTests(unittest.TestCase):
    def test_local_dotenv_without_streamlit_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / '.env'
            file.write_text('TAVILY_API_KEY=local-test\nFIREWORKS_API_KEY=local-model-test\nFIREWORKS_MODEL=test-model\n')
            with patch.dict(os.environ, {}, clear=True), patch.object(config, 'DOTENV_PATH', file), patch.object(config.st, 'secrets', {}):
                self.assertEqual(config.get_setting('TAVILY_API_KEY'), 'local-test')
                self.assertEqual(config.get_setting('FIREWORKS_MODEL'), 'test-model')

    def test_cloud_secrets_reach_clients_without_environment_mutation(self):
        cloud = {'TAVILY_API_KEY': 'cloud-test', 'FIREWORKS_API_KEY': 'cloud-model-test', 'FIREWORKS_MODEL': 'cloud-model'}
        with patch.dict(os.environ, {}, clear=True), patch.object(config, 'load_dotenv'), patch.object(config.st, 'secrets', cloud), patch.object(agent, 'TavilyClient') as search, patch.object(agent, 'ChatFireworks') as model:
            agent._configured_search_client()
            agent._configured_model(agent.SearchPlan)
            self.assertEqual(search.call_args.kwargs['api_key'], 'cloud-test')
            self.assertEqual(model.call_args.kwargs['api_key'], 'cloud-model-test')
            self.assertEqual(model.call_args.kwargs['model'], 'cloud-model')
            self.assertNotIn('TAVILY_API_KEY', os.environ)

    def test_cloud_wins_over_environment_and_environment_over_dotenv(self):
        with patch.dict(os.environ, {'TAVILY_API_KEY': 'env-test'}), patch.object(config, 'load_dotenv'), patch.object(config.st, 'secrets', {'TAVILY_API_KEY': ' cloud-test '}):
            self.assertEqual(config.get_setting('TAVILY_API_KEY'), 'cloud-test')

    def test_missing_secrets_file_falls_back_and_missing_key_is_friendly(self):
        from streamlit.errors import StreamlitSecretNotFoundError
        secrets = Mock()
        secrets.get.side_effect = StreamlitSecretNotFoundError('No secrets file')
        with patch.dict(os.environ, {}, clear=True), patch.object(config, 'load_dotenv'), patch.object(config.st, 'secrets', secrets):
            with self.assertRaisesRegex(agent.DiscoveryError, 'Streamlit.*Secrets'):
                agent._configured_search_client()

    def test_cloud_secret_is_redacted_from_diagnostics(self):
        with patch.object(config.st, 'secrets', {'TAVILY_API_KEY': 'cloud-test-secret'}), patch.object(config, 'load_dotenv'):
            self.assertNotIn('cloud-test-secret', agent._sanitize_provider_message('provider echoed cloud-test-secret'))

    def test_database_permission_failure_is_friendly(self):
        from src.persistence import research_session
        with patch('src.persistence.sqlite3.connect', side_effect=PermissionError('private filesystem detail')):
            with self.assertRaisesRegex(agent.DiscoveryError, 'writable') as caught:
                with research_session(Path(tempfile.gettempdir()) / 'marketintel-cloud-test.sqlite'):
                    pass
            self.assertNotIn('private filesystem detail', str(caught.exception))
