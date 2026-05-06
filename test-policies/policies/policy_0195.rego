package audit.validation.action.allow.core.policy_0195

# Auto-generated policy 195 (Rego v1 syntax)
# Package: audit.validation.action.allow.core

# Metadata
metadata := {
    "policy_id": "0195",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0195_allowed if {
    input.user.active
    input.resource.public
}
policy_0195_allowed if {
    input.user.role == "admin"
}
policy_0195_allowed if {
    data.policies.audit.enabled
}
default policy_0195_allowed = false
