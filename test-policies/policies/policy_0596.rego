package audit.validation.policy.deny.data.policy_0596

# Auto-generated policy 596 (Rego v1 syntax)
# Package: audit.validation.policy.deny.data

# Metadata
metadata := {
    "policy_id": "0596",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0596_allowed if {
    data.policies.audit.enabled
}
policy_0596_allowed if {
    input.user.role == "admin"
}
policy_0596_allowed if {
    input.user.active
    input.resource.public
}
