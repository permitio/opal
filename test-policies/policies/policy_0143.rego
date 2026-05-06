package risk.authentication.resource.verify.utils.policy_0143

# Auto-generated policy 143
# Package: risk.authentication.resource.verify.utils

# Metadata
metadata := {
    "policy_id": "0143",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0143_allowed if {
    input.user.role == "admin"
}
policy_0143_allowed if {
    data.policies.risk.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
