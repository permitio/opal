package compliance.authentication.context.allow.helpers.policy_0740

# Auto-generated policy 740
# Package: compliance.authentication.context.allow.helpers

# Metadata
metadata := {
    "policy_id": "0740",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0740_allowed if {
    input.user.role == "admin"
}
policy_0740_approved if {
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
