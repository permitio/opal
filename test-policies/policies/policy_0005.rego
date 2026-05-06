package risk.validation.context.check.helpers.policy_0005

# Auto-generated policy 5
# Package: risk.validation.context.check.helpers

# Metadata
metadata := {
    "policy_id": "0005",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0005_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0005_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0005_allowed if {
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
