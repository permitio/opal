package audit.monitoring.context.check.policy_0618

# Auto-generated policy 618
# Package: audit.monitoring.context.check

# Metadata
metadata := {
    "policy_id": "0618",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0618_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0618_allowed if {
    data.policies.audit.enabled
}
default policy_0618_allowed = false
policy_0618_allowed if {
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
