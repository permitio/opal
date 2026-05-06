package compliance.validation.policy.allow.logic.policy_0828

# Auto-generated policy 828
# Package: compliance.validation.policy.allow.logic

# Metadata
metadata := {
    "policy_id": "0828",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0828_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0828_allowed if {
    input.user.active
    input.resource.public
}
policy_0828_approved if {
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
