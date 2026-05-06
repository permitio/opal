package audit.validation.action.validate.core.policy_0610

# Auto-generated policy 610 (Rego v1 syntax)
# Package: audit.validation.action.validate.core

# Metadata
metadata := {
    "policy_id": "0610",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0610_allowed if {
    data.policies.audit.enabled
}
policy_0610_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
