package security.authorization.user.check.core.policy_0872

# Auto-generated policy 872 (Rego v1 syntax)
# Package: security.authorization.user.check.core

# Metadata
metadata := {
    "policy_id": "0872",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0872_allowed if {
    data.policies.security.enabled
}
policy_0872_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
