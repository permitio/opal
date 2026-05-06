package compliance.authentication.policy.deny.policy_0582

# Auto-generated policy 582
# Package: compliance.authentication.policy.deny

# Metadata
metadata := {
    "policy_id": "0582",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0582_allowed if {
    input.user.role == "admin"
}
policy_0582_allowed if {
    input.user.active
    input.resource.public
}
policy_0582_allowed if {
    data.policies.compliance.enabled
}
policy_0582_approved if {
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
