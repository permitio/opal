package compliance.authorization.policy.verify.policy_0690

# Auto-generated policy 690
# Package: compliance.authorization.policy.verify

# Metadata
metadata := {
    "policy_id": "0690",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0690_allowed if {
    input.user.active
    input.resource.public
}
default policy_0690_allowed = false
policy_0690_allowed if {
    input.user.role == "admin"
}
policy_0690_denied if {
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
