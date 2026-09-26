"""Outcome categories at the external boundary, independent of transport/provider."""


class TransportNotSent(Exception):
    """A local failure before the provider transport was invoked."""


class TransportCancelled(TransportNotSent):
    """Current permission or domain state forbids sending."""


class InvalidExternalResult(Exception):
    """A response was received but rejected/invalid; no implicit retry is allowed."""


class ExternalOutcomeUnknown(Exception):
    """Transport started but a definitive result is unavailable."""
