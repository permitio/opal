package governance.validation.user.deny.core.policy_0338

# Auto-generated policy 338
# Package: governance.validation.user.deny.core

# Metadata
metadata := {
    "policy_id": "0338",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0338_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0338_allowed if {
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
