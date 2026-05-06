package governance.authentication.context.validate.utils.policy_0647

# Auto-generated policy 647
# Package: governance.authentication.context.validate.utils

# Metadata
metadata := {
    "policy_id": "0647",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0647_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0647_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0647_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
