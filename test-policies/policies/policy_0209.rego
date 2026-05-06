package audit.validation.user.deny.helpers.policy_0209

# Auto-generated policy 209 (Rego v1 syntax)
# Package: audit.validation.user.deny.helpers

# Metadata
metadata := {
    "policy_id": "0209",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0209_allowed if {
    data.policies.audit.enabled
}
policy_0209_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
