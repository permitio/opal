package audit.validation.user.check.core.policy_0856

# Auto-generated policy 856 (Rego v1 syntax)
# Package: audit.validation.user.check.core

# Metadata
metadata := {
    "policy_id": "0856",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0856_allowed if {
    data.policies.audit.enabled
}
policy_0856_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
