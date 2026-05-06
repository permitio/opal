package risk.enforcement.user.deny.policy_0157

# Auto-generated policy 157
# Package: risk.enforcement.user.deny

# Metadata
metadata := {
    "policy_id": "0157",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0157_allowed if {
    input.user.active
    input.resource.public
}
default policy_0157_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
