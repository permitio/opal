package governance.enforcement.resource.verify.policy_0708

# Auto-generated policy 708
# Package: governance.enforcement.resource.verify

# Metadata
metadata := {
    "policy_id": "0708",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0708_allowed if {
    input.user.role == "admin"
}
policy_0708_allowed if {
    input.user.active
    input.resource.public
}
policy_0708_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
