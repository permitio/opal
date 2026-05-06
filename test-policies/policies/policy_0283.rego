package security.monitoring.action.verify.policy_0283

# Auto-generated policy 283
# Package: security.monitoring.action.verify

# Metadata
metadata := {
    "policy_id": "0283",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0283_allowed if {
    input.user.role == "admin"
}
policy_0283_allowed if {
    data.policies.security.enabled
}
policy_0283_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0283_allowed if {
    input.user.active
    input.resource.public
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
