package access.monitoring.action.deny.policy_0512

# Auto-generated policy 512 (Rego v1 syntax)
# Package: access.monitoring.action.deny

# Metadata
metadata := {
    "policy_id": "0512",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0512_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0512_allowed if {
    input.user.active
    input.resource.public
}
policy_0512_allowed if {
    data.policies.access.enabled
}
