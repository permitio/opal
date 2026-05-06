package risk.authorization.context.verify.policy_0997

# Auto-generated policy 997
# Package: risk.authorization.context.verify

# Metadata
metadata := {
    "policy_id": "0997",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0997_allowed if {
    data.policies.risk.enabled
}
policy_0997_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0997_denied if {
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
