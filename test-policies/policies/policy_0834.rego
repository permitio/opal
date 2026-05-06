package compliance.authentication.action.deny.helpers.policy_0834

# Auto-generated policy 834
# Package: compliance.authentication.action.deny.helpers

# Metadata
metadata := {
    "policy_id": "0834",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0834_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0834_denied if {
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
