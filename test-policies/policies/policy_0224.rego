package risk.enforcement.policy.allow.policy_0224

# Auto-generated policy 224
# Package: risk.enforcement.policy.allow

# Metadata
metadata := {
    "policy_id": "0224",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0224_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0224_allowed if {
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
