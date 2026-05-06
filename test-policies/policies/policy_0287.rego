package risk.authorization.user.check.policy_0287

# Auto-generated policy 287
# Package: risk.authorization.user.check

# Metadata
metadata := {
    "policy_id": "0287",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0287_allowed if {
    input.user.active
    input.resource.public
}
policy_0287_allowed if {
    input.user.role == "admin"
}
default policy_0287_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
