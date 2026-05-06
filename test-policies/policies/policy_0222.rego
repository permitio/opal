package governance.validation.policy.validate.data.policy_0222

# Auto-generated policy 222
# Package: governance.validation.policy.validate.data

# Metadata
metadata := {
    "policy_id": "0222",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0222_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0222_allowed if {
    input.user.active
    input.resource.public
}
policy_0222_denied if {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
