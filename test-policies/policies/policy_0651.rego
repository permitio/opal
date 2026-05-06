package access.enforcement.user.validate.policy_0651

# Auto-generated policy 651 (Rego v1 syntax)
# Package: access.enforcement.user.validate

# Metadata
metadata := {
    "policy_id": "0651",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0651_allowed if {
    input.user.role == "admin"
}
policy_0651_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0651_allowed if {
    data.policies.access.enabled
}
