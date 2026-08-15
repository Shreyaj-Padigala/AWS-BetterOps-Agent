"""Caching, rate-limit counters and (from Phase 9) distributed locks.

Redis is a performance and coordination layer, never a source of truth: everything in it
can be recomputed from PostgreSQL or an upstream API. That is why a Redis outage degrades
the application instead of breaking it, and why the durable investigation queue is SQS
rather than a Redis list (architecture.md §11).
"""
