package risk.monitoring.context.deny.utils.policy_0632

# Auto-generated policy 632 (Rego v1 syntax)
# Package: risk.monitoring.context.deny.utils

# Metadata
metadata := {
    "policy_id": "0632",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0632_allowed if {
    input.user.active
    input.resource.public
}
default policy_0632_allowed = false
