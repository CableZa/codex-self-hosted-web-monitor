import unittest

try:
    from . import monitor_api_accounts_tests
    from . import monitor_api_cache_alerts_tests
    from . import monitor_api_core_tests
    from . import monitor_api_limits_tests
    from . import monitor_api_sessions_integrations_tests
except ImportError:
    from tests import monitor_api_accounts_tests
    from tests import monitor_api_cache_alerts_tests
    from tests import monitor_api_core_tests
    from tests import monitor_api_limits_tests
    from tests import monitor_api_sessions_integrations_tests

MODULES = [
    monitor_api_core_tests,
    monitor_api_accounts_tests,
    monitor_api_limits_tests,
    monitor_api_cache_alerts_tests,
    monitor_api_sessions_integrations_tests,
]


def load_tests(loader, tests, pattern):
    suite = unittest.TestSuite()
    for module in MODULES:
        suite.addTests(loader.loadTestsFromModule(module))
    return suite
