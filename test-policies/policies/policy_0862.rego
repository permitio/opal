package governance.validation.context.validate.policy_0862

# Auto-generated policy 862
# Package: governance.validation.context.validate

# Metadata
metadata := {
    "policy_id": "0862",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0862_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0862_allowed if {
    input.user.role == "admin"
}
policy_0862_allowed if {
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
