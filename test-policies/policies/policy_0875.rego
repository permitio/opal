package security.monitoring.user.check.policy_0875

# Auto-generated policy 875 (Rego v1 syntax)
# Package: security.monitoring.user.check

# Metadata
metadata := {
    "policy_id": "0875",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0875_allowed = false
policy_0875_allowed if {
    data.policies.security.enabled
}
policy_0875_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0875_allowed if {
    input.user.role == "admin"
}
