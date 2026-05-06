package risk.monitoring.resource.deny.utils.policy_0612

# Auto-generated policy 612
# Package: risk.monitoring.resource.deny.utils

# Metadata
metadata := {
    "policy_id": "0612",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0612_allowed = false
policy_0612_allowed if {
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
