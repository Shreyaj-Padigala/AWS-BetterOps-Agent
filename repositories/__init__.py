"""Data access layer.

Repositories are the only modules that build SQL. They take explicit scoping arguments
(`organization_id`) and return models or `None` — they never make policy decisions and
never raise HTTP-shaped errors.
"""
