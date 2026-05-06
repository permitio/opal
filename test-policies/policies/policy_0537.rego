package audit.authorization.context.check.policy_0537

# Auto-generated policy 537 (Rego v1 syntax)
# Package: audit.authorization.context.check

# Metadata
metadata := {
    "policy_id": "0537",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0537_allowed if {
    input.user.role == "admin"
}
policy_0537_allowed if {
    input.user.active
    input.resource.public
}
