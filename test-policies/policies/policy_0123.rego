package compliance.validation.action.allow.core.policy_0123

# Auto-generated policy 123 (Rego v1 syntax)
# Package: compliance.validation.action.allow.core

# Metadata
metadata := {
    "policy_id": "0123",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0123_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0123_allowed if {
    data.policies.compliance.enabled
}
