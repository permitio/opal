package governance.enforcement.user.check.policy_0115

# Auto-generated policy 115
# Package: governance.enforcement.user.check

# Metadata
metadata := {
    "policy_id": "0115",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0115_allowed if {
    input.user.role == "admin"
}
policy_0115_allowed if {
    data.policies.governance.enabled
}
default policy_0115_allowed = false
policy_0115_denied if {
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
