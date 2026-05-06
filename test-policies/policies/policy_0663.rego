package governance.authorization.resource.check.policy_0663

# Auto-generated policy 663
# Package: governance.authorization.resource.check

# Metadata
metadata := {
    "policy_id": "0663",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0663_allowed = false
policy_0663_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0663_allowed if {
    input.user.active
    input.resource.public
}
policy_0663_allowed if {
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
