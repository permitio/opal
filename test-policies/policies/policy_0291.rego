package audit.validation.action.allow.policy_0291

# Auto-generated policy 291 (Rego v1 syntax)
# Package: audit.validation.action.allow

# Metadata
metadata := {
    "policy_id": "0291",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0291_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0291_allowed if {
    input.user.active
    input.resource.public
}
policy_0291_allowed if {
    data.policies.audit.enabled
}
