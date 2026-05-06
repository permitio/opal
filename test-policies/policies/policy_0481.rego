package access.authentication.user.allow.helpers.policy_0481

# Auto-generated policy 481 (Rego v1 syntax)
# Package: access.authentication.user.allow.helpers

# Metadata
metadata := {
    "policy_id": "0481",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0481_allowed = false
policy_0481_allowed if {
    input.user.role == "admin"
}
policy_0481_allowed if {
    data.policies.access.enabled
}
