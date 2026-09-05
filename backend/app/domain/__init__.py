"""Domain layer — pure business rules, no framework or database imports.

Modules here encode the hardest, most non-obvious rules of the system (the
appointment state machine, scheduling constraints, prescription safety, vitals
ranges, access scoping). They operate on plain values / enums and return
decisions; they never import FastAPI, SQLAlchemy, or a Session (DESIGN §7.6,
rule 3). That purity is what makes these rules unit-testable in isolation and is
the natural anchor for the knowledge base.
"""
