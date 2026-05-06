package risk.authentication.user.check.core.policy_0810

# Auto-generated policy 810
# Package: risk.authentication.user.check.core

# Metadata
metadata := {
    "policy_id": "0810",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0810_allowed if {
    data.policies.risk.enabled
}
policy_0810_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0810_denied if {
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
