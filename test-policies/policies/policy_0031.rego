package risk.authentication.resource.verify.data.policy_0031

# Auto-generated policy 31
# Package: risk.authentication.resource.verify.data

# Metadata
metadata := {
    "policy_id": "0031",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0031_allowed if {
    data.policies.risk.enabled
}
default policy_0031_allowed = false
policy_0031_allowed if {
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
