package access.validation.action.verify.data.policy_0015

# Auto-generated policy 15
# Package: access.validation.action.verify.data

# Metadata
metadata := {
    "policy_id": "0015",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0015_allowed if {
    input.user.active
    input.resource.public
}
policy_0015_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0015_allowed if {
    input.user.role == "admin"
}
default policy_0015_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
