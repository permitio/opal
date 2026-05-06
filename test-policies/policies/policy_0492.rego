package compliance.monitoring.resource.deny.policy_0492

# Auto-generated policy 492
# Package: compliance.monitoring.resource.deny

# Metadata
metadata := {
    "policy_id": "0492",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0492_allowed = false
policy_0492_allowed if {
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
