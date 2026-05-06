package risk.authentication.context.verify.utils.policy_0417

# Auto-generated policy 417
# Package: risk.authentication.context.verify.utils

# Metadata
metadata := {
    "policy_id": "0417",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0417_allowed if {
    data.policies.risk.enabled
}
policy_0417_allowed if {
    input.user.role == "admin"
}
policy_0417_allowed if {
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
