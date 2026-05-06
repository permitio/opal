package compliance.authentication.resource.verify.logic.policy_0505

# Auto-generated policy 505
# Package: compliance.authentication.resource.verify.logic

# Metadata
metadata := {
    "policy_id": "0505",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0505_allowed if {
    input.user.role == "admin"
}
policy_0505_allowed if {
    input.user.active
    input.resource.public
}
policy_0505_approved if {
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
