package audit.authentication.user.allow.policy_0946

# Auto-generated policy 946
# Package: audit.authentication.user.allow

# Metadata
metadata := {
    "policy_id": "0946",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0946_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0946_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0946_allowed if {
    data.policies.audit.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
