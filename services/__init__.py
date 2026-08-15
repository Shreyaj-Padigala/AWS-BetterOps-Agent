"""Business logic.

Services own business rules, authorisation checks and transaction boundaries. They never
write SQL (that is the repositories' job) and never touch Flask request or response
objects (that is the routes' job).
"""
