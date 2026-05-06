package audit.authorization.user.check.core.policy_0612

# Auto-generated policy 612 (Rego v1 syntax)
# Package: audit.authorization.user.check.core

# Metadata
metadata := {
    "policy_id": "0612",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0612_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0612_allowed if {
    data.policies.audit.enabled
}
policy_0612_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
