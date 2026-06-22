"""Sigma HQ control-plane: read-only aggregation of fleet state.

This package turns the dashboard into a workforce control plane. It reads live
state from upstream sources (SigmaControl, SigmaLink) through a common adapter
protocol, normalizes everything into one entity vocabulary, and exposes it via
read-only ``/api/v1/hq/*`` endpoints. Control/write actions are scaffolded but
disabled (see ``actions.py``) — read-first, write-later.
"""
