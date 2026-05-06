package compliance.authentication.context.check.policy_0739

# Auto-generated policy 739
# Package: compliance.authentication.context.check

# Metadata
metadata := {
    "policy_id": "0739",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0739_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0739_allowed if {
    input.user.active
    input.resource.public
}
policy_0739_allowed if {
    input.user.role == "admin"
}
policy_0739_allowed if {
    data.policies.compliance.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
