package risk.authorization.action.check.logic.policy_0402

# Auto-generated policy 402
# Package: risk.authorization.action.check.logic

# Metadata
metadata := {
    "policy_id": "0402",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0402_allowed = false
policy_0402_allowed if {
    input.user.active
    input.resource.public
}
policy_0402_allowed if {
    input.user.role == "admin"
}
policy_0402_approved if {
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
