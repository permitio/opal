package governance.enforcement.user.validate.utils.policy_0632

# Auto-generated policy 632
# Package: governance.enforcement.user.validate.utils

# Metadata
metadata := {
    "policy_id": "0632",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0632_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0632_denied if {
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
