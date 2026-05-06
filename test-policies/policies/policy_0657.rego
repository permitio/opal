package security.monitoring.context.deny.policy_0657

# Auto-generated policy 657 (Rego v1 syntax)
# Package: security.monitoring.context.deny

# Metadata
metadata := {
    "policy_id": "0657",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0657_allowed if {
    data.policies.security.enabled
}
policy_0657_allowed if {
    input.user.active
    input.resource.public
}
default policy_0657_allowed = false
policy_0657_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
