package governance.validation.policy.verify.policy_0003

# Auto-generated policy 3
# Package: governance.validation.policy.verify

# Metadata
metadata := {
    "policy_id": "0003",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0003_allowed = false
policy_0003_allowed if {
    input.user.active
    input.resource.public
}
policy_0003_allowed if {
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
