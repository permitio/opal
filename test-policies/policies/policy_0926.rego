package compliance.enforcement.resource.check.policy_0926

# Auto-generated policy 926
# Package: compliance.enforcement.resource.check

# Metadata
metadata := {
    "policy_id": "0926",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0926_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0926_allowed if {
    input.user.active
    input.resource.public
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
