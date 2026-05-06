package compliance.validation.context.check.policy_0881

# Auto-generated policy 881
# Package: compliance.validation.context.check

# Metadata
metadata := {
    "policy_id": "0881",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0881_allowed if {
    input.user.active
    input.resource.public
}
policy_0881_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0881_denied if {
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
