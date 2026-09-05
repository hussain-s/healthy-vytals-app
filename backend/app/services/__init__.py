"""Application/service layer — use-case orchestration.

Services coordinate a single use case: they validate/authorize at a higher level
than routers, open or join a unit of work, call domain rules for decisions, and
use repositories for persistence (DESIGN §7.2). They are the layer that knows
"what happens when a patient books an appointment" end to end. Business rules
themselves live in ``domain/``; services wire them to persistence and audit.
"""
