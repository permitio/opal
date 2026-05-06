package security.validation.context.allow.policy_0716

# Auto-generated policy 716 (Rego v1 syntax)
# Package: security.validation.context.allow

# Metadata
metadata := {
    "policy_id": "0716",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0716_allowed if {
    data.policies.security.enabled
}
policy_0716_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0716_allowed = false
