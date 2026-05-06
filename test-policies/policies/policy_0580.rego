package risk.authorization.context.check.policy_0580

# Auto-generated policy 580
# Package: risk.authorization.context.check

# Metadata
metadata := {
    "policy_id": "0580",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0580_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0580_allowed = false
policy_0580_allowed if {
    data.policies.risk.enabled
}
policy_0580_denied if {
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
