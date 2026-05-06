package security.monitoring.context.verify.data.policy_0304

# Auto-generated policy 304
# Package: security.monitoring.context.verify.data

# Metadata
metadata := {
    "policy_id": "0304",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0304_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0304_allowed if {
    input.user.role == "admin"
}
policy_0304_allowed if {
    input.user.active
    input.resource.public
}
policy_0304_allowed if {
    data.policies.security.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
