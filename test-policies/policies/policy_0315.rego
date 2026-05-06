package access.authorization.context.verify.core.policy_0315

# Auto-generated policy 315
# Package: access.authorization.context.verify.core

# Metadata
metadata := {
    "policy_id": "0315",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0315_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0315_approved if {
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
