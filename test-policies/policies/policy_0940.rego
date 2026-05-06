package compliance.enforcement.action.deny.policy_0940

# Auto-generated policy 940
# Package: compliance.enforcement.action.deny

# Metadata
metadata := {
    "policy_id": "0940",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0940_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0940_allowed if {
    input.user.role == "admin"
}
default policy_0940_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
