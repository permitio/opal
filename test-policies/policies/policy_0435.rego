package security.monitoring.context.verify.utils.policy_0435

# Auto-generated policy 435 (Rego v1 syntax)
# Package: security.monitoring.context.verify.utils

# Metadata
metadata := {
    "policy_id": "0435",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0435_allowed if {
    input.user.role == "admin"
}
policy_0435_allowed if {
    input.user.active
    input.resource.public
}
