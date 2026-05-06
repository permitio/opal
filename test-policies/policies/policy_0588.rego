package audit.validation.context.deny.policy_0588

# Auto-generated policy 588 (Rego v1 syntax)
# Package: audit.validation.context.deny

# Metadata
metadata := {
    "policy_id": "0588",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0588_allowed if {
    input.user.active
    input.resource.public
}
policy_0588_allowed if {
    input.user.role == "admin"
}
policy_0588_allowed if {
    data.policies.audit.enabled
}
default policy_0588_allowed = false
