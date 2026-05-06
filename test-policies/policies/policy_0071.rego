package governance.authorization.policy.verify.core.policy_0071

# Auto-generated policy 71
# Package: governance.authorization.policy.verify.core

# Metadata
metadata := {
    "policy_id": "0071",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0071_allowed if {
    input.user.role == "admin"
}
policy_0071_allowed if {
    input.user.active
    input.resource.public
}
default policy_0071_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
