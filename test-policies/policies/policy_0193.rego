package security.monitoring.policy.deny.policy_0193

# Auto-generated policy 193
# Package: security.monitoring.policy.deny

# Metadata
metadata := {
    "policy_id": "0193",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0193_allowed if {
    input.user.role == "admin"
}
policy_0193_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0193_allowed if {
    input.user.active
    input.resource.public
}
policy_0193_allowed if {
    data.policies.security.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
