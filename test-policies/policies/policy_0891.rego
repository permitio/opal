package risk.validation.user.deny.policy_0891

# Auto-generated policy 891
# Package: risk.validation.user.deny

# Metadata
metadata := {
    "policy_id": "0891",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0891_allowed = false
policy_0891_allowed if {
    input.user.role == "admin"
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
