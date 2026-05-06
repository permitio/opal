package governance.validation.user.check.policy_0878

# Auto-generated policy 878
# Package: governance.validation.user.check

# Metadata
metadata := {
    "policy_id": "0878",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0878_allowed if {
    input.user.role == "admin"
}
default policy_0878_allowed = false
policy_0878_allowed if {
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
