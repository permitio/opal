package access.authorization.policy.validate.policy_0760

# Auto-generated policy 760 (Rego v1 syntax)
# Package: access.authorization.policy.validate

# Metadata
metadata := {
    "policy_id": "0760",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0760_allowed if {
    data.policies.access.enabled
}
policy_0760_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0760_allowed = false
