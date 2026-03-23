from __future__ import annotations


class RSSAgentError(Exception):
    exit_code = 1


class ConfigError(RSSAgentError):
    exit_code = 2


class FetchError(RSSAgentError):
    exit_code = 3


class AnalysisError(RSSAgentError):
    exit_code = 4


class OutputError(RSSAgentError):
    exit_code = 5


class StateError(RSSAgentError):
    exit_code = 6


def get_exit_code(error: Exception) -> int:
    if isinstance(error, RSSAgentError):
        return error.exit_code
    return 1
