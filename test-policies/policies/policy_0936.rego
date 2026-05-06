package audit.validation.action.verify.utils.policy_0936

# Auto-generated policy 936 (Rego v1 syntax)
# Package: audit.validation.action.verify.utils

# Metadata
metadata := {
    "policy_id": "0936",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0936_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0936_allowed if {
    data.policies.audit.enabled
}
default policy_0936_allowed = false
