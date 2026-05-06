package audit.validation.user.check.policy_0295

# Auto-generated policy 295 (Rego v1 syntax)
# Package: audit.validation.user.check

# Metadata
metadata := {
    "policy_id": "0295",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0295_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0295_allowed if {
    input.user.active
    input.resource.public
}
policy_0295_allowed if {
    data.policies.audit.enabled
}
