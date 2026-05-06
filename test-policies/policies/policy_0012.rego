package audit.monitoring.policy.deny.policy_0012

# Auto-generated policy 12 (Rego v1 syntax)
# Package: audit.monitoring.policy.deny

# Metadata
metadata := {
    "policy_id": "0012",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0012_allowed = false
policy_0012_allowed if {
    data.policies.audit.enabled
}
policy_0012_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0012_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
