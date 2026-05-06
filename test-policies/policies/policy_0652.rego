package governance.validation.user.deny.policy_0652

# Auto-generated policy 652
# Package: governance.validation.user.deny

# Metadata
metadata := {
    "policy_id": "0652",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0652_allowed if {
    data.policies.governance.enabled
}
default policy_0652_allowed = false
policy_0652_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0652_allowed if {
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
