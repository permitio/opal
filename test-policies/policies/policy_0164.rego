package governance.authorization.action.verify.policy_0164

# Auto-generated policy 164
# Package: governance.authorization.action.verify

# Metadata
metadata := {
    "policy_id": "0164",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0164_allowed if {
    data.policies.governance.enabled
}
policy_0164_allowed if {
    input.user.active
    input.resource.public
}
default policy_0164_allowed = false
policy_0164_allowed if {
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
