package audit.monitoring.policy.allow.helpers.policy_0117

# Auto-generated policy 117 (Rego v1 syntax)
# Package: audit.monitoring.policy.allow.helpers

# Metadata
metadata := {
    "policy_id": "0117",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0117_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0117_allowed if {
    input.user.role == "admin"
}
