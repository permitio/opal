package access.enforcement.policy.validate.policy_0601

# Auto-generated policy 601 (Rego v1 syntax)
# Package: access.enforcement.policy.validate

# Metadata
metadata := {
    "policy_id": "0601",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0601_allowed = false
policy_0601_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0601_allowed if {
    data.policies.access.enabled
}
