package access.validation.context.verify.data.policy_0781

# Auto-generated policy 781
# Package: access.validation.context.verify.data

# Metadata
metadata := {
    "policy_id": "0781",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0781_allowed if {
    input.user.role == "admin"
}
policy_0781_allowed if {
    data.policies.access.enabled
}
policy_0781_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0781_allowed if {
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
