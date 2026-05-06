package security.monitoring.context.allow.policy_0749

# Auto-generated policy 749 (Rego v1 syntax)
# Package: security.monitoring.context.allow

# Metadata
metadata := {
    "policy_id": "0749",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0749_allowed if {
    input.user.active
    input.resource.public
}
policy_0749_allowed if {
    input.user.role == "admin"
}
