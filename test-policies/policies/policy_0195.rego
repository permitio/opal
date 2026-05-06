package risk.authentication.context.deny.utils.policy_0195

# Auto-generated policy 195
# Package: risk.authentication.context.deny.utils

# Metadata
metadata := {
    "policy_id": "0195",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0195_allowed = false
policy_0195_allowed if {
    input.user.role == "admin"
}
policy_0195_allowed if {
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
