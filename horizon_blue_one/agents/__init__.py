"""OrgAudi Agents — Production Pipeline

Only 2 production agents:
- A-07: Auditoria Assurance (5 forense detectors)
- A-08: Auditor NFA-e (LLM analysis with fallback)

26 prototype agents archived in _archived/ for future evaluation.
"""

from .base_agent import AgentResult
from .a07_auditoria_assurance import AuditoriaAssuranceAgent
from .a08_auditor_nfa import AuditorNFAAgent

__all__ = [
    "AgentResult",
    "AuditoriaAssuranceAgent",
    "AuditorNFAAgent",
]
