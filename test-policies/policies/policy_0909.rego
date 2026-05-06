package compliance.validation.policy.deny.policy_0909

# Auto-generated policy 909
# Package: compliance.validation.policy.deny

# Metadata
metadata := {
    "policy_id": "0909",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0909_allowed if {
    input.user.role == "admin"
}
default policy_0909_allowed = false
policy_0909_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0909_allowed if {
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
