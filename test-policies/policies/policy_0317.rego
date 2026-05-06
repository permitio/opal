package risk.enforcement.policy.check.policy_0317

# Auto-generated policy 317
# Package: risk.enforcement.policy.check

# Metadata
metadata := {
    "policy_id": "0317",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0317_allowed if {
    input.user.active
    input.resource.public
}
default policy_0317_allowed = false
policy_0317_denied if {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
