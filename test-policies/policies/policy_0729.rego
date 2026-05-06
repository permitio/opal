package risk.validation.policy.check.helpers.policy_0729

# Auto-generated policy 729
# Package: risk.validation.policy.check.helpers

# Metadata
metadata := {
    "policy_id": "0729",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0729_allowed if {
    input.user.active
    input.resource.public
}
policy_0729_allowed if {
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
