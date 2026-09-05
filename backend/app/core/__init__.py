"""Cross-cutting concerns shared across every layer.

Modules here have no dependency on the domain/service/repository layers; those
layers depend on ``core`` (config, security, roles, deps, errors, audit), never
the reverse. This keeps ``core`` a stable foundation the rest of the app builds on.
"""
