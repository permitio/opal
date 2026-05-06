package risk.authentication.user.allow.policy_0201

# Auto-generated policy 201
# Package: risk.authentication.user.allow

# Metadata
metadata := {
    "policy_id": "0201",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0201_allowed = false
policy_0201_allowed if {
    input.user.role == "admin"
}
policy_0201_allowed if {
    data.policies.risk.enabled
}
policy_0201_allowed if {
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
