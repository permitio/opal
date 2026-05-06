package access.enforcement.user.validate.policy_0938

# Auto-generated policy 938 (Rego v1 syntax)
# Package: access.enforcement.user.validate

# Metadata
metadata := {
    "policy_id": "0938",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0938_allowed if {
    data.policies.access.enabled
}
policy_0938_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0938_allowed = false
