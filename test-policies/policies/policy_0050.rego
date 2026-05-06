package governance.validation.context.allow.utils.policy_0050

# Auto-generated policy 50
# Package: governance.validation.context.allow.utils

# Metadata
metadata := {
    "policy_id": "0050",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0050_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0050_allowed if {
    input.user.role == "admin"
}
default policy_0050_allowed = false
policy_0050_allowed if {
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
