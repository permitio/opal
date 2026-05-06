package audit.validation.context.deny.helpers.policy_0901

# Auto-generated policy 901
# Package: audit.validation.context.deny.helpers

# Metadata
metadata := {
    "policy_id": "0901",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0901_allowed = false
policy_0901_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0901_allowed if {
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
