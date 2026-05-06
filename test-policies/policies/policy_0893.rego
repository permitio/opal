package security.monitoring.action.allow.policy_0893

# Auto-generated policy 893 (Rego v1 syntax)
# Package: security.monitoring.action.allow

# Metadata
metadata := {
    "policy_id": "0893",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0893_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0893_allowed if {
    input.user.role == "admin"
}
policy_0893_allowed if {
    data.policies.security.enabled
}
