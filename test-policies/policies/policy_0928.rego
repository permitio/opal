package access.monitoring.policy.deny.policy_0928

# Auto-generated policy 928 (Rego v1 syntax)
# Package: access.monitoring.policy.deny

# Metadata
metadata := {
    "policy_id": "0928",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0928_allowed = false
policy_0928_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
