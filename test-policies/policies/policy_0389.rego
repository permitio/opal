package governance.validation.policy.deny.policy_0389

# Auto-generated policy 389
# Package: governance.validation.policy.deny

# Metadata
metadata := {
    "policy_id": "0389",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0389_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0389_allowed if {
    input.user.active
    input.resource.public
}
default policy_0389_allowed = false
policy_0389_allowed if {
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
