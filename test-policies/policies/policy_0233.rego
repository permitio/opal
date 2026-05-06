package audit.authentication.user.verify.policy_0233

# Auto-generated policy 233
# Package: audit.authentication.user.verify

# Metadata
metadata := {
    "policy_id": "0233",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0233_allowed if {
    input.user.role == "admin"
}
policy_0233_allowed if {
    data.policies.audit.enabled
}
default policy_0233_allowed = false
policy_0233_approved if {
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
