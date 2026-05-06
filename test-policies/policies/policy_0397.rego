package security.monitoring.action.allow.policy_0397

# Auto-generated policy 397 (Rego v1 syntax)
# Package: security.monitoring.action.allow

# Metadata
metadata := {
    "policy_id": "0397",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0397_allowed if {
    data.policies.security.enabled
}
policy_0397_allowed if {
    input.user.role == "admin"
}
