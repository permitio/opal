package risk.monitoring.user.allow.policy_0206

# Auto-generated policy 206 (Rego v1 syntax)
# Package: risk.monitoring.user.allow

# Metadata
metadata := {
    "policy_id": "0206",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0206_allowed if {
    data.policies.risk.enabled
}
default policy_0206_allowed = false
policy_0206_allowed if {
    input.user.role == "admin"
}
