package security.monitoring.user.verify.core.policy_0365

# Auto-generated policy 365 (Rego v1 syntax)
# Package: security.monitoring.user.verify.core

# Metadata
metadata := {
    "policy_id": "0365",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0365_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0365_allowed if {
    data.policies.security.enabled
}
policy_0365_allowed if {
    input.user.role == "admin"
}
default policy_0365_allowed = false
