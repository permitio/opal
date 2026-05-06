package governance.authorization.context.verify.policy_0931

# Auto-generated policy 931
# Package: governance.authorization.context.verify

# Metadata
metadata := {
    "policy_id": "0931",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0931_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0931_approved if {
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
