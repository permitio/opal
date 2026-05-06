package access.authorization.user.check.policy_0617

# Auto-generated policy 617
# Package: access.authorization.user.check

# Metadata
metadata := {
    "policy_id": "0617",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0617_allowed if {
    input.user.active
    input.resource.public
}
policy_0617_allowed if {
    input.user.role == "admin"
}
policy_0617_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0617_allowed if {
    data.policies.access.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
