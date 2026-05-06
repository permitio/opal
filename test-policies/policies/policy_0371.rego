package access.enforcement.user.allow.policy_0371

# Auto-generated policy 371 (Rego v1 syntax)
# Package: access.enforcement.user.allow

# Metadata
metadata := {
    "policy_id": "0371",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0371_allowed if {
    input.user.role == "admin"
}
policy_0371_allowed if {
    data.policies.access.enabled
}
