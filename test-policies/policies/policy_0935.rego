package audit.authorization.context.check.policy_0935

# Auto-generated policy 935 (Rego v1 syntax)
# Package: audit.authorization.context.check

# Metadata
metadata := {
    "policy_id": "0935",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0935_allowed if {
    data.policies.audit.enabled
}
policy_0935_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0935_allowed if {
    input.user.role == "admin"
}
policy_0935_allowed if {
    input.user.active
    input.resource.public
}
