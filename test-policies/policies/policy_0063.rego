package audit.authorization.context.deny.helpers.policy_0063

# Auto-generated policy 63 (Rego v1 syntax)
# Package: audit.authorization.context.deny.helpers

# Metadata
metadata := {
    "policy_id": "0063",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0063_allowed if {
    input.user.role == "admin"
}
policy_0063_allowed if {
    input.user.active
    input.resource.public
}
policy_0063_allowed if {
    data.policies.audit.enabled
}
